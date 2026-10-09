"""Document Text Extractor and Chunking Engine for Denver RAG."""

from __future__ import annotations

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("rag.extractor")


class ExtractedDocument:
    """Represents raw extracted text and metadata from a local file."""

    def __init__(
        self,
        file_path: str,
        file_name: str,
        file_type: str,
        file_size: int,
        pages: list[dict[str, Any]],
    ) -> None:
        self.file_path = file_path
        self.file_name = file_name
        self.file_type = file_type
        self.file_size = file_size
        self.pages = pages  # list of {"page": int, "text": str}

    @property
    def total_text(self) -> str:
        return "\n\n".join(p["text"] for p in self.pages if p.get("text"))

    @property
    def page_count(self) -> int:
        return max(1, len(self.pages))


def extract_document(path: str | Path) -> ExtractedDocument:
    """Extract readable text and page metadata from any supported document format."""
    p = Path(path).resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Document file does not exist: {p}")

    ext = p.suffix.lower()
    file_size = p.stat().st_size
    file_name = p.name

    if ext == ".pdf":
        return _extract_pdf(p, file_name, file_size)
    elif ext == ".docx":
        return _extract_docx(p, file_name, file_size)
    else:
        # Default text/code extractor for .txt, .md, .py, .csv, .json, .log, etc.
        return _extract_plain_text(p, file_name, file_size, ext.lstrip("."))


def _extract_pdf(path: Path, file_name: str, file_size: int) -> ExtractedDocument:
    """Extract text per page from PDF using pypdf."""
    pages: list[dict[str, Any]] = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append({"page": idx, "text": text})
    except Exception as exc:
        logger.warning("pypdf extraction failed or degraded for %s: %s", path, exc)
        # Fallback to binary/regex text scanning
        try:
            raw = path.read_bytes()
            # Basic text pattern extraction
            matches = re.findall(rb"\(([^\)]+)\)\s*Tj", raw)
            if matches:
                recovered = b" ".join(matches).decode("latin-1", errors="ignore")
                pages.append({"page": 1, "text": recovered})
        except Exception:
            pass

    if not pages:
        pages.append({"page": 1, "text": ""})

    return ExtractedDocument(
        file_path=str(path),
        file_name=file_name,
        file_type="pdf",
        file_size=file_size,
        pages=pages,
    )


def _extract_docx(path: Path, file_name: str, file_size: int) -> ExtractedDocument:
    """Extract text from docx zip XML without external binary dependencies."""
    paragraphs: list[str] = []
    try:
        with zipfile.ZipFile(str(path)) as zf:
            xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Find all text nodes in w:t tags
            for p in tree.iter():
                if p.tag.endswith("p"):
                    p_text = "".join(node.text for node in p.iter() if node.tag.endswith("t") and node.text)
                    if p_text.strip():
                        paragraphs.append(p_text.strip())
    except Exception as exc:
        logger.warning("DOCX extraction error for %s: %s", path, exc)

    full_text = "\n\n".join(paragraphs)
    return ExtractedDocument(
        file_path=str(path),
        file_name=file_name,
        file_type="docx",
        file_size=file_size,
        pages=[{"page": 1, "text": full_text}],
    )


def _extract_plain_text(path: Path, file_name: str, file_size: int, file_type: str) -> ExtractedDocument:
    """Extract plain text or source code files with encoding detection."""
    content = ""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            content = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue

    return ExtractedDocument(
        file_path=str(path),
        file_name=file_name,
        file_type=file_type or "text",
        file_size=file_size,
        pages=[{"page": 1, "text": content}],
    )


def chunk_extracted_document(
    doc: ExtractedDocument,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[dict[str, Any]]:
    """Chunk an extracted document while preserving page metadata and sentence boundaries."""
    chunks: list[dict[str, Any]] = []

    for page_info in doc.pages:
        page_num = page_info.get("page", 1)
        raw_text = page_info.get("text", "").strip()
        if not raw_text:
            continue

        page_chunks = _split_text_with_overlap(raw_text, chunk_size=chunk_size, overlap=overlap)
        for chunk_text in page_chunks:
            if chunk_text.strip():
                chunks.append({
                    "content_chunk": chunk_text.strip(),
                    "page": page_num,
                    "file_name": doc.file_name,
                    "file_path": doc.file_path,
                    "file_type": doc.file_type,
                })

    return chunks


def _split_text_with_overlap(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into chunks with character length and semantic boundaries."""
    if len(text) <= chunk_size:
        return [text]

    # Split into paragraphs first
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    current_buf: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len + 1 > chunk_size and current_buf:
            chunk_content = "\n\n".join(current_buf)
            chunks.append(chunk_content)

            # Preserve overlap from tail of current_buf
            tail_buf: list[str] = []
            tail_len = 0
            for item in reversed(current_buf):
                if tail_len + len(item) <= overlap:
                    tail_buf.insert(0, item)
                    tail_len += len(item)
                else:
                    break
            current_buf = tail_buf
            current_len = tail_len

        current_buf.append(para)
        current_len += para_len + 1

    if current_buf:
        chunk_content = "\n\n".join(current_buf)
        if not chunks or chunks[-1] != chunk_content:
            chunks.append(chunk_content)

    return chunks
