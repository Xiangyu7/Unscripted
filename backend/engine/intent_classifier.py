import re
from typing import Dict, List, Tuple

from schemas.game_state import IntentType


# Keyword mappings for intent classification
INTENT_KEYWORDS: Dict[IntentType, List[str]] = {
    IntentType.observe: ["观察", "看", "注意", "留意", "打量", "审视", "端详", "望", "瞧"],
    IntentType.ask: ["问", "询问", "打听", "了解", "请教", "聊", "谈", "说"],
    IntentType.bluff: ["诈", "试探", "假装", "谎", "骗", "知道了", "已经知道", "装作"],
    IntentType.search: ["搜", "查", "检查", "翻", "调查", "搜查", "找", "寻找", "搜索"],
    IntentType.accuse: ["指控", "指出", "怀疑", "就是你", "凶手", "公开", "揭露", "揭穿"],
    IntentType.move: ["去", "前往", "走到", "进入", "离开", "走向", "来到", "移动"],
    IntentType.eavesdrop: ["偷听", "躲", "藏", "暗中", "悄悄", "窃听", "潜伏"],
    IntentType.hide: ["隐瞒", "藏起", "不公开", "先不说", "保密", "不告诉"],
}

# Character name mappings (Chinese name -> character id)
CHARACTER_NAMES: Dict[str, str] = {
    "林岚": "linlan",
    "linlan": "linlan",
    "林": "linlan",
    "秘书": "linlan",
    "周牧": "zhoumu",
    "zhoumu": "zhoumu",
    "周": "zhoumu",
    "发小": "zhoumu",
    "宋知微": "songzhi",
    "songzhi": "songzhi",
    "宋": "songzhi",
    "记者": "songzhi",
}

# Location name mappings
LOCATION_NAMES: Dict[str, str] = {
    "书房": "书房",
    "花园": "花园",
    "酒窖": "酒窖",
    "走廊": "走廊",
    "宴会厅": "宴会厅",
    "大厅": "宴会厅",
}

# Topic keywords that might be mentioned
TOPIC_KEYWORDS: List[str] = [
    "遗嘱", "遗产", "失踪", "争吵", "昨晚", "书房", "酒窖",
    "脚印", "划痕", "信", "纸条", "匿名", "晚宴", "顾言",
    "钱", "财产", "基金会", "秘密", "真相", "嫌疑",
]


def classify_intent(action: str) -> Tuple[IntentType, dict]:
    """
    Classify the player's action into an intent type with metadata.

    Returns:
        (intent_type, metadata) where metadata includes:
        - target_character: Optional[str] - character id if a character is referenced
        - target_location: Optional[str] - location name if a location is referenced
        - mentioned_topics: List[str] - topics mentioned in the action
    """
    action_lower = action.lower().strip()

    # Detect target character
    target_character = None
    for name, char_id in CHARACTER_NAMES.items():
        if name in action:
            target_character = char_id
            break

    # Detect target location
    target_location = None
    for loc_key, loc_name in LOCATION_NAMES.items():
        if loc_key in action:
            target_location = loc_name
            break

    # Detect mentioned topics
    mentioned_topics = [topic for topic in TOPIC_KEYWORDS if topic in action]

    # Score each intent type based on keyword matches
    intent_scores: Dict[IntentType, int] = {intent: 0 for intent in IntentType}

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in action:
                # Give higher score for longer keyword matches (more specific)
                intent_scores[intent] += len(keyword)

    # Special pattern matching for stronger signals
    # "去xxx" pattern strongly suggests move
    if re.search(r"去(书房|花园|酒窖|走廊|宴会厅|大厅)", action):
        intent_scores[IntentType.move] += 10

    # "问xxx" pattern strongly suggests ask
    if re.search(r"(问|询问)(林岚|周牧|宋知微)", action):
        intent_scores[IntentType.ask] += 10

    # "搜(查|索)xxx" pattern strongly suggests search
    if re.search(r"(搜|查|检查|翻)(书房|花园|酒窖|走廊|宴会厅)", action):
        intent_scores[IntentType.search] += 10

    # Accusation patterns
    if re.search(r"(就是你|你就是|指控|揭穿|凶手是)", action):
        intent_scores[IntentType.accuse] += 10

    # Bluff patterns
    if re.search(r"(我(已经)?知道|我(都)?听说了|别装了)", action):
        intent_scores[IntentType.bluff] += 10

    # Eavesdrop patterns
    if re.search(r"(偷听|暗中|悄悄|躲在.+听)", action):
        intent_scores[IntentType.eavesdrop] += 10

    # Find the highest scoring intent
    best_intent = IntentType.other
    best_score = 0

    for intent, score in intent_scores.items():
        if score > best_score:
            best_score = score
            best_intent = intent

    # If no strong match, try to infer from context
    if best_intent == IntentType.other:
        # If a character is mentioned, default to "ask"
        if target_character:
            best_intent = IntentType.ask
        # If a location is mentioned, could be "move" or "search"
        elif target_location:
            # Check for action verbs that hint at search vs move
            if any(w in action for w in ["里", "中", "内", "周围"]):
                best_intent = IntentType.search
            else:
                best_intent = IntentType.observe

    metadata = {
        "target_character": target_character,
        "target_location": target_location,
        "mentioned_topics": mentioned_topics,
    }

    return best_intent, metadata
