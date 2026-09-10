"""
Main FastAPI server application.
Serves WebSocket endpoints, health checks, metrics, and the frontend web UI.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.logging import logger
import asyncio
from backend.api.websocket import router as ws_router, rime_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Voice Agent Backend on {settings.HOST}:{settings.PORT}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER} | Model: {settings.LLM_MODEL}")
    logger.info(f"Rime Endpoint: {settings.RIME_WS_ENDPOINT} | Speaker: {settings.RIME_SPEAKER}")
    # Pre-warm TLS connection to Rime TTS in background so first request is warm
    asyncio.create_task(rime_client.warmup())
    yield
    await rime_client.close()
    logger.info("Voice Agent Backend shutting down.")


app = FastAPI(
    title="Real-Time AI Voice Agent",
    version="1.0.0",
    description="Real-time voice agent with Qwen reasoning, live web tools, and streaming Rime TTS",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount WebSocket router
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "llm_model": settings.LLM_MODEL,
        "tts_speaker": settings.RIME_SPEAKER,
        "search_provider": settings.WEB_SEARCH_PROVIDER
    }


# Mount Frontend static files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
