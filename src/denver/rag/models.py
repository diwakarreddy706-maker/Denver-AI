"""Data models for Denver Document and PDF Semantic RAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DocumentMetadata:
    """Metadata regarding an indexed document file."""
    file_path: str
    file_name: str
    file_type: str
    file_size_bytes: int
    chunk_count: int = 0
    page_count: int = 1
    indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size_bytes": self.file_size_bytes,
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "indexed_at": self.indexed_at,
        }


@dataclass
class DocumentChunk:
    """Represents a discrete semantic chunk of an indexed document."""
    doc_id: str
    file_path: str
    file_name: str
    chunk_index: int
    content_chunk: str
    id: int | None = None
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "chunk_index": self.chunk_index,
            "content_chunk": self.content_chunk,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class DocumentSearchResult:
    """A scored result item from document search."""
    file_name: str
    file_path: str
    chunk_index: int
    snippet: str
    score: float
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "chunk_index": self.chunk_index,
            "snippet": self.snippet,
            "score": round(self.score, 4),
            "page": self.page,
            "metadata": self.metadata,
        }


@dataclass
class DocumentAnswer:
    """Complete synthesized response to a user query backed by RAG citations."""
    query: str
    answer: str
    sources: list[DocumentSearchResult] = field(default_factory=list)
    confidence: float = 1.0

    def format_display(self) -> str:
        out = [self.answer]
        if self.sources:
            out.append("\nSources:")
            for i, s in enumerate(self.sources, start=1):
                page_info = f" (page {s.page})" if s.page else ""
                out.append(f"  {i}. {s.file_name}{page_info} [relevance {int(s.score * 100)}%]")
        return "\n".join(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "confidence": self.confidence,
            "sources": [s.to_dict() for s in self.sources],
        }
