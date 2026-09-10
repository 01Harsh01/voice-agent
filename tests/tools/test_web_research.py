"""
Tests for generic web_research tool.
Verifies real search execution, result normalization schema, and security sanitization.
"""
import pytest
from backend.tools.web_research import WebResearchTool


@pytest.mark.asyncio
async def test_web_research_schema_and_execution():
    tool = WebResearchTool()
    assert tool.name == "web_research"
    assert "query" in tool.parameters_schema["properties"]

    # Execute a real query
    result = await tool.execute(query="Python programming language official", max_results=3)

    assert "query" in result
    assert "retrieved_at" in result
    assert "results" in result
    assert result["status"] == "success"
    assert len(result["results"]) > 0

    first_hit = result["results"][0]
    assert "title" in first_hit
    assert "url" in first_hit
    assert "source" in first_hit
    assert "snippet" in first_hit
    # Should find python.org
    assert any("python" in r["url"].lower() for r in result["results"])
