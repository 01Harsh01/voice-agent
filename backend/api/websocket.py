"""
WebSocket voice session endpoint and connection manager.
Manages bidirectional audio and event streaming, barge-in cancellation,
and real-time debug trace broadcasting.
"""
import asyncio
import base64
import json
import time
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.config import settings
from backend.logging import logger
from backend.agent.agent_loop import AgentLoop
from backend.agent.context import ConversationContext
from backend.agent.request_manager import RequestManager, RequestState
from backend.agent.tool_registry import ToolRegistry
from backend.audio.cancellation import BargeInManager
from backend.audio.streaming import split_into_sentences
from backend.llm.qwen import QwenProvider
from backend.speech.rime import RimeTTSClient
from backend.speech.stt import STTHandler
from backend.tools.datetime import CurrentDateTimeTool
from backend.tools.web_research import WebResearchTool


router = APIRouter()

# Global singletons / registries
tool_registry = ToolRegistry()
tool_registry.register(CurrentDateTimeTool())
tool_registry.register(WebResearchTool())

llm_provider = QwenProvider()
agent_loop = AgentLoop(llm=llm_provider, tool_registry=tool_registry)
request_manager = RequestManager()
barge_in_manager = BargeInManager(request_manager)
stt_handler = STTHandler()
rime_client = RimeTTSClient()

# Active sessions: conversation_id -> ConversationContext
active_conversations: Dict[str, ConversationContext] = {}


@router.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    query_params = websocket.query_params
    conversation_id = query_params.get("conversation_id") or f"convo_{int(time.time()*1000)}"

    if conversation_id not in active_conversations:
        active_conversations[conversation_id] = ConversationContext(conversation_id)

    context = active_conversations[conversation_id]
    logger.info(f"WebSocket connected for conversation: {conversation_id}")

    # Send initial connection acknowledgment
    await websocket.send_json({
        "type": "connection_ready",
        "conversation_id": conversation_id,
        "tools": [t.name for t in tool_registry._tools.values()]
    })

    async def send_event(event_dict: dict):
        try:
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps(event_dict))
        except Exception:
            pass

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            event_type = payload.get("type")

            # 1. Barge-in / user interruption event
            if event_type == "barge_in":
                logger.info(f"Barge-in signal received from client for convo: {conversation_id}")
                barge_in_manager.handle_user_interruption(conversation_id)
                await send_event({
                    "type": "playback_stop",
                    "reason": "barge_in"
                })
                continue

            # 2. Reset / Clear history
            if event_type == "clear_history":
                context.clear()
                await send_event({"type": "history_cleared"})
                continue

            # 3. User speech event
            if event_type == "user_speech":
                raw_user_text = payload.get("text", "")
                user_text = stt_handler.process_transcript(raw_user_text)
                if not user_text:
                    continue

                # Create fresh isolated request handle (this automatically cancels prior active request for this conversation)
                req_handle = request_manager.create_request(conversation_id)
                req_id = req_handle.request_id

                # Notify client that earlier audio must stop for this new turn
                await send_event({
                    "type": "playback_stop",
                    "requestId": req_id
                })

                # Define trace dispatcher
                def trace_cb(stage: str, event_data: Optional[dict] = None, duration_ms: Optional[float] = None, **kwargs):
                    data_payload = event_data or {}
                    dur = duration_ms if duration_ms is not None else data_payload.get("duration_ms")
                    asyncio.create_task(send_event({
                        "type": "trace",
                        "requestId": req_id,
                        "stage": stage,
                        "data": data_payload.get("data", data_payload),
                        "duration_ms": dur,
                        "timestamp": time.time()
                    }))

                # Run processing pipeline as asynchronous task
                async def process_utterance(text: str, handle):
                    try:
                        # 1. LLM Reasoning & Tool Execution Loop
                        final_text = await agent_loop.run(
                            user_text=text,
                            context=context,
                            request_handle=handle,
                            trace_callback=trace_cb
                        )

                        if handle.is_cancelled:
                            logger.info(f"Request {handle.request_id} was cancelled before speech.")
                            return

                        # 2. Dispatch final synthesized text event
                        await send_event({
                            "type": "assistant_text_final",
                            "requestId": handle.request_id,
                            "text": final_text
                        })

                        # 3. Rime Streaming TTS with low-latency connection reuse
                        handle.transition_to(RequestState.SPEAKING)
                        trace_cb("TTS_START", {"text_length": len(final_text)})

                        tts_t0 = time.time()
                        first_audio_sent = False
                        total_chunks_sent = 0

                        await send_event({
                            "type": "assistant_text_chunk",
                            "requestId": handle.request_id,
                            "chunk": final_text
                        })

                        # Stream audio chunks directly from Rime
                        async for audio_bytes in rime_client.stream_speech(final_text, handle):
                            if handle.is_cancelled:
                                break

                            if not first_audio_sent:
                                first_audio_latency = (time.time() - tts_t0) * 1000
                                trace_cb("AUDIO_FIRST_BYTE", {}, duration_ms=first_audio_latency)
                                first_audio_sent = True

                            total_chunks_sent += 1
                            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                            await send_event({
                                "type": "audio_chunk",
                                "requestId": handle.request_id,
                                "audio": b64_audio,
                                "format": "pcm",
                                "sampleRate": 24000
                            })

                        if not handle.is_cancelled:
                            total_tts_dur = (time.time() - tts_t0) * 1000
                            trace_cb("TTS_COMPLETE", {"chunks": total_chunks_sent}, duration_ms=total_tts_dur)
                            await send_event({
                                "type": "audio_done",
                                "requestId": handle.request_id,
                                "chunksSent": total_chunks_sent
                            })
                            request_manager.complete_request(handle.request_id)
                            trace_cb("REQUEST_COMPLETE", {
                                "total_request_time_ms": (time.time() - handle.created_at) * 1000
                            })

                    except asyncio.CancelledError:
                        logger.info(f"Task for request {handle.request_id} cancelled.")
                    except Exception as err:
                        logger.error(f"Error processing request {handle.request_id}: {err}")
                        if not handle.is_cancelled:
                            await send_event({
                                "type": "error",
                                "requestId": handle.request_id,
                                "message": str(err)
                            })

                task = asyncio.create_task(process_utterance(user_text, req_handle))
                req_handle.register_task(task)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for conversation: {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket session exception: {e}")
