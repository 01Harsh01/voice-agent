"""
Integration and Compliance Tests.
Verifies API health endpoints, anti-contamination guarantees,
and performs an automated audit for the PRD strict Zero Mock Data Policy.
"""
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.agent.context import ConversationContext


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "llm_model" in data
        assert "tts_speaker" in data


def test_no_fake_data_files_exist():
    """
    PRD Section 14 & 15: Zero Mock Data Policy.
    Ensures no predefined answer files or mock datasets exist in the project repository.
    """
    root_dir = Path(__file__).resolve().parent.parent.parent
    forbidden_filenames = [
        "answers.txt",
        "answers.json",
        "mock_data.json",
        "fake_news.json",
        "weather_data.json",
        "knowledge.txt",
        "preloaded_answers.json",
        "demo_data.json",
        "responses.json"
    ]

    for forbidden in forbidden_filenames:
        matches = list(root_dir.rglob(forbidden))
        assert len(matches) == 0, f"Violation of Zero Mock Data Policy: Found forbidden file {matches}"


def test_anti_contamination_state_isolation():
    """
    PRD Section 20: Anti-Contamination.
    Verifies that turn 1 content is isolated and does not become default answer for turn 2.
    """
    convo = ConversationContext("test_anti_contamination")
    convo.add_user_turn("What date will it be two days from today?", request_id="req_001")
    convo.add_assistant_turn("In two days it will be Thursday, September 10, 2026.", request_id="req_001")

    # Second turn
    convo.add_user_turn("What major event happened today?", request_id="req_002")

    messages = convo.to_messages(system_prompt="System Prompt")

    # Verify messages preserve accurate history, but the last message is purely the new user query
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "What major event happened today?"
    assert len(messages) == 4  # System + User1 + Assistant1 + User2
