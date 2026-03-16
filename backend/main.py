import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load .env before config is initialized
load_dotenv()

from config import Config
from engine.turn_engine import TurnEngine, sessions
from schemas.game_state import (
    SpeechSynthesisRequest,
    SpeechSynthesisResponse,
    TurnRequest,
    TurnResponse,
    VoiceProviderState,
    VoiceStatusResponse,
    VoiceTranscriptionResponse,
    VoiceTurnResponse,
    redact_game_state,
)
from services.speech_service import SpeechService, SpeechServiceError
from stories.gu_family_case import create_initial_state
from stories.case_builder import CaseBuilder
from stories.generator import StoryGenerator
from stories.templates import select_template
from stories.validator import StoryValidator

# Initialize config and engine
config = Config()
engine = TurnEngine(config)
speech_service = SpeechService(config)
story_generator = StoryGenerator(config)
story_validator = StoryValidator()
case_builder = CaseBuilder()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    print("=" * 60)
    print("  Unscripted (非剧本杀) - Backend Server")
    print("=" * 60)
    print(f"  LLM Provider : {config.provider.value.upper()}")
    if config.model:
        print(f"  Model        : {config.model}")
    if config.base_url:
        print(f"  Base URL     : {config.base_url}")
    print(f"  Host         : {config.host}")
    print(f"  Port         : {config.port}")
    print("=" * 60)
    if config.provider.value == "fallback":
        print("  [!] Running in FALLBACK mode (rule-based, no LLM).")
        print("      Set LLM_API_KEY + LLM_BASE_URL for LLM mode.")
    print()
    yield
    print("Shutting down Unscripted backend...")


app = FastAPI(
    title="Unscripted API",
    description="Multi-agent interactive narrative game backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response models for endpoints ───────────────────────────


class ResetRequest(BaseModel):
    session_id: Optional[str] = None
    story_id: str = "gu_family_case"


class ResetResponse(BaseModel):
    session_id: str
    message: str
    game_state: dict


class GenerateCaseRequest(BaseModel):
    theme: str
    template_id: Optional[str] = None


class GenerateCaseResponse(BaseModel):
    session_id: str
    title: str
    message: str


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: Optional[str]
    active_sessions: int


def _raise_speech_http_error(err: SpeechServiceError) -> None:
    raise HTTPException(
        status_code=err.status_code,
        detail={
            "message": str(err),
            "provider": err.provider,
            "code": err.code,
        },
    )


# ─── Endpoints ────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        provider=config.provider.value,
        model=config.model,
        active_sessions=len(sessions),
    )


@app.get("/api/portraits")
async def get_portraits():
    """Generate or retrieve cached character portraits (default mood: calm)."""
    if not engine.image_agent:
        return {"portraits": {}}
    portraits = await engine.image_agent.generate_all_portraits()
    return {"portraits": portraits}


@app.get("/api/portraits/all-moods")
async def get_all_mood_portraits():
    """Pre-generate all mood variants for all characters.

    Returns {char_id: {mood: url}}. Call at game start to pre-cache.
    """
    if not engine.image_agent:
        return {"portraits": {}}
    variants = await engine.image_agent.generate_all_mood_variants()
    return {"portraits": variants}


@app.get("/api/portrait/{character_id}")
async def get_portrait(character_id: str, mood: str = "calm"):
    """Generate or retrieve a character portrait for a specific mood."""
    if not engine.image_agent:
        raise HTTPException(status_code=503, detail="Image service not configured")
    url = await engine.image_agent.generate_character_portrait(character_id, mood)
    if not url:
        raise HTTPException(status_code=404, detail=f"No portrait for '{character_id}'")
    return {"character_id": character_id, "mood": mood, "portrait_url": url}


@app.post("/api/reset", response_model=ResetResponse)
async def reset_session(req: ResetRequest = ResetRequest()):
    """Create or reset a game session."""
    sid = req.session_id or str(uuid.uuid4())

    if req.story_id == "gu_family_case":
        state = create_initial_state(sid)
    elif req.story_id in sessions and sessions[req.story_id].story_id.startswith("generated_"):
        # Allow resetting a generated case by passing its session_id as story_id
        state = sessions[req.story_id].model_copy(update={"session_id": sid, "round": 0, "tension": 20, "game_over": False, "ending": None})
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown story_id: '{req.story_id}'. Available: ['gu_family_case'] or use /api/generate-case.",
        )

    sessions[sid] = state
    engine.init_world(sid)
    return ResetResponse(
        session_id=sid,
        message="Session created successfully.",
        game_state=redact_game_state(state),
    )


@app.post("/api/generate-case", response_model=GenerateCaseResponse)
async def generate_case(req: GenerateCaseRequest):
    """Generate a new case from a user theme using template + LLM."""
    if config.provider.value == "fallback":
        raise HTTPException(
            status_code=503,
            detail="Story generation requires an LLM provider. Set LLM_API_KEY.",
        )

    # Select template
    if req.template_id:
        from stories.templates import TEMPLATE_REGISTRY

        template = TEMPLATE_REGISTRY.get(req.template_id)
        if not template:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown template_id: '{req.template_id}'. "
                f"Available: {list(TEMPLATE_REGISTRY.keys())}",
            )
    else:
        template = select_template(req.theme)

    # Generate with retry
    last_errors = []
    for attempt in range(2):
        try:
            filled = await story_generator.generate(template, req.theme)
        except Exception as e:
            last_errors.append(f"LLM call failed: {e}")
            continue

        errors = story_validator.validate(template, filled)
        if not errors:
            break
        last_errors = errors
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Story generation failed after 2 attempts: {last_errors}",
        )

    # Build GameState
    sid = str(uuid.uuid4())
    state = case_builder.build(template, filled, session_id=sid)
    sessions[sid] = state
    engine.init_world(sid)

    return GenerateCaseResponse(
        session_id=sid,
        title=state.title,
        message="Case generated successfully.",
    )


@app.get("/api/notebook/{session_id}")
async def get_notebook(session_id: str):
    """Get the player's investigation notebook for a session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {
        "entries": engine.notebook.get_notebook(session_id),
        "contradictions": engine.notebook.get_contradictions(session_id),
        "summary": engine.notebook.get_summary(session_id),
    }


@app.get("/api/state/{session_id}")
async def get_state(session_id: str):
    """Get the current game state for a session."""
    state = sessions.get(session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )
    return redact_game_state(state)


@app.get("/api/report/{session_id}")
async def get_report(session_id: str):
    """Get the case report for a completed game session."""
    state = sessions.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    discovered_clues = [
        {"id": c.id, "text": c.text, "location": c.location}
        for c in state.clues if c.discovered
    ]
    key_events = [
        {"round": e.round, "type": e.type, "text": e.text}
        for e in state.events
        if e.type in ("lie_caught", "twist", "proactive", "accuse", "confrontation")
    ]
    return {
        "session_id": session_id,
        "title": state.title,
        "game_over": state.game_over,
        "ending": state.ending,
        "round": state.round,
        "max_rounds": state.max_rounds,
        "tension": state.tension,
        "discovered_clues": discovered_clues,
        "total_clues": len(state.clues),
        "key_events": key_events,
        "characters": [
            {"id": c.id, "name": c.name, "trust": c.trust_to_player, "suspicion": c.suspicion}
            for c in state.characters
        ],
    }


@app.post("/api/undo/{session_id}")
async def undo_turn(session_id: str):
    """Undo the last turn, restoring all game state including NPC memory."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if not engine.has_undo(session_id):
        raise HTTPException(status_code=400, detail="Nothing to undo.")
    engine.undo_last_turn(session_id)
    state = sessions[session_id]
    return {
        "success": True,
        "round": state.round,
        "game_state": redact_game_state(state),
    }


@app.post("/api/turn", response_model=TurnResponse)
async def process_turn(req: TurnRequest):
    """Process a player's turn action."""
    if not req.player_action.strip():
        raise HTTPException(
            status_code=400,
            detail="player_action cannot be empty.",
        )

    try:
        result = await engine.process_turn(req.session_id, req.player_action)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Turn processing failed: {e}", file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing turn: {str(e)}",
        )


@app.post("/api/turn/stream")
async def process_turn_stream(req: TurnRequest):
    """Process a turn and stream results via SSE — events arrive as they're ready."""
    if not req.player_action.strip():
        raise HTTPException(status_code=400, detail="player_action cannot be empty.")

    # Large padding to force Render's reverse proxy to flush SSE immediately.
    # Render buffers ~16KB before sending the first byte to the client.
    _FLUSH_PAD = f": {' ' * 4096}\n\n"

    async def event_stream():
        # Send 4 chunks of 4KB padding (~16KB total) to bust the proxy buffer
        for _ in range(4):
            yield _FLUSH_PAD
        try:
            async for event in engine.process_turn_streaming(
                req.session_id, req.player_action
            ):
                payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield payload
                # Extra padding after each event to keep flushing
                yield _FLUSH_PAD
        except Exception as e:
            print(f"[ERROR] Stream turn failed: {e}", file=sys.stderr)
            yield f"data: {json.dumps({'type': 'error', 'text': f'Internal error: {str(e)}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
            "Transfer-Encoding": "chunked",
        },
    )


@app.get("/api/voice/status", response_model=VoiceStatusResponse)
async def get_voice_status():
    status = speech_service.get_status()
    return VoiceStatusResponse(
        asr=VoiceProviderState(**status["asr"].__dict__),
        tts=VoiceProviderState(**status["tts"].__dict__),
    )


@app.post("/api/voice/transcribe", response_model=VoiceTranscriptionResponse)
async def transcribe_audio(audio: UploadFile = File(...)):
    payload = await audio.read()
    try:
        result = await speech_service.transcribe_audio(
            payload,
            filename=audio.filename or "voice-input.wav",
            content_type=audio.content_type or "audio/wav",
        )
    except SpeechServiceError as err:
        _raise_speech_http_error(err)

    return VoiceTranscriptionResponse(
        transcript=result.text,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        usage=result.usage,
    )


@app.post("/api/voice/turn", response_model=VoiceTurnResponse)
async def process_voice_turn(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    payload = await audio.read()
    try:
        transcription = await speech_service.transcribe_audio(
            payload,
            filename=audio.filename or "voice-turn.wav",
            content_type=audio.content_type or "audio/wav",
            session_id=session_id,
        )
        turn_result = await engine.process_turn(session_id, transcription.text)
    except SpeechServiceError as err:
        _raise_speech_http_error(err)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except Exception as err:
        print(f"[ERROR] Voice turn failed: {err}", file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing voice turn: {str(err)}",
        )

    return VoiceTurnResponse(
        transcript=transcription.text,
        asr=VoiceTranscriptionResponse(
            transcript=transcription.text,
            provider=transcription.provider,
            model=transcription.model,
            latency_ms=transcription.latency_ms,
            usage=transcription.usage,
        ),
        turn=turn_result,
    )


@app.post("/api/voice/speak", response_model=SpeechSynthesisResponse)
async def synthesize_speech(req: SpeechSynthesisRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty.")

    try:
        result = await speech_service.synthesize_text(
            req.text.strip(),
            voice=req.voice,
            speed=req.speed,
            response_format=req.response_format,
        )
    except SpeechServiceError as err:
        _raise_speech_http_error(err)

    return SpeechSynthesisResponse(
        audio_base64=result.audio_base64,
        mime_type=result.mime_type,
        provider=result.provider,
        model=result.model,
        voice=result.voice,
        latency_ms=result.latency_ms,
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )
