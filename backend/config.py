import os
from enum import Enum


class LLMProvider(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    FALLBACK = "fallback"


class Config:
    """Application configuration - supports any OpenAI-compatible API (MiniMax, DeepSeek, etc.)."""

    def __init__(self):
        # Priority: LLM_API_KEY > OPENAI_API_KEY > ANTHROPIC_API_KEY > fallback
        self.api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.minimax.chat/v1")
        self.model = os.getenv("LLM_MODEL", "MiniMax-Text-01")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        if self.api_key:
            self.provider = LLMProvider.OPENAI_COMPATIBLE
        elif self.anthropic_key:
            self.provider = LLMProvider.ANTHROPIC
            self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        else:
            self.provider = LLMProvider.FALLBACK
            self.model = None

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))

    def __repr__(self) -> str:
        return (
            f"Config(provider={self.provider.value}, "
            f"model={self.model}, "
            f"base_url={self.base_url}, "
            f"host={self.host}, port={self.port})"
        )
