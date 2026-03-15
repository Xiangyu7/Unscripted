"""
NPC Interaction System — makes NPCs feel alive through:
  1. Memory callbacks — "你上次问我遗嘱的事，我已经回答过了"
  2. Proactive speech — NPCs speak up without being asked
  3. NPC-to-NPC confrontations — two characters argue in front of the player
"""

import random
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel


class NPCDialogue(BaseModel):
    """A line of NPC dialogue (proactive or confrontation)."""
    character_id: str
    character_name: str
    text: str
    is_proactive: bool = False       # NPC spoke without being asked
    is_confrontation: bool = False   # Part of NPC-vs-NPC argument


# ═══════════════════════════════════════════════════════════════
# 1. Memory — build "what I remember" context for character prompt
# ═══════════════════════════════════════════════════════════════

def build_memory_context(
    character_id: str,
    character_name: str,
    conversation_history: List[dict],  # [{round, statement}]
    player_asked_topics: List[str],
) -> str:
    """Build a memory prompt section so the NPC can reference past conversations."""
    if not conversation_history:
        return ""

    parts = []
    parts.append(f"【{character_name}的记忆——你记得之前跟侦探的对话】")

    for entry in conversation_history[-5:]:  # Last 5 exchanges
        parts.append(f"- 第{entry['round']}轮你说过: \"{entry['statement'][:80]}\"")

    # Topics the player has repeatedly asked about
    if player_asked_topics:
        repeated = [t for t in player_asked_topics if player_asked_topics.count(t) >= 2]
        if repeated:
            unique_repeated = list(set(repeated))[:3]
            parts.append(f"\n侦探反复追问过这些话题: {', '.join(unique_repeated)}")
            parts.append("如果侦探又问同样的问题，你可以表现出不耐烦：")
            parts.append("'这个问题你已经问过了。我的答案没有变。'")
            parts.append("或者用新的角度回答，但暗示你记得他问过。")

    parts.append("\n你可以主动引用之前的对话来显示你一直在注意：")
    parts.append("例如: '你之前问了我关于遗嘱的事——我注意到你对这个很感兴趣。'")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 2. Proactive speech — NPC speaks up without being asked
# ═══════════════════════════════════════════════════════════════

# Conditions that trigger proactive speech
PROACTIVE_TRIGGERS = {
    "linlan": [
        {
            "condition": lambda tension, round_num, discovered, **kw: tension >= 40 and round_num >= 5,
            "lines": [
                "林岚突然开口：「侦探先生，我想提醒你一件事——顾先生失踪前那天下午，周牧和他在书房里待了很久。出来的时候，两个人脸色都不太好。」",
                "林岚放下茶杯，主动说道：「我不知道这是否重要，但今晚宋知微一直在拍照和记笔记。一个普通的晚宴客人，不会这样做。」",
                "林岚的目光扫过众人：「继续这样下去，对谁都没有好处。也许是时候让某些人说出真话了。」她的眼神在周牧身上停了一秒。",
            ],
        },
        {
            "condition": lambda tension, discovered, **kw: tension >= 60 and len(discovered) >= 4,
            "lines": [
                "林岚深吸一口气：「好吧。有些事我一直没说——不是因为我想隐瞒，而是因为顾先生要求我保密。但现在……」她顿了顿，「情况变了。」",
            ],
        },
    ],
    "zhoumu": [
        {
            "condition": lambda tension, round_num, **kw: tension >= 35 and round_num >= 4,
            "lines": [
                "周牧突然放下酒杯：「行了行了，你们都看着我干嘛？说起来，我倒想问问宋知微——你到底是怎么知道今晚会出事的？」",
                "周牧站起来踱步：「我跟顾言认识二十年了。二十年。你们谁有资格在这里指指点点？」他的声音在发抖。",
                "周牧突然对你说：「侦探，我觉得你搞错方向了。你不应该查我们三个——你应该查查这栋房子。这里面有太多秘密了。」",
            ],
        },
        {
            "condition": lambda tension, **kw: tension >= 55,
            "lines": [
                "周牧猛地灌了一口酒：「好吧！你想知道真相？说起来……昨晚我确实跟顾言吵了一架。但那是因为……」他突然闭嘴了，像是说多了。",
            ],
        },
    ],
    "songzhi": [
        {
            "condition": lambda round_num, discovered, **kw: round_num >= 3 and len(discovered) >= 1,
            "lines": [
                "宋知微推了推眼镜，翻开笔记本：「侦探先生，我整理了一下时间线。顾言最后被人看到是晚上8点45分。从那之后到现在，这栋宅子里至少发生了三件值得注意的事。」",
                "宋知微抬起头：「等一下——我刚才注意到一个细节。林岚，你说你整晚都在宴会厅？那为什么你的鞋底有走廊地毯的绒毛？」",
                "宋知微合上笔记本，看着你：「我们交换一下情报？我告诉你我观察到的，你告诉我你发现的线索。公平交易。」",
            ],
        },
        {
            "condition": lambda tension, discovered, **kw: tension >= 50 and len(discovered) >= 3,
            "lines": [
                "宋知微突然站起来：「好了，我不装了。我来这里不是巧合——我收到过一封匿名信，说今晚顾家会出事。信上没有署名，但……」她看了林岚一眼，「笔迹很眼熟。」",
            ],
        },
    ],
}


def get_proactive_speech(
    character_id: str,
    tension: int,
    round_num: int,
    discovered_clues: List[str],
    used_lines: set,
) -> Optional[NPCDialogue]:
    """Check if an NPC wants to speak up proactively this turn."""
    triggers = PROACTIVE_TRIGGERS.get(character_id, [])
    char_names = {"linlan": "林岚", "zhoumu": "周牧", "songzhi": "宋知微"}

    for trigger in triggers:
        ctx = {
            "tension": tension,
            "round_num": round_num,
            "discovered": discovered_clues,
        }
        if trigger["condition"](**ctx):
            available = [l for l in trigger["lines"] if l not in used_lines]
            if available:
                line = random.choice(available)
                used_lines.add(line)
                return NPCDialogue(
                    character_id=character_id,
                    character_name=char_names.get(character_id, character_id),
                    text=line,
                    is_proactive=True,
                )
    return None


# ═══════════════════════════════════════════════════════════════
# 3. NPC-to-NPC confrontation — two characters argue
# ═══════════════════════════════════════════════════════════════

CONFRONTATION_SCRIPTS: List[dict] = [
    {
        "id": "linlan_vs_zhoumu_will",
        "trigger": lambda tension, discovered, **kw: tension >= 45 and any("遗嘱" in c for c in discovered),
        "characters": ("linlan", "zhoumu"),
        "dialogue": [
            NPCDialogue(character_id="zhoumu", character_name="周牧",
                        text="周牧猛地转向林岚：「你到底在替顾言藏什么？你以为我不知道——遗嘱的事，你从头到尾都清楚！」",
                        is_confrontation=True),
            NPCDialogue(character_id="linlan", character_name="林岚",
                        text="林岚冷冷地回视：「我藏什么？周牧，比起我，你倒是应该解释一下昨晚为什么那么大声。整个走廊都听到了你和顾先生的争吵。」",
                        is_confrontation=True),
            NPCDialogue(character_id="zhoumu", character_name="周牧",
                        text="周牧脸涨得通红：「那是我们兄弟之间的事！你一个外人——」他突然住嘴，意识到说多了。",
                        is_confrontation=True),
        ],
    },
    {
        "id": "songzhi_vs_linlan_tip",
        "trigger": lambda tension, discovered, **kw: tension >= 50 and any("纸条" in c or "匿名" in c for c in discovered),
        "characters": ("songzhi", "linlan"),
        "dialogue": [
            NPCDialogue(character_id="songzhi", character_name="宋知微",
                        text="宋知微突然开口：「林岚小姐，我有个问题。那张写着'注意遗产'的纸条——笔迹工整、用词精准、提前准备好的。你作为秘书，经手的文件最多。你认不认得这个笔迹？」",
                        is_confrontation=True),
            NPCDialogue(character_id="linlan", character_name="林岚",
                        text="林岚的指尖在桌面上停顿了一秒：「宋小姐，你身为记者，应该知道——指认笔迹需要专业鉴定，不是靠猜测。」",
                        is_confrontation=True),
            NPCDialogue(character_id="songzhi", character_name="宋知微",
                        text="宋知微嘴角一挑：「你没有否认。这条信息很有趣。」她在笔记本上飞快地写了几个字。",
                        is_confrontation=True),
        ],
    },
    {
        "id": "zhoumu_vs_songzhi_motive",
        "trigger": lambda tension, round_num, **kw: tension >= 55 and round_num >= 10,
        "characters": ("zhoumu", "songzhi"),
        "dialogue": [
            NPCDialogue(character_id="zhoumu", character_name="周牧",
                        text="周牧突然指着宋知微：「你！说到底在场的人里，你的动机最明显！一个记者恰好在犯罪现场？别告诉我是巧合。你早就知道今晚会出事！」",
                        is_confrontation=True),
            NPCDialogue(character_id="songzhi", character_name="宋知微",
                        text="宋知微推了推眼镜，不慌不忙：「周牧先生，愤怒不能替代逻辑。比起问我为什么在这里，你不如解释一下——你口袋里那封一直没拆的信，是写给谁的？」",
                        is_confrontation=True),
            NPCDialogue(character_id="zhoumu", character_name="周牧",
                        text="周牧下意识摸了摸口袋，然后猛地把手放下：「那是……那跟这件事没关系！」",
                        is_confrontation=True),
        ],
    },
]


class NPCInteractionSystem:
    """Manages proactive NPC speech and NPC-vs-NPC confrontations."""

    def __init__(self):
        self._used_proactive: Dict[str, set] = {}   # session → used lines
        self._used_confrontations: Dict[str, set] = {}  # session → used script IDs

    def get_proactive_lines(
        self,
        session_id: str,
        present_characters: List[str],
        tension: int,
        round_num: int,
        discovered_clues: List[str],
    ) -> List[NPCDialogue]:
        """Get proactive NPC lines for this turn (max 1)."""
        if session_id not in self._used_proactive:
            self._used_proactive[session_id] = set()

        # Only 30% chance to trigger proactive speech per turn
        if random.random() > 0.3:
            return []

        # Pick one random present character to speak
        random.shuffle(present_characters)
        for char_id in present_characters:
            line = get_proactive_speech(
                char_id, tension, round_num, discovered_clues,
                self._used_proactive[session_id],
            )
            if line:
                return [line]
        return []

    def get_confrontation(
        self,
        session_id: str,
        present_characters: List[str],
        tension: int,
        round_num: int,
        discovered_clue_texts: List[str],
    ) -> List[NPCDialogue]:
        """Check if a confrontation should trigger between two NPCs."""
        if session_id not in self._used_confrontations:
            self._used_confrontations[session_id] = set()

        # Only trigger confrontation 20% of the time
        if random.random() > 0.2:
            return []

        present_set = set(present_characters)

        for script in CONFRONTATION_SCRIPTS:
            if script["id"] in self._used_confrontations[session_id]:
                continue

            char_a, char_b = script["characters"]
            if char_a not in present_set or char_b not in present_set:
                continue

            ctx = {
                "tension": tension,
                "round_num": round_num,
                "discovered": discovered_clue_texts,
            }
            if script["trigger"](**ctx):
                self._used_confrontations[session_id].add(script["id"])
                return script["dialogue"]

        return []
