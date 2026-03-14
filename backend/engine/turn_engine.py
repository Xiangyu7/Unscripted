import asyncio
from typing import Dict, Optional

from agents.character_agent import CharacterAgent
from agents.director_agent import DirectorAgent
from config import Config
from engine.intent_classifier import classify_intent
from engine.rule_judge import judge_action
from schemas.game_state import (
    Event,
    GameState,
    NPCEvent,
    NPCReply,
    TurnResponse,
)


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    """Clamp a value to [lo, hi] range."""
    return max(lo, min(hi, value))


# In-memory session storage (shared across the application)
sessions: Dict[str, GameState] = {}


class TurnEngine:
    """Orchestrates a full game turn: classify, judge, direct, respond."""

    def __init__(self, config: Config):
        self.config = config
        self.director = DirectorAgent(config)
        self.character_agent = CharacterAgent(config)

    async def process_turn(
        self, session_id: str, player_action: str
    ) -> TurnResponse:
        """
        Process a complete game turn.

        Flow:
        1. Get current GameState from session store
        2. Check if game is over
        3. Classify intent
        4. Judge action with rule_judge
        5. If scene changed (move), update state.scene
        6. Call director_agent
        7. Determine which characters to call
        8. Call character_agent for each relevant character
        9. Update game state
        10. Check end conditions
        11. Return TurnResponse
        """
        # 1. Get current state
        state = sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session '{session_id}' not found. Please create a session first.")

        # 2. Check if game is already over
        if state.game_over:
            return TurnResponse(
                round=state.round,
                phase=state.phase,
                tension=state.tension,
                scene=state.scene,
                director_note="游戏已经结束。" + (state.ending or ""),
                game_over=True,
                ending=state.ending,
            )

        # 3. Classify intent
        intent, metadata = classify_intent(player_action)

        # 4. Judge action
        rule_result = judge_action(intent, metadata, state)

        # 5. Handle scene movement
        target_loc = metadata.get("target_location")
        if intent.value == "move" and rule_result["success"] == "full" and target_loc:
            state.scene = target_loc

        # Get current scene (short name) for location matching
        current_scene_short = state.scene
        for scene in state.available_scenes:
            if scene in state.scene:
                current_scene_short = scene
                break

        # 6. Call director agent
        direction = await self.director.generate_direction(
            state, player_action, rule_result
        )

        # 7. Determine which characters to respond
        target_char_id = metadata.get("target_character")
        relevant_characters = []

        for char in state.characters:
            # Character is relevant if:
            # - They are specifically targeted
            # - They are in the same location as the player
            # - The action is accuse (everyone reacts)
            is_targeted = char.id == target_char_id
            is_at_same_location = char.location == current_scene_short
            is_accuse = intent.value == "accuse"

            if is_targeted or (is_at_same_location and intent.value != "move") or is_accuse:
                relevant_characters.append(char)

        # 8. Call character agents in parallel
        async def get_char_response(char):
            response_text = await self.character_agent.generate_response(
                character=char,
                state=state,
                player_action=player_action,
                intent=intent,
                rule_result=rule_result,
            )
            return NPCReply(
                character_id=char.id,
                character_name=char.name,
                text=response_text,
            )

        npc_replies = []
        if relevant_characters:
            tasks = [get_char_response(c) for c in relevant_characters]
            npc_replies = await asyncio.gather(*tasks)
            npc_replies = list(npc_replies)

        # 9. Update game state

        # Round increment
        state.round += 1

        # Tension
        state.tension = _clamp(state.tension + rule_result["tension_delta"])

        # Trust and suspicion changes
        for char in state.characters:
            if char.id in rule_result.get("trust_changes", {}):
                char.trust_to_player = _clamp(
                    char.trust_to_player + rule_result["trust_changes"][char.id]
                )
            if char.id in rule_result.get("suspicion_changes", {}):
                char.suspicion = _clamp(
                    char.suspicion + rule_result["suspicion_changes"][char.id]
                )

        # Discover clues
        new_clue_texts = []
        for clue_id in rule_result.get("discovered_clues", []):
            for clue in state.clues:
                if clue.id == clue_id and not clue.discovered:
                    clue.discovered = True
                    clue.holder = "player"
                    new_clue_texts.append(clue.text)
                    if clue.text not in state.knowledge.player_known:
                        state.knowledge.player_known.append(clue.text)

        # Phase change
        if rule_result.get("phase_change"):
            state.phase = rule_result["phase_change"]
        if direction.get("suggested_phase") and not rule_result.get("phase_change"):
            state.phase = direction["suggested_phase"]

        # Record events
        state.events.append(
            Event(
                round=state.round,
                type=intent.value,
                text=f"玩家：{player_action}",
            )
        )

        # NPC events from director
        npc_events = []
        for evt_text in direction.get("npc_events", []):
            npc_events.append(NPCEvent(text=evt_text))
            state.events.append(
                Event(
                    round=state.round,
                    type="npc_event",
                    text=evt_text,
                )
            )

        # 10. Check end conditions
        game_over = False
        ending = None

        if state.round >= state.max_rounds:
            game_over = True
            ending = (
                "时间耗尽——天亮了，警察到来。"
                "你未能在限定时间内查明真相。"
                "顾言从酒窖密室中走出，揭示了一切都是他的试探。"
            )
        elif state.tension >= 100:
            game_over = True
            ending = (
                "局势彻底失控——有人在混乱中摔碎了花瓶，"
                "警报声大作。管家报了警，所有人被带走问话。"
                "真相依然笼罩在迷雾之中。"
            )
        else:
            # Check for "真相大白" ending
            cellar_sound = next(
                (c for c in state.clues if c.id == "cellar_sound"), None
            )
            if (
                cellar_sound
                and cellar_sound.discovered
                and intent.value == "search"
                and target_loc == "酒窖"
                and state.tension >= 80
            ):
                game_over = True
                ending = (
                    "真相大白——你在酒窖深处发现了一间密室，"
                    "顾言就在里面！他微微一笑：'你找到我了。'"
                    "原来一切都是顾言自导自演的试探。"
                    "他想看看在他'失踪'后，身边的人会露出怎样的真面目。"
                )

            # Check for "完美破局" ending
            if intent.value == "accuse" and player_action:
                action_lower = player_action.lower()
                truth_keywords = ["自导自演", "自己策划", "假装失踪", "酒窖密室", "试探"]
                matches = sum(1 for kw in truth_keywords if kw in action_lower)
                if matches >= 2:
                    game_over = True
                    ending = (
                        "完美破局——你精准地道出了真相的核心！"
                        "顾言从酒窖密室中走出，向你鼓掌：'了不起，你看穿了一切。'"
                        "他的失踪确实是一场精心策划的试探——"
                        "而你，是唯一识破了这场戏的人。"
                    )

        if game_over:
            state.game_over = True
            state.ending = ending

        # 11. Build and return TurnResponse
        return TurnResponse(
            round=state.round,
            phase=state.phase,
            tension=state.tension,
            scene=state.scene,
            director_note=direction.get("director_note", ""),
            new_clues=new_clue_texts,
            npc_replies=npc_replies,
            npc_events=npc_events,
            system_narration=(
                rule_result.get("narration", "")
                + " "
                + direction.get("system_narration", "")
            ).strip(),
            game_over=game_over,
            ending=ending,
        )
