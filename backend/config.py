"""
Configuration module using Pydantic Settings.
Loads environment variables cleanly with type validation and defaults.
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # LLM Settings
    LLM_PROVIDER: str = "huggingface"
    LLM_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"
    LLM_BASE_URL: str = "https://router.huggingface.co/v1"
    HF_TOKEN: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None

    # Rime TTS Settings
    RIME_API_KEY: Optional[str] = None
    RIME_WS_ENDPOINT: str = "wss://users-ws.rime.ai/ws3"
    RIME_MODEL_ID: str = "coda"
    RIME_SPEAKER: str = "astra"
    RIME_AUDIO_FORMAT: str = "mp3"
    RIME_SAMPLING_RATE: int = 24000

    # Web Search Provider Settings
    WEB_SEARCH_PROVIDER: str = "duckduckgo"
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None

    # Timeouts and Limits
    MAX_TOOL_ITERATIONS: int = 5
    REQUEST_TIMEOUT_SECONDS: float = 30.0
    LLM_TIMEOUT_SECONDS: float = 20.0
    WEB_TIMEOUT_SECONDS: float = 10.0
    RIME_TIMEOUT_SECONDS: float = 15.0

    @property
    def effective_llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.HF_TOKEN or ""


settings = Settings()
