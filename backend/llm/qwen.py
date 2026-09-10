"""
Qwen LLM Provider implementation using OpenAI-compatible API endpoint (e.g. Hugging Face Router).
Supports Qwen2.5-72B-Instruct with native function/tool calling.
"""
import json
import re
from typing import Any, Dict, List, Optional, Union
import httpx
from backend.config import settings
from backend.logging import logger
from backend.llm.base import BaseLLMProvider, LLMResponse, ToolCall


def clean_voice_text(text: str) -> str:
    """
    Sanitizes LLM output text for voice/TTS consumption.
    Preserves numbers, spoken URLs, units, and names while stripping markdown formatting,
    raw asterisks, bullets, table headers, and emojis.
    """
    if not text:
        return ""

    cleaned = text
    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    # Remove inline backticks
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Remove Markdown headers (# Header)
    cleaned = re.sub(r"^\s*#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    # Remove bold/italic asterisks or underscores (**bold**, *italic*)
    cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)
    # Remove bullet markers (- item, * item)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.MULTILINE)
    # Remove numbered lists prefix (1. item) when it disrupts flow
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Replace common currency symbols with spoken words if needed
    cleaned = cleaned.replace("₹", " rupees ").replace("$", " dollars ").replace("€", " euros ")
    # Strip emojis
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    # Collapse multiple whitespaces/newlines into smooth speech
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


class QwenProvider(BaseLLMProvider):
    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self._model = model_name or settings.LLM_MODEL
        self._base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self._api_key = api_key or settings.effective_llm_api_key
        self._timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return "qwen"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        temperature: float = 0.7,
        max_tokens: int = 500,
        request_id: Optional[str] = None
    ) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        logger.info(
            f"Sending LLM request to {self._model}",
            model=self._model,
            message_count=len(messages),
            has_tools=bool(tools),
            request_id=request_id
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if not response.is_success:
                    err_body = response.text
                    logger.error(f"LLM API returned HTTP {response.status_code}: {err_body}")
                    raise RuntimeError(f"LLM API error ({response.status_code}): {err_body}")

                data = response.json()
                choice = data["choices"][0]
                message = choice.get("message", {})

                # Parse tool calls if present
                raw_tool_calls = message.get("tool_calls")
                parsed_tool_calls = None
                if raw_tool_calls:
                    parsed_tool_calls = []
                    for tc in raw_tool_calls:
                        func = tc.get("function", {})
                        call_id = tc.get("id", f"call_{func.get('name')}")
                        name = func.get("name", "")
                        args = func.get("arguments", "{}")
                        if isinstance(args, dict):
                            args = json.dumps(args)
                        parsed_tool_calls.append(
                            ToolCall(id=call_id, name=name, arguments=args)
                        )

                content = message.get("content")
                if content:
                    content = clean_voice_text(content)

                return LLMResponse(
                    content=content,
                    tool_calls=parsed_tool_calls,
                    finish_reason=choice.get("finish_reason"),
                    raw_response=data
                )

            except Exception as e:
                # If Hugging Face failed (e.g. 402 credits depleted) and Mistral key is available, failover automatically!
                if settings.MISTRAL_API_KEY:
                    logger.warning(f"Primary LLM failed ({e}). Automatically failing over to Mistral ministral-8b-latest.")
                    try:
                        mistral_url = "https://api.mistral.ai/v1/chat/completions"
                        mistral_headers = {
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {settings.MISTRAL_API_KEY}"
                        }
                        mistral_payload = {
                            "model": "ministral-8b-latest",
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens
                        }
                        if tools:
                            mistral_payload["tools"] = tools
                            mistral_payload["tool_choice"] = tool_choice

                        async with httpx.AsyncClient(timeout=self._timeout) as fallback_client:
                            fb_resp = await fallback_client.post(mistral_url, headers=mistral_headers, json=mistral_payload)
                            if fb_resp.is_success:
                                fb_data = fb_resp.json()
                                fb_choice = fb_data["choices"][0]
                                fb_msg = fb_choice.get("message", {})

                                fb_tool_calls = None
                                raw_tcs = fb_msg.get("tool_calls")
                                if raw_tcs:
                                    fb_tool_calls = []
                                    for tc in raw_tcs:
                                        f_dict = tc.get("function", {})
                                        f_args = f_dict.get("arguments", "{}")
                                        if isinstance(f_args, dict):
                                            f_args = json.dumps(f_args)
                                        fb_tool_calls.append(
                                            ToolCall(
                                                id=tc.get("id", f"call_{f_dict.get('name')}"),
                                                name=f_dict.get("name", ""),
                                                arguments=f_args
                                            )
                                        )

                                fb_content = fb_msg.get("content")
                                if fb_content:
                                    fb_content = clean_voice_text(fb_content)

                                logger.info("Failover to Mistral succeeded.")
                                return LLMResponse(
                                    content=fb_content,
                                    tool_calls=fb_tool_calls,
                                    finish_reason=fb_choice.get("finish_reason"),
                                    raw_response=fb_data
                                )
                    except Exception as fb_err:
                        logger.error(f"Failover to Mistral also failed: {fb_err}")

                logger.error(f"LLM invocation failed: {e}")
                raise
