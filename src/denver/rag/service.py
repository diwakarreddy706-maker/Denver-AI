"""Document RAG Service: Indexing, Semantic Vector Search & Question Answering."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger
from denver.memory.database import sanitize_fts_query
from denver.memory.embeddings import EmbeddingManager, cosine_similarity
from denver.memory.repositories import _deserialize_vec, _serialize_vec
from denver.rag.extractor import chunk_extracted_document, extract_document
from denver.rag.models import DocumentAnswer, DocumentChunk, DocumentMetadata, DocumentSearchResult

logger = get_logger("rag.service")


class DocumentRAGService:
    """Manages document ingestion, chunk storage, vector similarity search, and RAG Q&A."""

    def __init__(
        self,
        db_conn_or_path: sqlite3.Connection | str = "denver_memory.sqlite3",
        embedding_manager: EmbeddingManager | None = None,
        llm_provider: Any = None,
    ) -> None:
        if isinstance(db_conn_or_path, sqlite3.Connection):
            self.conn = db_conn_or_path
        else:
            self.conn = sqlite3.connect(str(db_conn_or_path), check_same_thread=False)
        self.embedding_manager = embedding_manager or EmbeddingManager()
        self.llm_provider = llm_provider
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure document_chunks table and FTS5 full-text index exist."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content_chunk TEXT NOT NULL,
                embedding BLOB,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(doc_id);
            CREATE INDEX IF NOT EXISTS idx_doc_chunks_file_path ON document_chunks(file_path);
            CREATE INDEX IF NOT EXISTS idx_doc_chunks_file_name ON document_chunks(file_name);
            """
        )
        try:
            self.conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
                    file_name,
                    content_chunk,
                    content=document_chunks,
                    content_rowid=id
                );

                CREATE TRIGGER IF NOT EXISTS doc_chunks_ai AFTER INSERT ON document_chunks BEGIN
                    INSERT INTO document_chunks_fts(rowid, file_name, content_chunk)
                    VALUES (new.id, COALESCE(new.file_name, ''), COALESCE(new.content_chunk, ''));
                END;

                CREATE TRIGGER IF NOT EXISTS doc_chunks_ad AFTER DELETE ON document_chunks BEGIN
                    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, file_name, content_chunk)
                    VALUES('delete', old.id, COALESCE(old.file_name, ''), COALESCE(old.content_chunk, ''));
                END;

                CREATE TRIGGER IF NOT EXISTS doc_chunks_au AFTER UPDATE ON document_chunks BEGIN
                    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, file_name, content_chunk)
                    VALUES('delete', old.id, COALESCE(old.file_name, ''), COALESCE(old.content_chunk, ''));
                    INSERT INTO document_chunks_fts(rowid, file_name, content_chunk)
                    VALUES (new.id, COALESCE(new.file_name, ''), COALESCE(new.content_chunk, ''));
                END;
                """
            )
        except sqlite3.OperationalError as exc:
            logger.debug("FTS5 table initialization skipped in RAGService: %s", exc)
        self.conn.commit()

    async def index_file(self, file_path: str | Path) -> DocumentMetadata:
        """Extract text, chunk, generate embeddings, and persist chunks to SQLite."""
        p = Path(file_path).resolve()
        extracted = extract_document(p)
        chunks = chunk_extracted_document(extracted, chunk_size=750, overlap=120)

        if not chunks:
            # Handle empty document
            chunks = [{
                "content_chunk": f"[Empty Document: {extracted.file_name}]",
                "page": 1,
                "file_name": extracted.file_name,
                "file_path": extracted.file_path,
                "file_type": extracted.file_type,
            }]

        doc_id = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:16]

        # 1. Generate embeddings in batch
        texts: list[str] = [str(c["content_chunk"]) for c in chunks]
        vectors, _ = await self.embedding_manager.embed_batch(texts)

        # 2. Clear old chunks for this document
        self.conn.execute("DELETE FROM document_chunks WHERE file_path = ?;", (str(p),))

        # 3. Store new chunks
        cursor = self.conn.cursor()
        for idx, (chunk_data, vec) in enumerate(zip(chunks, vectors)):
            meta = {
                "page": chunk_data.get("page", 1),
                "file_type": chunk_data.get("file_type", ""),
            }
            blob = _serialize_vec(vec)
            cursor.execute(
                """
                INSERT INTO document_chunks (doc_id, file_path, file_name, chunk_index, content_chunk, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (doc_id, str(p), p.name, idx, chunk_data["content_chunk"], blob, json.dumps(meta)),
            )

        self.conn.commit()
        logger.info("Indexed '%s' into %d chunks with embeddings.", p.name, len(chunks))

        return DocumentMetadata(
            file_path=str(p),
            file_name=p.name,
            file_type=extracted.file_type,
            file_size_bytes=extracted.file_size,
            chunk_count=len(chunks),
            page_count=extracted.page_count,
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        file_filter: str | None = None,
    ) -> list[DocumentSearchResult]:
        return await self.search_chunks(query=query, top_k=top_k, file_filter=file_filter)

    def _retrieve_candidate_chunks(
        self,
        query: str,
        file_filter: str | None = None,
        candidate_limit: int = 60,
    ) -> list[tuple]:
        """Stage 1: Retrieve candidate chunks via FTS5 BM25 index with fallback to recent/matching rows."""
        candidate_ids: set[int] = set()
        candidates: list[tuple] = []

        # 1. Try FTS5 BM25 match
        fts_query = sanitize_fts_query(query)
        if fts_query:
            try:
                fts_sql = """
                    SELECT c.id, c.doc_id, c.file_path, c.file_name, c.chunk_index, c.content_chunk, c.embedding, c.metadata
                    FROM document_chunks c
                    JOIN document_chunks_fts fts ON c.id = fts.rowid
                    WHERE document_chunks_fts MATCH ?
                """
                params: list[Any] = [fts_query]
                if file_filter:
                    fts_sql += " AND (c.file_name LIKE ? OR c.file_path LIKE ?)"
                    like_pat = f"%{file_filter.strip()}%"
                    params.extend([like_pat, like_pat])
                fts_sql += " ORDER BY fts.rank LIMIT ?;"
                params.append(candidate_limit)

                cursor = self.conn.execute(fts_sql, params)
                for row in cursor.fetchall():
                    if row[0] not in candidate_ids:
                        candidate_ids.add(row[0])
                        candidates.append(row)
            except Exception as exc:
                logger.debug("FTS5 candidate query exception: %s", exc)

        # 2. If candidates are fewer than candidate_limit, supplement with recent/matching rows
        # ensuring pure semantic matches without exact keyword overlap are not omitted
        if len(candidates) < candidate_limit:
            remaining_limit = candidate_limit - len(candidates)
            fb_sql = "SELECT id, doc_id, file_path, file_name, chunk_index, content_chunk, embedding, metadata FROM document_chunks"
            fb_params: list[Any] = []
            conditions: list[str] = []

            if file_filter:
                conditions.append("(file_name LIKE ? OR file_path LIKE ?)")
                like_pat = f"%{file_filter.strip()}%"
                fb_params.extend([like_pat, like_pat])

            if candidate_ids:
                placeholders = ",".join("?" for _ in candidate_ids)
                conditions.append(f"id NOT IN ({placeholders})")
                fb_params.extend(list(candidate_ids))

            if conditions:
                fb_sql += " WHERE " + " AND ".join(conditions)

            fb_sql += " ORDER BY id DESC LIMIT ?;"
            fb_params.append(remaining_limit)

            try:
                cursor = self.conn.execute(fb_sql, fb_params)
                for row in cursor.fetchall():
                    if row[0] not in candidate_ids:
                        candidate_ids.add(row[0])
                        candidates.append(row)
            except Exception as exc:
                logger.debug("Candidate fallback query exception: %s", exc)

        return candidates

    async def search_chunks(
        self,
        query: str,
        top_k: int = 5,
        file_filter: str | None = None,
    ) -> list[DocumentSearchResult]:
        """Search indexed document chunks using two-stage hybrid retrieval (FTS5 BM25 + cosine vector similarity)."""
        query_clean = query.strip()
        if not query_clean:
            return []

        # Embed query vector
        query_vec, _ = await self.embedding_manager.embed(query_clean)

        # Stage 1: Candidate Generation via FTS5 BM25 + supplemental chunks
        candidate_rows = self._retrieve_candidate_chunks(
            query=query_clean,
            file_filter=file_filter,
            candidate_limit=max(60, top_k * 10),
        )
        if not candidate_rows:
            return []

        # Stage 2: Vector Re-ranking & Lexical Boost
        scored_results: list[DocumentSearchResult] = []
        q_tokens = set(re.findall(r"\w+", query_clean.lower()))

        for row in candidate_rows:
            _id, doc_id, f_path, f_name, c_idx, content, emb_blob, meta_raw = row
            chunk_vec = _deserialize_vec(emb_blob) if emb_blob else []
            sim_score = cosine_similarity(query_vec, chunk_vec) if (query_vec and chunk_vec) else 0.0

            # Lexical boost: check token overlap
            c_tokens = set(re.findall(r"\w+", content.lower()))
            overlap = len(q_tokens.intersection(c_tokens)) / max(1, len(q_tokens))
            hybrid_score = (0.75 * sim_score) + (0.25 * overlap)

            meta = json.loads(meta_raw) if meta_raw else {}
            page_num = meta.get("page")

            # Extract snippet around query or first 250 characters
            snippet = content[:280].strip()
            if len(content) > 280:
                snippet += "..."

            scored_results.append(
                DocumentSearchResult(
                    file_name=f_name,
                    file_path=f_path,
                    chunk_index=c_idx,
                    snippet=snippet,
                    score=hybrid_score,
                    page=page_num,
                    metadata=meta,
                )
            )

        scored_results.sort(key=lambda x: x.score, reverse=True)
        return scored_results[:top_k]

    async def ask(
        self,
        query: str,
        top_k: int = 4,
        file_filter: str | None = None,
    ) -> DocumentAnswer:
        """Synthesize an answer to query using retrieved document chunks and LLM or extractive synthesis."""
        sources = await self.search(query=query, top_k=top_k, file_filter=file_filter)
        if not sources or (sources and sources[0].score < 0.20):
            return DocumentAnswer(
                query=query,
                answer=f"I couldn't find any relevant information in your indexed documents regarding: '{query}'.",
                sources=[],
                confidence=0.0,
            )

        # Context assembly
        context_blocks = []
        for idx, src in enumerate(sources, start=1):
            page_str = f" (Page {src.page})" if src.page else ""
            context_blocks.append(f"[{idx}] {src.file_name}{page_str}:\n{src.snippet}")

        context_str = "\n\n".join(context_blocks)

        # Attempt LLM synthesis if provider available
        if self.llm_provider and hasattr(self.llm_provider, "generate_response"):
            prompt = (
                f"You are Denver AI assistant. Answer the user's question accurately using ONLY the provided document excerpts.\n"
                f"If the excerpts do not contain the answer, say so.\n\n"
                f"Document Excerpts:\n{context_str}\n\n"
                f"User Question: {query}\n\n"
                f"Answer:"
            )
            try:
                res = await self.llm_provider.generate_response(prompt)
                if res and isinstance(res, str) and res.strip():
                    return DocumentAnswer(
                        query=query,
                        answer=res.strip(),
                        sources=sources,
                        confidence=min(1.0, sources[0].score * 1.5),
                    )
            except Exception as exc:
                logger.warning("LLM synthesis error in Document RAG, falling back to extractive summary: %s", exc)

        # Deterministic Extractive fallback
        best_source = sources[0]
        page_ref = f" (Page {best_source.page})" if best_source.page else ""
        extractive_answer = (
            f"Based on **{best_source.file_name}**{page_ref}:\n\n"
            f"> \"{best_source.snippet}\""
        )
        return DocumentAnswer(
            query=query,
            answer=extractive_answer,
            sources=sources,
            confidence=round(best_source.score, 2),
        )

    def list_documents(self) -> list[dict[str, Any]]:
        """List all indexed documents and chunk statistics."""
        cursor = self.conn.execute(
            """
            SELECT file_path, file_name, COUNT(*) as chunks, MIN(created_at) as indexed_at
            FROM document_chunks
            GROUP BY file_path, file_name
            ORDER BY indexed_at DESC;
            """
        )
        results = []
        for row in cursor.fetchall():
            results.append({
                "file_path": row[0],
                "file_name": row[1],
                "chunk_count": row[2],
                "indexed_at": row[3],
            })
        return results

    def delete_document(self, file_target: str) -> bool:
        """Remove indexed document chunks matching file_path or file_name."""
        target = file_target.strip()
        cursor = self.conn.execute(
            "DELETE FROM document_chunks WHERE file_path = ? OR file_name = ?;",
            (target, target),
        )
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted document chunks for '%s'.", file_target)
        return deleted


# Module-level singleton helper
_RAG_SERVICE: DocumentRAGService | None = None


def get_rag_service(db_conn_or_path: sqlite3.Connection | str | None = None) -> DocumentRAGService:
    """Retrieve or initialize shared DocumentRAGService."""
    global _RAG_SERVICE
    if _RAG_SERVICE is None:
        target = db_conn_or_path if db_conn_or_path is not None else "denver_memory.sqlite3"
        _RAG_SERVICE = DocumentRAGService(target)
    elif db_conn_or_path is not None and isinstance(db_conn_or_path, sqlite3.Connection) and _RAG_SERVICE.conn is not db_conn_or_path:
        _RAG_SERVICE = DocumentRAGService(db_conn_or_path)
    return _RAG_SERVICE
