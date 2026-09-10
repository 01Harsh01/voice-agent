# Real-Time AI Voice Agent (VoiceFlow)

A production-grade conversational AI voice assistant powered by **Qwen2.5-72B-Instruct**, generic real-world tools (**`web_research`**, **`current_datetime`**), and streaming **Rime TTS** over WebSockets.

Designed and implemented in accordance with **PRD & TRD v1.0**.

---

## 🏛️ Core Design Principles

1. **Qwen Decides:** Understanding conversational context, deciding if external information is needed, generating structured tool calls, and synthesizing the final answer.
2. **Generic Tools Act:** Accessing the real world, retrieving current live web data, and returning normalized results with **zero mock data, zero answer files, zero fake weather/news**.
3. **Rime Speaks:** Converting streaming text into low-latency audio via Rime's persistent WebSocket endpoint (`/ws3`).
4. **Strict Barge-In & Request Isolation:** When the user speaks, prior tasks are immediately cancelled, pending audio chunks are discarded, and stale callbacks are rejected.
5. **No Context Contamination:** Every turn executes a fresh reasoning cycle.

---

## 📁 Architecture & Project Structure

```text
voice-agent/
│
├── backend/
│   ├── main.py                    # FastAPI server entrypoint & static frontend mount
│   ├── config.py                  # Pydantic Settings configuration
│   ├── logging.py                 # Structured logger with secret masking & latency tracking
│   ├── security.py                # Untrusted web data sanitizer & prompt injection guard
│   │
│   ├── api/
│   │   └── websocket.py           # Real-time WebSocket gateway (/ws/voice)
│   │
│   ├── agent/
│   │   ├── agent_loop.py          # Iterative tool calling loop (max 5 iterations)
│   │   ├── context.py             # Conversation history & anti-contamination state
│   │   ├── request_manager.py     # Request lifecycle & cancellation management
│   │   └── tool_registry.py       # Generic Tool Registry (OpenAI JSON Schema)
│   │
│   ├── llm/
│   │   ├── base.py                # BaseLLMProvider interface
│   │   └── qwen.py                # Qwen2.5-72B OpenAI-compatible client
│   │
│   ├── tools/
│   │   ├── web_research.py        # Real DuckDuckGo / Tavily live search & page extraction
│   │   └── datetime.py            # Runtime system clock and timezone capability
│   │
│   ├── speech/
│   │   ├── stt.py                 # Speech-to-Text transcript processor
│   │   └── rime.py                # Rime WebSocket (/ws3) streaming TTS client
│   │
│   └── audio/
│       ├── streaming.py           # Low-latency sentence segmenter
│       └── cancellation.py        # Instantaneous barge-in manager
│
├── frontend/                      # Modern Voice UI
│   ├── index.html                 # Semantic HTML5 with accessible controls
│   ├── style.css                  # Dark glassmorphic design, glowing voice orb, responsive layout
│   └── app.js                     # Web Audio API streaming player, STT & Live Debug Trace drawer
│
├── tests/                         # Comprehensive Pytest Suite
│   ├── agent/                     # Agent loop, multi-turn context & anti-contamination
│   ├── tools/                     # Web research & runtime datetime
│   ├── voice/                     # Streaming sentence segmentation & voice formatting
│   ├── interruption/              # Barge-in cancellation & request isolation
│   └── integration/               # Health check & Zero Mock Data Policy compliance
│
├── Dockerfile                     # Production container image
├── docker-compose.yml             # Local orchestrated runtime
├── requirements.txt               # Dependencies
├── .env.example                   # Environment configuration template
└── README.md
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.13+ or Docker
- A Hugging Face / OpenAI-compatible API key for Qwen
- A Rime AI API key for streaming TTS

### 2. Setup Virtual Environment
```bash
# Create venv
uv venv --python 3.13 .venv

# Activate venv (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and provide your credentials:
```bash
cp .env.example .env
```

```ini
LLM_PROVIDER=huggingface
LLM_MODEL=Qwen/Qwen2.5-72B-Instruct
LLM_BASE_URL=https://router.huggingface.co/v1
HF_TOKEN=your_huggingface_token
RIME_API_KEY=your_rime_api_key
RIME_MODEL_ID=coda
RIME_SPEAKER=astra
```

### 4. Run Locally
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser to: **`http://localhost:8000`**

---

## 🧪 Running the Test Suite

Execute the comprehensive test suite to verify all PRD requirements:
```bash
pytest -v
```

Tests cover:
- **`tests/tools/test_datetime.py`**: Dynamic runtime date/time lookup.
- **`tests/tools/test_web_research.py`**: Live web research, result schema normalization, and zero mock data.
- **`tests/voice/test_streaming.py`**: Punctuation-based sentence splitting protecting abbreviations and decimals.
- **`tests/interruption/test_cancellation.py`**: Request isolation, task cancellation, and stale-result rejection.
- **`tests/agent/test_agent_loop.py`**: Direct knowledge synthesis vs. iterative tool calling.
- **`tests/integration/test_pipeline.py`**: Health endpoint and automated codebase scan confirming zero forbidden mock files.

---

## 🐳 Docker Deployment

```bash
docker compose up -d --build
```
Check health:
```bash
curl http://localhost:8000/health
```
