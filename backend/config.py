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

        self.modelscope_api_key = os.getenv("MODELSCOPE_API_KEY")

        # Speech stack: keep text, ASR, and TTS independently configurable so
        # one provider outage or quota issue does not take down the full turn.
        self.asr_provider = os.getenv(
            "ASR_PROVIDER",
            "glm" if (os.getenv("ASR_API_KEY") or self.api_key) else "disabled",
        )
        self.asr_api_key = os.getenv("ASR_API_KEY") or self.api_key
        self.asr_base_url = os.getenv("ASR_BASE_URL") or self.base_url
        self.asr_model = os.getenv("ASR_MODEL", "glm-asr-2512")

        self.tts_provider = os.getenv("TTS_PROVIDER", "disabled")
        self.tts_api_key = os.getenv("TTS_API_KEY") or self.api_key
        self.tts_base_url = os.getenv("TTS_BASE_URL") or self.base_url
        self.tts_model = os.getenv("TTS_MODEL", "glm-tts")
        self.tts_default_voice = os.getenv("TTS_DEFAULT_VOICE", "tongtong")
        self.tts_response_format = os.getenv("TTS_RESPONSE_FORMAT", "wav")

        self.voice_timeout_seconds = float(os.getenv("VOICE_TIMEOUT_SECONDS", "30"))

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))

    def __repr__(self) -> str:
        return (
            f"Config(provider={self.provider.value}, "
            f"model={self.model}, "
            f"base_url={self.base_url}, "
            f"host={self.host}, port={self.port})"
        )
