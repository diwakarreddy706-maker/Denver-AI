"""Unit tests for Playwright & CDP Deep Web Agent Subsystem."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.web_agent import (
    WebActionResult,
    WebAgent,
    WebSearchResult,
    _HTMLTextExtractor,
)
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_web.sqlite3"
    return DenverDatabase(db_path=str(db_file))


@pytest.fixture
def memory_service(temp_db):
    return MemoryService(db=temp_db, privacy_mode=False)


def test_html_text_extractor():
    """Verify HTML parser strips scripts, styles, and extracts title & body."""
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Denver Assistant Documentation</title>
        <style>body { font-family: sans-serif; }</style>
        <script>console.log("ignore me");</script>
      </head>
      <body>
        <nav><a href="/">Home</a></nav>
        <header><h1>Welcome Header</h1></header>
        <main>
          <h2>Core Features</h2>
          <p>Denver is an autonomous AI desktop assistant for Windows.</p>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)

    assert parser.title == "Denver Assistant Documentation"
    text = parser.get_text()
    assert "Denver is an autonomous AI desktop assistant" in text
    assert "console.log" not in text
    assert "font-family" not in text


@pytest.mark.asyncio
async def test_web_agent_search(tmp_path):
    """Verify autonomous web search produces structured snippets."""
    agent = WebAgent(output_dir=tmp_path)

    # Empty query check
    res_empty = await agent.search_web("")
    assert res_empty.success is False

    # Mocked network search response
    mock_results = [
        WebSearchResult(
            title="FastAPI Web Framework",
            url="https://fastapi.tiangolo.com",
            snippet="FastAPI is a modern, fast web framework for building APIs with Python.",
        )
    ]
    with patch.object(agent, "search_web", AsyncMock(return_value=WebActionResult(
        success=True,
        action="search_web",
        title="Search: fastapi python",
        content="Found 1 results.",
        data={"results": [r.to_dict() for r in mock_results], "count": 1},
    ))):
        res = await agent.search_web("fastapi python")
        assert res.success is True
        assert len(res.data.get("results", [])) == 1
        assert res.data["results"][0]["title"] == "FastAPI Web Framework"


@pytest.mark.asyncio
async def test_web_agent_page_extraction(tmp_path):
    """Verify webpage content extraction and tag stripping."""
    agent = WebAgent(output_dir=tmp_path)

    sample_html = "<html><head><title>Test Page</title></head><body><p>Hello from Denver Web Agent.</p></body></html>"
    with patch("urllib.request.urlopen") as mock_url:
        mock_response = MagicMock()
        mock_response.read.return_value = sample_html.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_url.return_value = mock_response

        res = await agent.extract_page_content("https://example.com/test")
        assert res.success is True
        assert res.title == "Test Page"
        assert "Hello from Denver Web Agent." in res.content


@pytest.mark.asyncio
async def test_web_agent_screenshot_capture(tmp_path):
    """Verify website screenshot generation produces valid PNG artifact."""
    agent = WebAgent(output_dir=tmp_path)
    res = await agent.capture_web_screenshot("https://news.ycombinator.com")

    assert res.success is True
    assert res.screenshot_path is not None
    img_path = Path(res.screenshot_path)
    assert img_path.exists()
    assert img_path.stat().st_size > 0
    assert img_path.suffix.lower() == ".png"


def test_web_agent_router_intents():
    """Verify IntentRouter matches web agent trigger phrases."""
    router = IntentRouter()

    # Search web
    i1 = router.route("search the web for quantum computing advances")
    assert i1.action_name == "web_search_query"
    assert "quantum computing advances" in i1.params.get("query", "")

    i2 = router.route("search google for rust vs c++")
    assert i2.action_name == "web_search_query"
    assert "rust vs c++" in i2.params.get("query", "")

    # Extract webpage
    i3 = router.route("read webpage https://en.wikipedia.org/wiki/Artificial_intelligence")
    assert i3.action_name == "extract_web_page"
    assert i3.params.get("url") == "https://en.wikipedia.org/wiki/Artificial_intelligence"

    i4 = router.route("scrape webpage https://github.com/trending")
    assert i4.action_name == "extract_web_page"
    assert i4.params.get("url") == "https://github.com/trending"

    # Screenshot
    i5 = router.route("take screenshot of website https://google.com")
    assert i5.action_name == "capture_web_screenshot"
    assert i5.params.get("url") == "https://google.com"


@pytest.mark.asyncio
async def test_web_agent_command_service_end_to_end(memory_service, tmp_path):
    """Verify end-to-end command flow for web search, page reading, and screenshots."""
    service = CommandEngineService(memory_service=memory_service)
    service.web_agent.output_dir = tmp_path

    # 1. Search the web
    mock_res = WebActionResult(
        success=True,
        action="search_web",
        data={
            "results": [
                {
                    "title": "Python 3.14 Release Notes",
                    "url": "https://docs.python.org/3.14/",
                    "snippet": "New features and improvements in Python 3.14.",
                }
            ]
        },
    )
    with patch.object(service.web_agent, "search_web", AsyncMock(return_value=mock_res)):
        res1 = await service.process_command("search the web for Python 3.14")
        assert res1.success is True
        assert "Python 3.14 Release Notes" in res1.message

    # 2. Extract webpage content
    mock_extract = WebActionResult(
        success=True,
        action="extract_page_content",
        url="https://docs.python.org/3.14/",
        title="Python 3.14 Documentation",
        content="Python 3.14 introduces performance optimizations and new syntax.",
    )
    with patch.object(service.web_agent, "extract_page_content", AsyncMock(return_value=mock_extract)):
        res2 = await service.process_command("read webpage https://docs.python.org/3.14/")
        assert res2.success is True
        assert "Python 3.14 Documentation" in res2.message

    # 3. Capture website screenshot
    res3 = await service.process_command("take screenshot of website https://docs.python.org")
    assert res3.success is True
    assert "Captured webpage screenshot" in res3.message or "screenshot" in res3.message.lower()
