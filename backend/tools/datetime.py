"""
Runtime current date and time capability.
Provides accurate real-time clock and calendar data without relying on model internal knowledge.
"""
from datetime import datetime, timezone
import zoneinfo
from typing import Any, Dict, Optional
from backend.agent.tool_registry import BaseTool


class CurrentDateTimeTool(BaseTool):
    @property
    def name(self) -> str:
        return "current_datetime"

    @property
    def description(self) -> str:
        return (
            "Returns the current date, time, day of the week, and timezone. "
            "Always call this tool when the user asks about today, tomorrow, yesterday, "
            "dates, current time, or relative calendar days."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Optional IANA timezone name (e.g. 'Asia/Kolkata', 'America/New_York', 'UTC'). Defaults to local system timezone."
                }
            },
            "required": []
        }

    async def execute(self, timezone_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        # Handle param naming flexibility (timezone or timezone_name)
        tz_str = timezone_name or kwargs.get("timezone")

        if tz_str:
            try:
                tz = zoneinfo.ZoneInfo(tz_str)
                now = datetime.now(tz)
                active_tz = tz_str
            except Exception:
                now = datetime.now().astimezone()
                active_tz = str(now.tzinfo)
        else:
            now = datetime.now().astimezone()
            active_tz = str(now.tzinfo)

        utc_now = datetime.now(timezone.utc)

        return {
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "formatted_date": now.strftime("%A, %B %d, %Y"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "timezone": active_tz,
            "utc_iso": utc_now.isoformat()
        }
