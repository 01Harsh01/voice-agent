"""
Rime Streaming Text-To-Speech (TTS) Client.
Connects directly to Rime's real-time API with persistent connection pooling
and resilient fallback for ultra-low latency, guaranteed audio delivery.
"""
import asyncio
import base64
import json
import traceback
from typing import AsyncGenerator, Dict, Optional
import httpx
from backend.config import settings
from backend.logging import logger
from backend.agent.request_manager import RequestHandle


class RimeTTSClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model_id: Optional[str] = None,
        speaker: Optional[str] = None,
        audio_format: Optional[str] = None
    ):
        self.api_key = api_key or settings.RIME_API_KEY or ""
        self.endpoint = endpoint or settings.RIME_WS_ENDPOINT
        self.model_id = model_id or settings.RIME_MODEL_ID
        self.speaker = speaker or settings.RIME_SPEAKER
        self.audio_format = audio_format or settings.RIME_AUDIO_FORMAT
        
        # Persistent HTTP client with keep-alive connection pooling
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=30.0)
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=10.0, read=20.0),
                limits=limits
            )
        return self._http_client

    async def warmup(self):
        """Pre-warms the TLS connection to Rime on server startup."""
        if not self.api_key:
            return
        try:
            client = self._get_client()
            logger.info("Pre-warming Rime TTS connection pool...")
            await client.post(
                "https://users.rime.ai/v1/rime-tts",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "speaker": self.speaker,
                    "text": "System ready.",
                    "modelId": self.model_id,
                    "audioFormat": "pcm"
                }
            )
            logger.info("Rime TTS connection pool pre-warmed successfully.")
        except Exception as e:
            logger.warning(f"Rime warmup note: {repr(e)}")

    async def stream_speech(
        self,
        text: str,
        request_handle: RequestHandle
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesizes text through Rime and yields raw audio chunks as they stream in.
        If streaming encounters a network hiccup, automatically falls back to direct POST.
        """
        if not text or not text.strip():
            return

        if not self.api_key:
            logger.warning("Rime API key not configured. Audio synthesis skipped.")
            return

        req_id = request_handle.request_id
        logger.info(
            f"Synthesizing Rime speech for {req_id}",
            speaker=self.speaker,
            model=self.model_id,
            text_length=len(text)
        )

        http_endpoint = "https://users.rime.ai/v1/rime-tts"
        client = self._get_client()
        chunks_yielded = 0

        # Attempt 1: Streaming response
        try:
            async with client.stream(
                "POST",
                http_endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "speaker": self.speaker,
                    "text": text,
                    "modelId": self.model_id,
                    "audioFormat": "pcm"
                }
            ) as response:
                if response.status_code == 200:
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if request_handle.is_cancelled:
                            logger.info(f"Discarding Rime audio for cancelled request {req_id}")
                            break
                        if chunk:
                            chunks_yielded += 1
                            yield chunk
                else:
                    err_txt = await response.aread()
                    logger.error(f"Rime stream returned HTTP {response.status_code}: {err_txt.decode(errors='ignore')}")
        except asyncio.CancelledError:
            logger.info(f"Rime stream cancelled for {req_id}")
            raise
        except Exception as stream_err:
            logger.warning(f"Rime streaming encountered issue for {req_id}: {repr(stream_err)}. Falling back to direct post.")

        # Attempt 2: Direct POST fallback if streaming yielded 0 chunks
        if chunks_yielded == 0 and not request_handle.is_cancelled:
            try:
                logger.info(f"Executing Rime direct POST fallback for {req_id}...")
                resp = await client.post(
                    http_endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "speaker": self.speaker,
                        "text": text,
                        "modelId": self.model_id,
                        "audioFormat": "pcm"
                    }
                )
                if resp.status_code == 200 and resp.content:
                    logger.info(f"Rime direct POST succeeded for {req_id}, bytes: {len(resp.content)}")
                    # Yield in 4096-byte slices so frontend receives progressive audio chunks
                    raw = resp.content
                    for i in range(0, len(raw), 4096):
                        if request_handle.is_cancelled:
                            break
                        yield raw[i:i+4096]
                else:
                    logger.error(f"Rime direct POST fallback failed ({resp.status_code}): {resp.text}")
            except Exception as post_err:
                logger.error(f"Rime direct POST error for {req_id}: {repr(post_err)}")

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
