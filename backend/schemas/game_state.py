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


class StoryTruth(BaseModel):
    core_truth: str
    culprit: Optional[str] = None
    hidden_chain: List[str]


class KnowledgeGraph(BaseModel):
    public_facts: List[str]
    player_known: List[str] = Field(default_factory=list)
    character_beliefs: Dict[str, List[str]] = Field(default_factory=dict)


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
    game_over: bool = False
    ending: Optional[str] = None
    max_rounds: int = 20


class TurnRequest(BaseModel):
    session_id: str
    player_action: str


class NPCReply(BaseModel):
    character_id: str
    character_name: str
    text: str


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
    system_narration: str = ""
    game_over: bool = False
    ending: Optional[str] = None
