"""
Structured logging module for Voice Agent.
Provides formatted console logging and structured JSON event generation for trace inspection.
Masks secrets and sensitive tokens automatically.
"""
import sys
import time
import json
import logging
from typing import Any, Dict, Optional


def mask_secret(value: Optional[str]) -> str:
    if not value or len(value) <= 6:
        return "******"
    return f"{value[:3]}...{value[-3:]}"


class StructuredLogger:
    def __init__(self, name: str = "VoiceAgent"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def info(self, msg: str, **kwargs):
        self.logger.info(self._format_msg(msg, kwargs))

    def warning(self, msg: str, **kwargs):
        self.logger.warning(self._format_msg(msg, kwargs))

    def error(self, msg: str, **kwargs):
        self.logger.error(self._format_msg(msg, kwargs))

    def debug(self, msg: str, **kwargs):
        self.logger.debug(self._format_msg(msg, kwargs))

    def _format_msg(self, msg: str, extra: Dict[str, Any]) -> str:
        if not extra:
            return msg
        cleaned_extra = {}
        for k, v in extra.items():
            if any(secret_term in k.lower() for secret_term in ["key", "token", "auth", "secret", "password"]):
                cleaned_extra[k] = mask_secret(str(v))
            else:
                cleaned_extra[k] = v
        return f"{msg} | {json.dumps(cleaned_extra, default=str)}"

    def create_trace_event(
        self,
        request_id: str,
        conversation_id: str,
        stage: str,
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None
    ) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "conversation_id": conversation_id,
            "request_id": request_id,
            "stage": stage,
            "duration_ms": duration_ms,
            "data": data or {}
        }


logger = StructuredLogger("VoiceAgent")
