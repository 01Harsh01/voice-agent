"""
Tests for runtime current_datetime tool.
Ensures tool returns accurate system clock and timezone data dynamically.
"""
import pytest
from datetime import datetime
from backend.tools.datetime import CurrentDateTimeTool


@pytest.mark.asyncio
async def test_current_datetime_returns_runtime_data():
    tool = CurrentDateTimeTool()
    result = await tool.execute()

    assert "iso" in result
    assert "date" in result
    assert "formatted_date" in result
    assert "time" in result
    assert "day_of_week" in result
    assert "timezone" in result

    # Check date matches current year
    current_year = str(datetime.now().year)
    assert result["date"].startswith(current_year)


@pytest.mark.asyncio
async def test_current_datetime_supports_timezone():
    tool = CurrentDateTimeTool()
    result = await tool.execute(timezone="Asia/Kolkata")

    assert result["timezone"] == "Asia/Kolkata"
    assert "utc_iso" in result
