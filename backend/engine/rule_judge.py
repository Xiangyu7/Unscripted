import random
from typing import Dict, List, Optional

from schemas.game_state import GameState, IntentType


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    """Clamp a value to [lo, hi] range."""
    return max(lo, min(hi, value))


def _discover_clues_for_location(
    location: str,
    intent: IntentType,
    state: GameState,
) -> List[str]:
    """Find clues that can be discovered at the given location with current conditions."""
    discovered = []

    for clue in state.clues:
        if clue.discovered:
            continue
        if clue.location != location:
            continue

        condition = clue.discover_condition

        # Parse discover conditions
        can_discover = False

        # Simple search condition: "search<location>"
        if f"search{location}" in condition and intent == IntentType.search:
            # Check for tension threshold: "且 tension>=X"
            if "tension>=" in condition:
                try:
                    threshold = int(condition.split("tension>=")[1].split()[0])
                    if state.tension >= threshold:
                        can_discover = True
                except (ValueError, IndexError):
                    can_discover = True
            else:
                can_discover = True

        # Eavesdrop condition: "eavesdrop<location>"
        if f"eavesdrop{location}" in condition and intent == IntentType.eavesdrop:
            can_discover = True

        # Observe condition: "observe仔细"
        if "observe" in condition and intent == IntentType.observe:
            can_discover = True

        # "或" (OR) conditions - check each side
        if "或" in condition:
            parts = condition.split("或")
            for part in parts:
                part = part.strip()
                if f"search{location}" in part and intent == IntentType.search:
                    if "tension>=" in part:
                        try:
                            threshold = int(part.split("tension>=")[1].split()[0])
                            if state.tension >= threshold:
                                can_discover = True
                        except (ValueError, IndexError):
                            can_discover = True
                    else:
                        can_discover = True
                if f"eavesdrop{location}" in part and intent == IntentType.eavesdrop:
                    can_discover = True
                if "observe" in part and intent == IntentType.observe:
                    can_discover = True

        if can_discover:
            discovered.append(clue.id)

    return discovered


def _get_characters_at_location(state: GameState, location: str) -> List[str]:
    """Get character IDs at a given location."""
    return [c.id for c in state.characters if c.location == location]


def _determine_phase(state: GameState, intent: IntentType) -> Optional[str]:
    """Determine if a phase transition should occur."""
    discovered_count = sum(1 for c in state.clues if c.discovered)

    if intent == IntentType.accuse:
        return "公开对峙"
    if state.tension >= 70:
        return "高压对峙"
    if discovered_count >= 3:
        return "深入调查"
    if state.round >= state.max_rounds - 3:
        return "终局逼近"

    return None


def judge_action(intent: IntentType, metadata: dict, state: GameState) -> dict:
    """
    Judge the player's action based on intent, metadata, and current game state.

    Returns a dict with:
        success: "full" | "partial" | "blocked"
        tension_delta: int
        suspicion_changes: {char_id: int_delta}
        trust_changes: {char_id: int_delta}
        discovered_clues: [clue_id]
        phase_change: Optional[str]
        narration: str
        boundary_note: Optional[str]
    """
    result: Dict = {
        "success": "full",
        "tension_delta": 0,
        "suspicion_changes": {},
        "trust_changes": {},
        "discovered_clues": [],
        "phase_change": None,
        "narration": "",
        "boundary_note": None,
    }

    target_char = metadata.get("target_character")
    target_loc = metadata.get("target_location")

    # Resolve effective location for searching
    # The current scene name may include a prefix like "顾家老宅·"
    current_scene_short = state.scene
    for scene in state.available_scenes:
        if scene in state.scene:
            current_scene_short = scene
            break

    if intent == IntentType.observe:
        result["success"] = "full"
        result["tension_delta"] = random.randint(3, 5)
        result["narration"] = "你仔细打量着周围的一切，试图从细节中找出端倪。"

        # Observing can discover clues at current location
        result["discovered_clues"] = _discover_clues_for_location(
            current_scene_short, IntentType.observe, state
        )

        # Small trust boost with characters present
        for char_id in _get_characters_at_location(state, current_scene_short):
            result["trust_changes"][char_id] = random.randint(1, 3)

    elif intent == IntentType.ask:
        if target_char:
            char = next((c for c in state.characters if c.id == target_char), None)
            if char:
                if char.trust_to_player > 40:
                    result["success"] = "full"
                    result["narration"] = f"你向{char.name}提出了问题，对方似乎愿意回应。"
                    result["trust_changes"][target_char] = random.randint(1, 3)
                elif char.trust_to_player >= 20:
                    result["success"] = "partial"
                    result["narration"] = f"{char.name}犹豫了一下，只给了你一个模棱两可的回答。"
                    result["trust_changes"][target_char] = random.randint(-1, 1)
                else:
                    result["success"] = "blocked"
                    result["narration"] = f"{char.name}冷冷地看了你一眼，显然不想搭理你。"
                    result["trust_changes"][target_char] = random.randint(-2, 0)

                result["tension_delta"] = random.randint(3, 6)
                result["suspicion_changes"][target_char] = random.randint(1, 3)
            else:
                result["success"] = "blocked"
                result["narration"] = "你想问的人不在这里。"
                result["boundary_note"] = "找不到你要询问的对象。"
        else:
            # General question to the room
            result["success"] = "partial"
            result["tension_delta"] = random.randint(2, 4)
            result["narration"] = "你向在场的人提出了问题，有人交换了一下眼神。"

    elif intent == IntentType.bluff:
        result["tension_delta"] = random.randint(8, 12)

        if target_char:
            char = next((c for c in state.characters if c.id == target_char), None)
            if char:
                if char.suspicion > 50:
                    result["success"] = "partial"
                    result["narration"] = (
                        f"你的试探让{char.name}明显紧张了起来，"
                        "但对方很快又恢复了镇定。你从TA的反应中捕捉到了一些信息。"
                    )
                    result["suspicion_changes"][target_char] = random.randint(5, 8)
                else:
                    result["success"] = "blocked"
                    result["narration"] = (
                        f"{char.name}不为所动地看着你，"
                        "似乎你的诈术没有起效。"
                    )
                    result["suspicion_changes"][target_char] = random.randint(2, 4)

                result["trust_changes"][target_char] = random.randint(-10, -5)
            else:
                result["success"] = "blocked"
                result["narration"] = "你想试探的人不在附近。"
        else:
            # Bluff to the room
            result["success"] = "partial"
            result["narration"] = "你抛出了一个模棱两可的暗示，在场的人各有反应。"
            for char in state.characters:
                if char.location == current_scene_short:
                    result["trust_changes"][char.id] = random.randint(-6, -3)
                    result["suspicion_changes"][char.id] = random.randint(2, 5)

    elif intent == IntentType.search:
        search_location = target_loc or current_scene_short

        if search_location == current_scene_short or target_loc is None:
            result["success"] = "full"
            result["tension_delta"] = random.randint(6, 10)
            result["narration"] = f"你仔细搜查了{search_location}的每个角落。"

            result["discovered_clues"] = _discover_clues_for_location(
                search_location, IntentType.search, state
            )

            if result["discovered_clues"]:
                clue_texts = []
                for cid in result["discovered_clues"]:
                    clue = next((c for c in state.clues if c.id == cid), None)
                    if clue:
                        clue_texts.append(clue.text)
                result["narration"] += (
                    "你发现了一些东西：" + "；".join(clue_texts) + "。"
                )
            else:
                result["narration"] += "但没有发现什么特别的东西。"

            # Characters at location become more suspicious
            for char_id in _get_characters_at_location(state, search_location):
                result["suspicion_changes"][char_id] = random.randint(2, 5)
                result["trust_changes"][char_id] = random.randint(-3, -1)
        else:
            result["success"] = "blocked"
            result["tension_delta"] = random.randint(2, 4)
            result["narration"] = f"你需要先去{search_location}才能搜查那里。"
            result["boundary_note"] = f"你当前在{current_scene_short}，无法搜查{search_location}。请先移动到那里。"

    elif intent == IntentType.accuse:
        result["success"] = "full"
        result["tension_delta"] = random.randint(12, 18)
        result["narration"] = "你公开提出了你的怀疑，气氛一下子紧张到了极点。所有人的目光都聚集在了一起。"

        # Big trust/suspicion changes for everyone
        for char in state.characters:
            if char.id == target_char:
                result["trust_changes"][char.id] = random.randint(-15, -8)
                result["suspicion_changes"][char.id] = random.randint(8, 15)
            else:
                result["trust_changes"][char.id] = random.randint(-5, 3)
                result["suspicion_changes"][char.id] = random.randint(-3, 5)

    elif intent == IntentType.move:
        if target_loc:
            if target_loc in state.available_scenes:
                result["success"] = "full"
                result["tension_delta"] = 2
                result["narration"] = f"你离开了{current_scene_short}，来到了{target_loc}。"
            else:
                result["success"] = "blocked"
                result["narration"] = f"你不知道怎么去{target_loc}。"
                result["boundary_note"] = f"'{target_loc}'不是一个可以前往的地点。"
        else:
            result["success"] = "blocked"
            result["narration"] = "你想去哪里？请指明目的地。"
            result["boundary_note"] = "请指明你要前往的地点。"

    elif intent == IntentType.eavesdrop:
        result["tension_delta"] = random.randint(5, 8)

        # 50% chance of success
        if random.random() < 0.5:
            result["success"] = "full"
            result["narration"] = "你小心翼翼地藏好自己，竖起耳朵聆听。你听到了一些有趣的动静。"

            eavesdrop_location = target_loc or current_scene_short
            result["discovered_clues"] = _discover_clues_for_location(
                eavesdrop_location, IntentType.eavesdrop, state
            )
        else:
            result["success"] = "partial"
            result["narration"] = "你试图偷听，但只捕捉到一些断断续续的片段，无法拼凑出完整信息。"

    elif intent == IntentType.hide:
        result["success"] = "full"
        result["tension_delta"] = 0
        result["narration"] = "你决定暂时保守这个信息，等待更好的时机。"

    else:  # IntentType.other
        result["success"] = "partial"
        result["tension_delta"] = random.randint(1, 3)
        result["narration"] = "你做了一些事情，但似乎没有产生太大的影响。"

    # Determine phase change
    # We need to simulate the state after tension change for phase calculation
    simulated_tension = _clamp(state.tension + result["tension_delta"])
    simulated_discovered = sum(1 for c in state.clues if c.discovered) + len(
        result["discovered_clues"]
    )

    if intent == IntentType.accuse:
        result["phase_change"] = "公开对峙"
    elif simulated_tension >= 70 and state.phase != "高压对峙":
        result["phase_change"] = "高压对峙"
    elif simulated_discovered >= 3 and state.phase == "自由试探":
        result["phase_change"] = "深入调查"
    elif state.round >= state.max_rounds - 3 and state.phase not in (
        "终局逼近",
        "公开对峙",
    ):
        result["phase_change"] = "终局逼近"

    return result
