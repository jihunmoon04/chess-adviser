import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # Stockfish Settings
    STOCKFISH_PATH: str = "stockfish"
    STOCKFISH_THREADS: int = 2
    STOCKFISH_HASH_MB: int = 128
    STOCKFISH_MULTI_PV: int = 3
    STOCKFISH_FAST_DEPTH: int = 10
    STOCKFISH_FAST_TIMEOUT_MS: int = 40
    STOCKFISH_DEFAULT_DEPTH: int = 18
    STOCKFISH_TIMEOUT_MS: int = 600

    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # 'gemini' or 'openai'
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Cache Settings
    REDIS_URL: Optional[str] = None
    CACHE_TTL_SECONDS: int = 86400  # 24 hours

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
