"""Unit tests for Denver Document & PDF Semantic RAG (Step 3)."""

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from denver.automation.executor import AutomationExecutor
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService, CommandRequest
from denver.rag.extractor import (
    _extract_docx,
    _split_text_with_overlap,
    chunk_extracted_document,
    extract_document,
)
from denver.rag.models import (
    DocumentAnswer,
    DocumentChunk,
    DocumentMetadata,
    DocumentSearchResult,
)
from denver.rag.service import DocumentRAGService


def test_document_models():
    """Verify serialization and formatting of RAG domain models."""
    meta = DocumentMetadata(
        file_path="C:/docs/quarterly_report.pdf",
        file_name="quarterly_report.pdf",
        file_type="pdf",
        file_size_bytes=1048576,
        chunk_count=12,
        page_count=4,
    )
    d = meta.to_dict()
    assert d["file_name"] == "quarterly_report.pdf"
    assert d["chunk_count"] == 12

    chunk = DocumentChunk(
        doc_id="doc123",
        file_path="C:/docs/notes.txt",
        file_name="notes.txt",
        chunk_index=0,
        content_chunk="Project Phoenix roadmap kicks off in Q4 2026.",
        metadata={"page": 1},
    )
    assert chunk.content_chunk.startswith("Project Phoenix")
    assert chunk.to_dict()["doc_id"] == "doc123"

    res = DocumentSearchResult(
        file_name="notes.txt",
        file_path="C:/docs/notes.txt",
        chunk_index=0,
        snippet="Project Phoenix roadmap...",
        score=0.92,
        page=1,
    )
    assert res.score == 0.92

    ans = DocumentAnswer(
        query="When does Project Phoenix start?",
        answer="Project Phoenix kicks off in Q4 2026.",
        sources=[res],
    )
    disp = ans.format_display()
    assert "Project Phoenix kicks off in Q4 2026." in disp
    assert "notes.txt" in disp
    assert "page 1" in disp


def test_text_and_markdown_extraction_and_chunking():
    """Verify plain text and markdown extraction with paragraph chunking and overlap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = Path(tmpdir) / "project_overview.md"
        doc_path.write_text(
            "# Autonomous Assistant\n\n"
            "Denver is an AI desktop companion built for Windows 11.\n\n"
            "Key capabilities include voice control, task orchestration, and local document RAG.\n\n"
            "Security is enforced via scoped confirmation tokens for high-risk operations.",
            encoding="utf-8",
        )

        extracted = extract_document(doc_path)
        assert extracted.file_name == "project_overview.md"
        assert extracted.file_type == "md"
        assert "Denver is an AI desktop companion" in extracted.total_text

        chunks = chunk_extracted_document(extracted, chunk_size=120, overlap=30)
        assert len(chunks) >= 2
        for c in chunks:
            assert "content_chunk" in c
            assert c["file_name"] == "project_overview.md"


def test_docx_extraction_zip_xml():
    """Verify DOCX extraction from standard OpenXML zip archive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "sample_doc.docx"
        # Create a minimal valid docx zip structure
        xml_content = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body>'
            b'<w:p><w:r><w:t>Confidential Strategy Document.</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Projected revenue growth exceeds 45 percent year-over-year.</w:t></w:r></w:p>'
            b'</w:body></w:document>'
        )
        with zipfile.ZipFile(docx_path, "w") as zf:
            zf.writestr("word/document.xml", xml_content)

        extracted = extract_document(docx_path)
        assert extracted.file_type == "docx"
        assert "Confidential Strategy Document" in extracted.total_text
        assert "Projected revenue growth exceeds 45 percent" in extracted.total_text


@pytest.mark.asyncio
async def test_rag_service_indexing_and_search():
    """Verify full RAG lifecycle: file indexing, SQLite storage, semantic search, and document listing."""
    conn = sqlite3.connect(":memory:")
    service = DocumentRAGService(conn)

    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = Path(tmpdir) / "machine_learning.txt"
        f1.write_text(
            "Machine learning is a field of artificial intelligence focused on building applications that learn from data.\n\n"
            "Supervised learning algorithms train on labeled examples to make predictions.\n\n"
            "Unsupervised learning finds hidden patterns and intrinsic groupings in unlabeled datasets.",
            encoding="utf-8",
        )

        f2 = Path(tmpdir) / "kitchen_recipes.txt"
        f2.write_text(
            "Classic Neapolitan Pizza Recipe:\n\n"
            "Ingredients: 500g Tipo 00 flour, 325ml water, 10g fine salt, 3g active dry yeast.\n\n"
            "Knead the dough vigorously for 15 minutes, then ferment at room temperature for 8 hours.",
            encoding="utf-8",
        )

        # 1. Index files
        meta1 = await service.index_file(f1)
        assert meta1.chunk_count >= 1
        meta2 = await service.index_file(f2)
        assert meta2.chunk_count >= 1

        # 2. List indexed documents
        doc_list = service.list_documents()
        assert len(doc_list) == 2
        names = [d["file_name"] for d in doc_list]
        assert "machine_learning.txt" in names
        assert "kitchen_recipes.txt" in names

        # 3. Search: Machine learning query
        results_ml = await service.search("supervised learning labeled data", top_k=3)
        assert len(results_ml) > 0
        assert results_ml[0].file_name == "machine_learning.txt"
        assert "Supervised learning" in results_ml[0].snippet

        # 4. Search: Pizza dough query
        results_pizza = await service.search("how to make pizza dough yeast water", top_k=3)
        assert len(results_pizza) > 0
        assert results_pizza[0].file_name == "kitchen_recipes.txt"
        assert "Neapolitan Pizza" in results_pizza[0].snippet

        # 5. Delete document
        deleted = service.delete_document("kitchen_recipes.txt")
        assert deleted is True
        assert len(service.list_documents()) == 1


@pytest.mark.asyncio
async def test_rag_service_ask_question():
    """Verify question synthesis against indexed document chunks."""
    conn = sqlite3.connect(":memory:")
    service = DocumentRAGService(conn)

    with tempfile.TemporaryDirectory() as tmpdir:
        doc = Path(tmpdir) / "wifi_instructions.txt"
        doc.write_text(
            "Guest Wi-Fi Network Credentials:\n\n"
            "SSID: DenverHQ-Guest\n"
            "Password: PegasusSkyline99\n"
            "Band: 5GHz preferred for best throughput.",
            encoding="utf-8",
        )

        await service.index_file(doc)

        # Query existing information
        answer = await service.ask("what is the guest wifi password?")
        assert answer.confidence > 0.0
        assert len(answer.sources) > 0
        assert "wifi_instructions.txt" in answer.format_display()

        # Query nonexistent information
        ans_missing = await service.ask("what is the capital of Mars?")
        assert ans_missing.confidence == 0.0
        assert "couldn't find" in ans_missing.answer.lower()


def test_document_rag_router_intents():
    """Verify regex intent matching for all document RAG commands."""
    router = IntentRouter()

    # Index document
    i1 = router.route("index document C:/Users/diwak/Desktop/report.pdf")
    assert i1.action_name == "index_document"
    assert "report.pdf" in i1.params["path"]

    i1b = router.route("read and index 'my_notes.txt'")
    assert i1b.action_name == "index_document"
    assert i1b.params["path"] == "my_notes.txt"

    # Search documents
    i2 = router.route("search documents for revenue goals")
    assert i2.action_name == "search_documents"
    assert i2.params["query"] == "revenue goals"

    i2b = router.route("find in documents quarterly performance")
    assert i2b.action_name == "search_documents"
    assert i2b.params["query"] == "quarterly performance"

    # Ask document
    i3 = router.route("ask documents what is the guest wifi password?")
    assert i3.action_name == "ask_document"
    assert "wifi" in i3.params["query"]

    # List documents
    i4 = router.route("list indexed documents")
    assert i4.action_name == "list_documents"

    # Delete document
    i5 = router.route("delete document report.pdf")
    assert i5.action_name == "delete_document"
    assert i5.params["path"] == "report.pdf"


@pytest.mark.asyncio
async def test_document_rag_command_engine_integration():
    """Verify end-to-end execution of RAG commands through CommandEngineService."""
    executor = AutomationExecutor()
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

    with tempfile.TemporaryDirectory() as tmpdir:
        sample_file = Path(tmpdir) / "server_specs.txt"
        sample_file.write_text(
            "Primary Production Server Architecture:\n\n"
            "Hostname: srv-denver-edge-01\n"
            "CPU: AMD EPYC 9654 96-Core Processor\n"
            "RAM: 512GB DDR5 Registered ECC\n"
            "Storage: 4x 7.68TB NVMe U.3 Enterprise SSDs in RAID 10.",
            encoding="utf-8",
        )

        # 1. Index document via CommandEngineService
        res_idx = await service.process_command(
            CommandRequest(raw_text=f"index document {sample_file}")
        )
        assert res_idx.success is True
        assert res_idx.action_name == "index_document"
        assert "server_specs.txt" in res_idx.message

        # 2. List documents
        res_list = await service.process_command(
            CommandRequest(raw_text="list indexed documents")
        )
        assert res_list.success is True
        assert res_list.action_name == "list_documents"
        assert "server_specs.txt" in res_list.message

        # 3. Search documents
        res_search = await service.process_command(
            CommandRequest(raw_text="search documents for AMD EPYC processor")
        )
        assert res_search.success is True
        assert res_search.action_name == "search_documents"
        assert "srv-denver-edge-01" in res_search.message

        # 4. Ask documents
        res_ask = await service.process_command(
            CommandRequest(raw_text="ask documents what CPU does the server have?")
        )
        assert res_ask.success is True
        assert res_ask.action_name == "ask_document"
        assert "AMD EPYC" in res_ask.message

        # 5. Delete document
        res_del = await service.process_command(
            CommandRequest(raw_text="delete document server_specs.txt")
        )
        assert res_del.success is True
        assert res_del.action_name == "delete_document"
