from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    observe = "observe"
    ask = "ask"
    bluff = "bluff"
    search = "search"
    accuse = "accuse"
    move = "move"
    eavesdrop = "eavesdrop"
    hide = "hide"
    other = "other"


class FactScope(str, Enum):
    public = "public"
    player_known = "player_known"
    npc_private = "npc_private"
    shared_secret = "shared_secret"
    truth = "truth"


class Character(BaseModel):
    id: str
    name: str
    public_role: str
    style: str
    goal: str
    fear: str
    secret: str
    private_knowledge: List[str]
    relation_map: Dict[str, str]
    trust_to_player: int = Field(default=50, ge=0, le=100)
    suspicion: int = Field(default=30, ge=0, le=100)
    speaking_rules: str
    hard_boundaries: List[str]
    location: str = "宴会厅"
    mood: str = "neutral"


class Clue(BaseModel):
    id: str
    text: str
    discovered: bool = False
    holder: Optional[str] = None
    location: str
    discover_condition: str = ""


class Event(BaseModel):
    round: int
    type: str
    text: str


class VoteOption(BaseModel):
    id: str
    label: str
    kind: str = "suspect"


class PublicStatement(BaseModel):
    character_id: str
    character_name: str
    text: str


class VoteRecord(BaseModel):
    voter_id: str
    voter_name: str
    target_id: str
    target_label: str
    reason: str


class VoteState(BaseModel):
    status: str = "idle"
    prompt: str = ""
    options: List[VoteOption] = Field(default_factory=list)
    public_statements: List[PublicStatement] = Field(default_factory=list)
    player_choice_id: Optional[str] = None
    votes: List[VoteRecord] = Field(default_factory=list)
    tally: Dict[str, int] = Field(default_factory=dict)
    winning_option_id: Optional[str] = None
    winning_option_label: Optional[str] = None
    outcome: Optional[str] = None


class StoryTruth(BaseModel):
    core_truth: str
    culprit: Optional[str] = None
    hidden_chain: List[str]


class KnowledgeFact(BaseModel):
    id: str
    text: str
    scope: FactScope
    holders: List[str] = Field(default_factory=list)
    revealed_to_player: bool = False
    publicly_revealed: bool = False
    source: str = ""
    related_characters: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class DisclosureEvent(BaseModel):
    round: int
    fact_id: str
    learned_by: List[str] = Field(default_factory=list)
    method: str
    source: Optional[str] = None
    made_public: bool = False


class KnowledgeGraph(BaseModel):
    public_facts: List[str]
    player_known: List[str] = Field(default_factory=list)
    character_beliefs: Dict[str, List[str]] = Field(default_factory=dict)
    facts: List[KnowledgeFact] = Field(default_factory=list)
    disclosures: List[DisclosureEvent] = Field(default_factory=list)


class GameState(BaseModel):
    session_id: str
    story_id: str
    title: str
    scene: str
    phase: str
    round: int = 0
    tension: int = Field(default=20, ge=0, le=100)
    truth: StoryTruth
    characters: List[Character]
    clues: List[Clue]
    knowledge: KnowledgeGraph
    events: List[Event]
    available_scenes: List[str] = Field(
        default_factory=lambda: ["宴会厅", "书房", "花园", "酒窖", "走廊"]
    )
    vote_state: Optional[VoteState] = None
    game_over: bool = False
    ending: Optional[str] = None
    max_rounds: int = 20
    behavior_tags: Dict[str, int] = Field(default_factory=dict)  # tag -> count
    key_choices: List[str] = Field(default_factory=list)  # irreversible choices made


def _dedupe_texts(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_fact_by_id(state: GameState, fact_id: str) -> Optional[KnowledgeFact]:
    for fact in state.knowledge.facts:
        if fact.id == fact_id:
            return fact
    return None


def get_player_visible_facts(state: GameState) -> List[KnowledgeFact]:
    visible: List[KnowledgeFact] = []
    for fact in state.knowledge.facts:
        if (
            fact.scope in (FactScope.public, FactScope.player_known)
            or fact.publicly_revealed
            or fact.revealed_to_player
            or "player" in fact.holders
        ):
            visible.append(fact)
    return visible


def get_player_visible_fact_texts(state: GameState) -> List[str]:
    texts = list(state.knowledge.public_facts)
    texts.extend(state.knowledge.player_known)
    texts.extend(fact.text for fact in get_player_visible_facts(state))
    return _dedupe_texts(texts)


def get_character_scoped_facts(state: GameState, character_id: str) -> List[str]:
    texts: List[str] = list(state.knowledge.public_facts)
    beliefs = state.knowledge.character_beliefs.get(character_id, [])
    texts.extend(beliefs)
    for fact in state.knowledge.facts:
        if (
            fact.scope == FactScope.public
            or fact.publicly_revealed
            or character_id in fact.holders
        ):
            texts.append(fact.text)
    return _dedupe_texts(texts)


def record_fact_disclosure(
    state: GameState,
    fact_id: str,
    *,
    learned_by: List[str],
    method: str,
    round_num: int,
    source: Optional[str] = None,
    make_public: bool = False,
) -> bool:
    fact = get_fact_by_id(state, fact_id)
    if fact is None:
        return False

    changed = False
    if make_public and not fact.publicly_revealed:
        fact.publicly_revealed = True
        changed = True

    for learner in learned_by:
        if learner == "player":
            if not fact.revealed_to_player:
                fact.revealed_to_player = True
                changed = True
            if fact.text not in state.knowledge.player_known:
                state.knowledge.player_known.append(fact.text)
                changed = True
        else:
            if learner not in fact.holders:
                fact.holders.append(learner)
                changed = True
            beliefs = state.knowledge.character_beliefs.setdefault(learner, [])
            if fact.text not in beliefs:
                beliefs.append(fact.text)
                changed = True

    if fact.scope == FactScope.public or fact.publicly_revealed:
        if fact.text not in state.knowledge.public_facts:
            state.knowledge.public_facts.append(fact.text)
            changed = True

    if changed:
        state.knowledge.disclosures.append(
            DisclosureEvent(
                round=round_num,
                fact_id=fact_id,
                learned_by=list(learned_by),
                method=method,
                source=source,
                made_public=make_public,
            )
        )

    return changed


def redact_game_state(state: GameState) -> dict:
    """Return a player-safe snapshot of game state."""
    state_dict = state.model_dump()
    # Strip internal tracking fields — not for the frontend
    state_dict.pop("behavior_tags", None)
    state_dict.pop("key_choices", None)
    state_dict["truth"] = {
        "core_truth": "[REDACTED]",
        "culprit": state.truth.culprit,
        "hidden_chain": ["[REDACTED]"] * len(state.truth.hidden_chain),
    }
    for char in state_dict["characters"]:
        char["secret"] = "[REDACTED]"
        char["private_knowledge"] = ["[REDACTED]"]
        char["hard_boundaries"] = ["[REDACTED]"]
    state_dict["knowledge"]["player_known"] = get_player_visible_fact_texts(state)
    state_dict["knowledge"]["character_beliefs"] = {}
    state_dict["knowledge"]["facts"] = []
    for fact in get_player_visible_facts(state):
        payload = fact.model_dump()
        payload["holders"] = ["player"] if fact.revealed_to_player else []
        if fact.scope == FactScope.truth:
            payload["source"] = "[REDACTED]"
        state_dict["knowledge"]["facts"].append(payload)
    state_dict["knowledge"]["disclosures"] = [
        disclosure.model_dump()
        for disclosure in state.knowledge.disclosures
        if disclosure.made_public or "player" in disclosure.learned_by
    ]
    return state_dict


class TurnRequest(BaseModel):
    session_id: str
    player_action: str


class NPCReply(BaseModel):
    character_id: str
    character_name: str
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = None


class NPCEvent(BaseModel):
    text: str


class TurnResponse(BaseModel):
    round: int
    phase: str
    tension: int
    scene: str
    director_note: str
    new_clues: List[str] = Field(default_factory=list)
    npc_replies: List[NPCReply] = Field(default_factory=list)
    npc_events: List[NPCEvent] = Field(default_factory=list)
    public_statements: List[PublicStatement] = Field(default_factory=list)
    vote_records: List[VoteRecord] = Field(default_factory=list)
    system_narration: str = ""
    narrator_voice: Optional[str] = None
    scene_image: Optional[str] = None
    game_over: bool = False
    ending: Optional[str] = None
    game_state: Optional[dict] = None


class VoiceProviderState(BaseModel):
    provider: str
    model: Optional[str] = None
    available: bool = False
    detail: str = ""
    fallback: Optional[str] = None


class VoiceStatusResponse(BaseModel):
    asr: VoiceProviderState
    tts: VoiceProviderState


class VoiceTranscriptionResponse(BaseModel):
    transcript: str
    provider: str
    model: str
    latency_ms: int
    usage: Optional[dict] = None


class VoiceTurnResponse(BaseModel):
    transcript: str
    asr: VoiceTranscriptionResponse
    turn: TurnResponse


class SpeechSynthesisRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = None
    response_format: str = "wav"


class SpeechSynthesisResponse(BaseModel):
    audio_base64: str
    mime_type: str
    provider: str
    model: str
    voice: str
    latency_ms: int
