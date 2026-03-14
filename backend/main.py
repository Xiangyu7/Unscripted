import sys
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env before config is initialized
load_dotenv()

from config import Config
from engine.turn_engine import TurnEngine, sessions
from schemas.game_state import GameState, TurnRequest, TurnResponse
from stories.gu_family_case import create_initial_state

# Initialize config and engine
config = Config()
engine = TurnEngine(config)


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


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: Optional[str]
    active_sessions: int


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


@app.post("/api/reset", response_model=ResetResponse)
async def reset_session(req: ResetRequest = ResetRequest()):
    """Create or reset a game session."""
    sid = req.session_id or str(uuid.uuid4())

    if req.story_id == "gu_family_case":
        state = create_initial_state(sid)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown story_id: '{req.story_id}'. Available: ['gu_family_case']",
        )

    sessions[sid] = state
    return ResetResponse(session_id=sid, message="Session created successfully.")


@app.get("/api/state/{session_id}")
async def get_state(session_id: str):
    """Get the current game state for a session."""
    state = sessions.get(session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )
    # Return the full state, but redact the truth for the player
    state_dict = state.model_dump()
    # Remove truth details from the response to prevent cheating
    state_dict["truth"] = {
        "core_truth": "[REDACTED]",
        "culprit": state.truth.culprit,
        "hidden_chain": ["[REDACTED]"] * len(state.truth.hidden_chain),
    }
    # Remove character secrets and private knowledge
    for char in state_dict["characters"]:
        char["secret"] = "[REDACTED]"
        char["private_knowledge"] = ["[REDACTED]"]
        char["hard_boundaries"] = ["[REDACTED]"]
    return state_dict


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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )
