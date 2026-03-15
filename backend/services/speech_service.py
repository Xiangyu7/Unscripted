from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from config import Config


# ── Game-specific ASR post-processing ──────────────────────────────
# Chinese ASR often misrecognizes proper nouns (character names, locations).
# This maps common misrecognitions to correct game terms.

_NAME_CORRECTIONS = {
    # 林岚 (lín lán) — common misrecognitions
    "林蓝": "林岚", "琳岚": "林岚", "临岚": "林岚", "林兰": "林岚",
    "琳蓝": "林岚", "林澜": "林岚", "淋岚": "林岚", "琳兰": "林岚",
    "凛岚": "林岚", "林览": "林岚",
    # 周牧 (zhōu mù)
    "周目": "周牧", "周木": "周牧", "周幕": "周牧", "周慕": "周牧",
    "洲牧": "周牧", "周暮": "周牧", "周沐": "周牧", "粥木": "周牧",
    # 宋知微 (sòng zhī wēi)
    "宋之微": "宋知微", "宋志微": "宋知微", "宋芝微": "宋知微",
    "宋知威": "宋知微", "宋知薇": "宋知微", "宋之伟": "宋知微",
    "宋之为": "宋知微", "宋志伟": "宋知微", "送知微": "宋知微",
    "宋枝微": "宋知微", "宋至微": "宋知微",
    # 顾言 (gù yán)
    "顾严": "顾言", "顾研": "顾言", "古言": "顾言", "故言": "顾言",
    "顾颜": "顾言", "顾岩": "顾言", "固言": "顾言",
    # 场景名
    "宴会厅": "宴会厅",  # Already correct, but ensure normalization
    "酒窖": "酒窖", "酒窑": "酒窖", "酒要": "酒窖",
    "书房": "书房", "疏房": "书房",
    # 关键词
    "遗嘱": "遗嘱", "遗住": "遗嘱", "一嘱": "遗嘱",
    "密室": "密室", "秘室": "密室",
}


def _correct_game_names(text: str) -> str:
    """Replace common ASR misrecognitions with correct game terms.

    Two-pass strategy:
      1. Exact match from known correction table (fast)
      2. Pinyin fuzzy match for unknown misrecognitions (catches everything)
    """
    # Pass 1: exact match (fast path)
    for wrong, correct in _NAME_CORRECTIONS.items():
        if wrong in text:
            text = text.replace(wrong, correct)

    # Pass 2: pinyin fuzzy match (catches novel misrecognitions)
    text = _fuzzy_correct_names(text)
    return text


# ── Pinyin-based fuzzy name correction ─────────────────────────────

try:
    from pypinyin import lazy_pinyin, Style
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False

# Game terms with their pinyin (without tones for fuzzy matching)
_GAME_TERMS = {
    "林岚": None,    # pinyin computed lazily
    "周牧": None,
    "宋知微": None,
    "顾言": None,
    "酒窖": None,
    "书房": None,
    "宴会厅": None,
    "遗嘱": None,
    "密室": None,
}


def _get_pinyin(text: str) -> str:
    """Get space-joined pinyin without tones."""
    if not _HAS_PYPINYIN:
        return ""
    return " ".join(lazy_pinyin(text, style=Style.NORMAL))


def _init_term_pinyin():
    """Lazily compute pinyin for all game terms."""
    for term in _GAME_TERMS:
        if _GAME_TERMS[term] is None:
            _GAME_TERMS[term] = _get_pinyin(term)


def _fuzzy_correct_names(text: str) -> str:
    """Scan text for character sequences whose pinyin matches a game term."""
    if not _HAS_PYPINYIN:
        return text

    _init_term_pinyin()

    result = text
    for term, term_pinyin in _GAME_TERMS.items():
        if not term_pinyin or term in result:
            continue  # Already correct or no pinyin available

        term_len = len(term)
        # Slide a window of same character length over the text
        i = 0
        while i <= len(result) - term_len:
            window = result[i:i + term_len]
            # Skip if window is already the correct term
            if window == term:
                i += 1
                continue
            window_pinyin = _get_pinyin(window)
            if window_pinyin == term_pinyin and window != term:
                # Pinyin matches but characters differ → replace
                result = result[:i] + term + result[i + term_len:]
            i += 1

    return result


def _trim_trailing_slash(url: str) -> str:
    return url[:-1] if url.endswith("/") else url


def _mime_type_for_format(response_format: str) -> str:
    fmt = response_format.lower()
    if fmt == "wav":
        return "audio/wav"
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt == "pcm":
        return "audio/pcm"
    return "application/octet-stream"


class SpeechServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        provider: str = "unknown",
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        self.code = code


@dataclass
class ProviderStatus:
    provider: str
    model: Optional[str]
    available: bool
    detail: str = ""
    fallback: Optional[str] = None


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    usage: Optional[Dict[str, Any]] = None


@dataclass
class SynthesisResult:
    audio_base64: str
    mime_type: str
    provider: str
    model: str
    voice: str
    latency_ms: int


class SpeechToTextProvider:
    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> TranscriptionResult:
        raise NotImplementedError

    def get_status(self) -> ProviderStatus:
        raise NotImplementedError


class TextToSpeechProvider:
    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: Optional[float] = None,
        response_format: str,
    ) -> SynthesisResult:
        raise NotImplementedError

    def get_status(self) -> ProviderStatus:
        raise NotImplementedError


class DisabledSpeechToTextProvider(SpeechToTextProvider):
    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider="disabled",
            model=None,
            available=False,
            detail="ASR provider is disabled.",
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> TranscriptionResult:
        raise SpeechServiceError(
            "ASR provider is disabled.",
            status_code=503,
            provider="disabled",
            code="asr_disabled",
        )


class DisabledTextToSpeechProvider(TextToSpeechProvider):
    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider="disabled",
            model=None,
            available=False,
            detail="TTS provider is disabled; browser speech fallback is recommended.",
            fallback="browser",
        )

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: Optional[float] = None,
        response_format: str,
    ) -> SynthesisResult:
        raise SpeechServiceError(
            "TTS provider is disabled.",
            status_code=503,
            provider="disabled",
            code="tts_disabled",
        )


class GLMASpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: float) -> None:
        self.provider = "glm"
        self.api_key = api_key
        self.base_url = _trim_trailing_slash(base_url)
        self.model = model
        self.timeout_seconds = timeout_seconds

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider,
            model=self.model,
            available=bool(self.api_key),
            detail="Configured for multipart upload transcription.",
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> TranscriptionResult:
        if not audio_bytes:
            raise SpeechServiceError(
                "Uploaded audio file is empty.",
                status_code=400,
                provider=self.provider,
                code="empty_audio",
            )

        headers = {"Authorization": f"Bearer {self.api_key}"}
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                data={"model": self.model},
                files={"file": (filename, audio_bytes, content_type)},
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = _json_or_none(response)
        if response.status_code >= 400:
            raise SpeechServiceError(
                _error_message(payload, response),
                status_code=502,
                provider=self.provider,
                code=_error_code(payload),
            )

        transcript = (payload or {}).get("text", "").strip()
        if not transcript:
            raise SpeechServiceError(
                "ASR returned an empty transcript.",
                status_code=502,
                provider=self.provider,
                code="empty_transcript",
            )

        return TranscriptionResult(
            text=transcript,
            provider=self.provider,
            model=self.model,
            latency_ms=latency_ms,
            usage=(payload or {}).get("usage"),
        )


class GLMTextToSpeechProvider(TextToSpeechProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        default_voice: str,
        timeout_seconds: float,
    ) -> None:
        self.provider = "glm"
        self.api_key = api_key
        self.base_url = _trim_trailing_slash(base_url)
        self.model = model
        self.default_voice = default_voice
        self.timeout_seconds = timeout_seconds

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider,
            model=self.model,
            available=bool(self.api_key),
            detail="Configured for synthesized audio output.",
            fallback="browser",
        )

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: Optional[float] = None,
        response_format: str,
    ) -> SynthesisResult:
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or self.default_voice,
            "speed": max(0.5, min(2.0, speed or 1.0)),
            "volume": 1.0,
            "response_format": response_format,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers=headers,
                json=payload,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)

        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "application/json" in content_type:
            payload_json = _json_or_none(response)
            raise SpeechServiceError(
                _error_message(payload_json, response),
                status_code=502,
                provider=self.provider,
                code=_error_code(payload_json),
            )

        return SynthesisResult(
            audio_base64=base64.b64encode(response.content).decode("ascii"),
            mime_type=_mime_type_for_format(response_format),
            provider=self.provider,
            model=self.model,
            voice=voice or self.default_voice,
            latency_ms=latency_ms,
        )


def _json_or_none(response: httpx.Response) -> Optional[Dict[str, Any]]:
    try:
        return response.json()
    except json.JSONDecodeError:
        return None


def _error_message(payload: Optional[Dict[str, Any]], response: httpx.Response) -> str:
    if payload and isinstance(payload.get("error"), dict):
        return payload["error"].get("message", response.text)
    return response.text or f"HTTP {response.status_code}"


def _error_code(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if payload and isinstance(payload.get("error"), dict):
        code = payload["error"].get("code")
        return str(code) if code is not None else None
    return None


class SpeechService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.asr = self._build_asr_provider()
        self.tts = self._build_tts_provider()

    def _build_asr_provider(self) -> SpeechToTextProvider:
        if self.config.asr_provider == "glm" and self.config.asr_api_key:
            return GLMASpeechToTextProvider(
                api_key=self.config.asr_api_key,
                base_url=self.config.asr_base_url,
                model=self.config.asr_model,
                timeout_seconds=self.config.voice_timeout_seconds,
            )
        return DisabledSpeechToTextProvider()

    def _build_tts_provider(self) -> TextToSpeechProvider:
        if self.config.tts_provider == "glm" and self.config.tts_api_key:
            return GLMTextToSpeechProvider(
                api_key=self.config.tts_api_key,
                base_url=self.config.tts_base_url,
                model=self.config.tts_model,
                default_voice=self.config.tts_default_voice,
                timeout_seconds=self.config.voice_timeout_seconds,
            )
        return DisabledTextToSpeechProvider()

    def get_status(self) -> Dict[str, ProviderStatus]:
        return {
            "asr": self.asr.get_status(),
            "tts": self.tts.get_status(),
        }

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str,
        content_type: str,
        session_id: Optional[str] = None,
    ) -> TranscriptionResult:
        result = await self.asr.transcribe(
            audio_bytes,
            filename=filename,
            content_type=content_type,
        )
        # Post-process: correct game-specific proper nouns
        result.text = _correct_game_names(result.text)
        self._log_span(
            "voice_transcribe",
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            ok=True,
            session_id=session_id,
            transcript_chars=len(result.text),
        )
        return result

    async def synthesize_text(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SynthesisResult:
        chosen_voice = voice or self.config.tts_default_voice
        fmt = response_format or self.config.tts_response_format
        result = await self.tts.synthesize(
            text,
            voice=chosen_voice,
            speed=speed,
            response_format=fmt,
        )
        self._log_span(
            "voice_synthesize",
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            ok=True,
            session_id=session_id,
            text_chars=len(text),
            voice=result.voice,
        )
        return result

    def _log_span(self, event: str, **payload: Any) -> None:
        data = {"event": event, **payload}
        print(f"[Voice] {json.dumps(data, ensure_ascii=False)}")
