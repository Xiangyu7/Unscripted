"""
Auto Playtest — LLM plays as detective to find bugs.

Runs a full game session with an LLM-powered detective that makes decisions
each turn, while an issue detector watches for narrative problems.

Usage:
    python -m tests.auto_playtest
    python -m tests.auto_playtest --strategy aggressive
    python -m tests.auto_playtest --rounds 10
    python -m tests.auto_playtest --strategy random --rounds 15
"""

import asyncio
import argparse
import re
import sys
import os
import time
from dataclasses import dataclass, field
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from config import Config, LLMProvider
from engine.turn_engine import TurnEngine, sessions
from stories.gu_family_case import create_initial_state
from schemas.game_state import redact_game_state, TurnResponse, GameState


# ─── Terminal colors ──────────────────────────────────────────────────

class C:
    """ANSI color codes for terminal output."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"

    @staticmethod
    def supports_color() -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    @classmethod
    def disable(cls):
        for attr in ("BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE",
                      "MAGENTA", "CYAN", "WHITE", "RESET"):
            setattr(cls, attr, "")


if not C.supports_color():
    C.disable()


# ─── Data structures ─────────────────────────────────────────────────

@dataclass
class Issue:
    round: int
    category: str        # contradiction | leakage | inconsistency | dead_end | error | empty_response
    severity: str        # critical | warning | info
    description: str
    context: str = ""


@dataclass
class TurnRecord:
    round: int
    action: str
    director_note: str = ""
    npc_replies: list = field(default_factory=list)
    new_clues: list = field(default_factory=list)
    scene: str = ""
    tension: int = 0
    phase: str = ""
    elapsed_ms: int = 0
    error: Optional[str] = None


# ─── Detective (LLM player) ──────────────────────────────────────────

class PlaytestDetective:
    """LLM-powered detective that plays the game automatically."""

    def __init__(self, config: Config, strategy: str = "thorough"):
        self.config = config
        self.strategy = strategy
        self.action_history: list[str] = []
        self.visited_scenes: set[str] = set()
        self.talked_to: set[str] = set()
        self.clue_count = 0
        self._recent_events: list[str] = []  # tracks what happened for context
        self._init_client()

    def _init_client(self):
        if self.config.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=self.config.anthropic_key)
            self._openai = None
        else:
            from openai import AsyncOpenAI
            self._openai = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
            self._anthropic = None

    async def decide_action(self, game_state: dict, round_num: int, max_rounds: int) -> str:
        """Ask LLM what action to take as the detective."""

        characters = game_state.get("characters", [])
        clues = [c for c in game_state.get("clues", []) if c.get("discovered")]
        scene = game_state.get("scene", "")
        tension = game_state.get("tension", 0)
        available_scenes = game_state.get("available_scenes", [])
        phase = game_state.get("phase", "")

        self.visited_scenes.add(scene)
        self.clue_count = len(clues)

        # Characters at current scene with mood/trust/suspicion
        chars_here = []
        chars_elsewhere = []
        for ch in characters:
            loc = ch.get("location", "")
            name = ch["name"]
            role = ch["public_role"]
            mood = ch.get("mood", "neutral")
            trust = ch.get("trust_to_player", 50)
            suspicion = ch.get("suspicion", 30)
            mood_labels = {
                "desperate": "绝望", "angry": "愤怒", "fearful": "恐惧",
                "nervous": "紧张", "calm": "冷静", "guarded": "警惕", "neutral": "正常"
            }
            mood_cn = mood_labels.get(mood, mood)
            info = f"{name}（{role}，{mood_cn}，信任{trust}/嫌疑{suspicion}）"

            if loc and (loc in scene or scene.endswith(loc)):
                chars_here.append(info)
                self.talked_to.add(name)
            else:
                chars_elsewhere.append(f"{name}在{loc}")

        # Which scenes haven't been visited
        unvisited = [s for s in available_scenes if s not in self.visited_scenes]

        # Recent interaction history (include NPC responses, not just actions)
        recent_log = []
        for entry in self._recent_events[-8:]:
            recent_log.append(entry)

        strategy_instruction = {
            "thorough": (
                "你是一个经验丰富的侦探。系统地调查：\n"
                "1. 每到一个新场景，先仔细搜查环境（翻抽屉、看角落、检查物品）\n"
                "2. 和在场的每个人对话，追问可疑之处\n"
                "3. 发现线索后，拿线索去质问相关的嫌疑人\n"
                "4. 优先去还没探索的场景"
            ),
            "aggressive": (
                "你是一个咄咄逼人的侦探。直接切入要害：\n"
                "1. 当面质问NPC，追问他们的矛盾之处\n"
                "2. 用已有线索诈唬他们，看他们的反应\n"
                "3. 翻他们的私人物品（手机、口袋、包）\n"
                "4. 不给他们喘息的机会，连续追问"
            ),
            "random": (
                "你是一个行为不可预测的侦探。做些意想不到的事：\n"
                "1. 翻垃圾桶、敲墙壁、检查天花板、闻酒杯\n"
                "2. 突然关灯、打碎花瓶、堵住门\n"
                "3. 对NPC说些奇怪的话，观察反应\n"
                "4. 尝试一些游戏可能没考虑到的行为"
            ),
            "speedrun": (
                "你是一个追求效率的侦探。快速通关：\n"
                "1. 直奔书房搜查抽屉和文件\n"
                "2. 去酒窖搜查深处\n"
                "3. 用发现的证据直接质问嫌疑人\n"
                "4. 尽早发起公开对峙"
            ),
        }.get(self.strategy, "thorough")

        # Build context-aware action suggestions (mimicking QuickActions)
        suggestions = self._build_suggestions(scene, chars_here, unvisited, clues, tension, round_num)

        # Late-game nudge
        late_game_hint = ""
        if round_num >= max_rounds - 3:
            late_game_hint = (
                '\n⚠ 回合快用完了！如果你觉得证据足够，可以说"发起公开对峙"进入最终投票。'
            )

        clue_texts = [f"「{c.get('text', '')[:50]}」" for c in clues[:8]]

        prompt = f"""你正在玩一款推理游戏「非剧本杀」。你扮演一位受邀来到顾家老宅的私人侦探。
顾家继承人顾言在晚宴中途神秘失踪，你需要在{max_rounds}回合内查明真相。

三位嫌疑人：
- 林岚——顾家秘书，冷静克制，似乎知道什么
- 周牧——顾言发小，表面随和，暗藏紧张
- 宋知微——记者，敏锐多疑，为何恰好在场？

━━━ 当前状态 ━━━
回合：第{round_num}轮（共{max_rounds}轮）
场景：{scene}
阶段：{phase}
紧张度：{tension}/100
已发现线索：{len(clues)}条

━━━ 你身边的人 ━━━
{chr(10).join(chars_here) if chars_here else '当前场景无人'}
{('其他人：' + '、'.join(chars_elsewhere)) if chars_elsewhere else ''}

━━━ 已有线索 ━━━
{chr(10).join(clue_texts) if clue_texts else '暂无线索——去搜查房间或和人对话吧'}

━━━ 最近发生的事 ━━━
{chr(10).join(recent_log[-6:]) if recent_log else '游戏刚开始'}

━━━ 可探索的地点 ━━━
{', '.join(available_scenes)}
{'（未去过：' + ', '.join(unvisited) + '）' if unvisited else '（全部去过）'}

━━━ 你的策略 ━━━
{strategy_instruction}

━━━ 建议行动 ━━━
{chr(10).join(f'• {s}' for s in suggestions)}
{late_game_hint}

请输出你的下一步行动。直接输出一句话，不要解释。
重要：不要只是"去某地看看"——到了就要搜查或跟人对话！"""

        action = await self._call_llm(prompt)
        # Clean up: take first line, strip quotes/whitespace
        action = action.strip().split("\n")[0].strip().strip('"').strip("'").strip()
        # Cap length to avoid absurdly long inputs
        if len(action) > 100:
            action = action[:100]
        self.action_history.append(action)
        return action

    async def _call_llm(self, prompt: str) -> str:
        if self._anthropic:
            resp = await self._anthropic.messages.create(
                model=self.config.model,
                max_tokens=100,
                temperature=0.8,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        else:
            resp = await self._openai.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=100,
            )
            return resp.choices[0].message.content.strip()

    def record_turn_result(self, action: str, result: TurnResponse):
        """Record what happened this turn so the detective has context next turn."""
        self._recent_events.append(f"[你] {action}")

        if result.system_narration:
            narr = result.system_narration[:80]
            self._recent_events.append(f"[叙述] {narr}")

        for reply in result.npc_replies:
            self._recent_events.append(f"[{reply.character_name}] {reply.text[:80]}")

        for clue in result.new_clues:
            self._recent_events.append(f"[线索发现] {clue[:60]}")

        for event in result.npc_events:
            text = event.text[:60]
            self._recent_events.append(f"[事件] {text}")

        # Keep only last 20 entries to avoid prompt bloat
        if len(self._recent_events) > 20:
            self._recent_events = self._recent_events[-20:]

    def _build_suggestions(
        self,
        scene: str,
        chars_here: list[str],
        unvisited: list[str],
        clues: list[dict],
        tension: int,
        round_num: int,
    ) -> list[str]:
        """Generate context-aware action suggestions, mimicking the game's QuickActions."""
        suggestions = []

        # Scene-specific search suggestions
        scene_short = scene.split("·")[-1] if "·" in scene else scene
        search_map = {
            "宴会厅": ["仔细观察宴会厅的每个角落", "翻翻垃圾桶和角落的杂物"],
            "书房": ["打开书桌抽屉翻翻看", "检查书房门把手上的痕迹"],
            "花园": ["搜查花园的灌木丛", "检查花园石凳附近"],
            "酒窖": ["搜查酒窖深处", "仔细听酒窖最里面有没有声音"],
            "走廊": ["检查走廊尽头的门", "观察走廊地毯上的脚印"],
        }
        if scene_short in search_map:
            suggestions.extend(search_map[scene_short][:1])

        # Character interaction suggestions
        for char_info in chars_here[:2]:
            name = char_info.split("（")[0]
            if "紧张" in char_info or "恐惧" in char_info:
                suggestions.append(f"追问{name}，他看起来很紧张")
            elif "愤怒" in char_info:
                suggestions.append(f"安抚{name}，试着让他冷静下来再说")
            else:
                suggestions.append(f"跟{name}聊聊顾言最近的状况")

        # Use evidence to confront
        if clues:
            latest_clue = clues[-1].get("text", "")[:20]
            if chars_here:
                name = chars_here[0].split("（")[0]
                suggestions.append(f"拿线索质问{name}：「{latest_clue}...」这怎么解释？")

        # Movement suggestions
        if unvisited:
            suggestions.append(f"去{unvisited[0]}看看")

        # High-tension special actions
        if tension >= 45:
            suggestions.append("趁林岚不注意偷看她的手机")
        if tension >= 60 and len(clues) >= 4:
            suggestions.append("检查失踪现场是否有人为布置的痕迹")
        if round_num >= 12 and len(clues) >= 3:
            suggestions.append("发起公开对峙")

        return suggestions[:5]  # max 5 suggestions


# ─── Issue Detector ───────────────────────────────────────────────────

class IssueDetector:
    """Watches every turn for narrative problems."""

    # Valid locations in the Gu Family case
    VALID_LOCATIONS = {"宴会厅", "书房", "花园", "酒窖", "走廊", "顾家老宅"}
    VALID_CHARACTERS = {"林岚", "周牧", "宋知微", "顾言"}

    # Words that suggest wrong-setting hallucination
    BANNED_SETTING_WORDS = {"城堡", "庄园", "教堂", "图书馆", "博物馆", "宫殿", "神殿", "地牢"}

    # Hard boundary keywords — NPCs should never reveal these unprompted
    LEAKAGE_PATTERNS = {
        "linlan": [
            re.compile(r"遗嘱副本"),
            re.compile(r"按计划行动"),
            re.compile(r"顾言.*委托.*转移"),
            re.compile(r"自导自演"),
        ],
        "zhoumu": [
            re.compile(r"遗嘱.*修改"),
            re.compile(r"捐.*基金会"),
            re.compile(r"我.*去.*酒窖"),
            re.compile(r"承认.*争吵.*遗产"),
        ],
        "songzhi": [
            re.compile(r"匿名信"),
            re.compile(r"匿名.*爆料"),
            re.compile(r"提前.*知道.*出事"),
            re.compile(r"我的.*信息源"),
        ],
    }

    def __init__(self):
        self.issues: list[Issue] = []
        self.npc_statements: dict[str, list[dict]] = {}  # char_id -> [{round, text}]
        self.turn_records: list[TurnRecord] = []
        self._stuck_counter = 0
        self._last_clue_count = 0
        self._last_scene = ""
        self._last_tension = 0

    def check_turn(
        self,
        round_num: int,
        action: str,
        result: TurnResponse,
        state: GameState,
    ) -> list[Issue]:
        """Run all checks on a completed turn. Returns new issues found."""
        turn_issues: list[Issue] = []

        # Record turn
        record = TurnRecord(
            round=round_num,
            action=action,
            director_note=result.director_note,
            npc_replies=[(r.character_id, r.character_name, r.text) for r in result.npc_replies],
            new_clues=list(result.new_clues),
            scene=result.scene,
            tension=result.tension,
            phase=result.phase,
        )
        self.turn_records.append(record)

        # Collect NPC statements
        for reply in result.npc_replies:
            cid = reply.character_id
            if cid not in self.npc_statements:
                self.npc_statements[cid] = []
            self.npc_statements[cid].append({
                "round": round_num,
                "text": reply.text,
                "action": action,
            })

        # --- Check 1: Empty or very short NPC responses ---
        turn_issues.extend(self._check_empty_responses(round_num, result))

        # --- Check 2: Information leakage (hard boundary violations) ---
        turn_issues.extend(self._check_information_leakage(round_num, result))

        # --- Check 3: Narrative inconsistency (wrong locations/settings) ---
        turn_issues.extend(self._check_narrative_inconsistency(round_num, result))

        # --- Check 4: NPC self-contradiction ---
        turn_issues.extend(self._check_contradictions(round_num, result))

        # --- Check 5: Dead ends (stuck detection) ---
        turn_issues.extend(self._check_dead_end(round_num, result, state))

        # --- Check 6: Tension anomalies ---
        turn_issues.extend(self._check_tension_anomaly(round_num, result))

        # --- Check 7: Character identity confusion ---
        turn_issues.extend(self._check_character_confusion(round_num, result))

        self._last_scene = result.scene
        self._last_tension = result.tension

        self.issues.extend(turn_issues)
        return turn_issues

    def _check_empty_responses(self, round_num: int, result: TurnResponse) -> list[Issue]:
        issues = []
        for reply in result.npc_replies:
            text = reply.text.strip()
            if not text:
                issues.append(Issue(
                    round=round_num,
                    category="empty_response",
                    severity="critical",
                    description=f"{reply.character_name} gave an empty response",
                    context=f"character_id={reply.character_id}",
                ))
            elif len(text) < 5:
                issues.append(Issue(
                    round=round_num,
                    category="empty_response",
                    severity="warning",
                    description=f"{reply.character_name} gave a suspiciously short response ({len(text)} chars)",
                    context=f"text={text!r}",
                ))
        if not result.director_note.strip():
            issues.append(Issue(
                round=round_num,
                category="empty_response",
                severity="warning",
                description="Director note is empty",
            ))
        return issues

    def _check_information_leakage(self, round_num: int, result: TurnResponse) -> list[Issue]:
        issues = []
        for reply in result.npc_replies:
            cid = reply.character_id
            patterns = self.LEAKAGE_PATTERNS.get(cid, [])
            for pat in patterns:
                if pat.search(reply.text):
                    # Check if this is early in the game (low tension = more suspicious)
                    severity = "critical" if result.tension < 40 else "warning"
                    issues.append(Issue(
                        round=round_num,
                        category="leakage",
                        severity=severity,
                        description=(
                            f"{reply.character_name} may have leaked restricted info "
                            f"(matched: {pat.pattern!r})"
                        ),
                        context=f"tension={result.tension}, text={reply.text[:80]}...",
                    ))
        return issues

    def _check_narrative_inconsistency(self, round_num: int, result: TurnResponse) -> list[Issue]:
        issues = []
        # Check all text fields for banned setting words
        all_text = result.director_note + " " + result.system_narration
        for reply in result.npc_replies:
            all_text += " " + reply.text
        for event in result.npc_events:
            all_text += " " + event.text

        for word in self.BANNED_SETTING_WORDS:
            if word in all_text:
                issues.append(Issue(
                    round=round_num,
                    category="inconsistency",
                    severity="warning",
                    description=f"Hallucinated setting word '{word}' found in narrative",
                    context=f"The game is set in 顾家老宅, not a {word}",
                ))

        # Check for mentions of non-existent characters
        # Simple heuristic: look for common names that aren't in the cast
        fake_names = {"张三", "李四", "王五", "赵六", "陈七"}
        for name in fake_names:
            if name in all_text:
                issues.append(Issue(
                    round=round_num,
                    category="inconsistency",
                    severity="critical",
                    description=f"Non-existent character '{name}' mentioned in narrative",
                    context=all_text[:100],
                ))

        return issues

    def _check_contradictions(self, round_num: int, result: TurnResponse) -> list[Issue]:
        """Detect if an NPC said something that directly contradicts a previous statement."""
        issues = []

        # Simple contradiction patterns: pairs of phrases that contradict each other
        contradiction_pairs = [
            (r"我昨晚.{0,10}没.*离开", r"我昨晚.{0,10}去了"),
            (r"我不认识", r"我.*很.*熟"),
            (r"我没有.*看到", r"我.*看到了"),
            (r"我.*不知道.*遗嘱", r"遗嘱.*的事"),
            (r"我.*没去过.*酒窖", r"我.*在.*酒窖"),
            (r"我.*没去过.*书房", r"我.*在.*书房"),
            (r"我.*信任.*顾言", r"我.*恨.*顾言"),
        ]

        for reply in result.npc_replies:
            cid = reply.character_id
            prev_statements = self.npc_statements.get(cid, [])

            for prev in prev_statements:
                # Skip current round (already added above)
                if prev["round"] == round_num:
                    continue

                for pat_a, pat_b in contradiction_pairs:
                    re_a = re.compile(pat_a)
                    re_b = re.compile(pat_b)
                    # Check if prev matches A and current matches B (or vice versa)
                    if (re_a.search(prev["text"]) and re_b.search(reply.text)) or \
                       (re_b.search(prev["text"]) and re_a.search(reply.text)):
                        issues.append(Issue(
                            round=round_num,
                            category="contradiction",
                            severity="critical",
                            description=(
                                f"{reply.character_name} contradicted themselves: "
                                f"round {prev['round']} vs round {round_num}"
                            ),
                            context=(
                                f"Before (R{prev['round']}): {prev['text'][:60]}... | "
                                f"Now (R{round_num}): {reply.text[:60]}..."
                            ),
                        ))
        return issues

    def _check_dead_end(self, round_num: int, result: TurnResponse, state: GameState) -> list[Issue]:
        """Detect if player is stuck: no new clues, same scene, no tension change for 3+ turns."""
        issues = []
        discovered = sum(1 for c in state.clues if c.discovered)

        same_scene = result.scene == self._last_scene
        same_tension = abs(result.tension - self._last_tension) <= 2
        no_new_clues = discovered == self._last_clue_count

        if same_scene and same_tension and no_new_clues and not result.new_clues:
            self._stuck_counter += 1
        else:
            self._stuck_counter = 0

        self._last_clue_count = discovered

        if self._stuck_counter >= 3:
            issues.append(Issue(
                round=round_num,
                category="dead_end",
                severity="warning",
                description=(
                    f"Player appears stuck for {self._stuck_counter} consecutive turns "
                    f"(no new clues, same scene, stable tension)"
                ),
                context=f"scene={result.scene}, tension={result.tension}, clues={discovered}",
            ))

        return issues

    def _check_tension_anomaly(self, round_num: int, result: TurnResponse) -> list[Issue]:
        """Detect extreme tension jumps or drops."""
        issues = []
        if round_num <= 1:
            return issues

        delta = result.tension - self._last_tension
        if abs(delta) > 30:
            issues.append(Issue(
                round=round_num,
                category="inconsistency",
                severity="warning",
                description=f"Tension jumped by {delta:+d} in a single turn ({self._last_tension} -> {result.tension})",
                context="Extreme tension swings may break immersion",
            ))

        return issues

    def _check_character_confusion(self, round_num: int, result: TurnResponse) -> list[Issue]:
        """Detect if an NPC speaks as if they are a different character."""
        issues = []
        identity_map = {
            "linlan": ("林岚", {"周牧", "宋知微"}),
            "zhoumu": ("周牧", {"林岚", "宋知微"}),
            "songzhi": ("宋知微", {"林岚", "周牧"}),
        }

        for reply in result.npc_replies:
            cid = reply.character_id
            if cid not in identity_map:
                continue
            own_name, other_names = identity_map[cid]
            # Check if NPC refers to itself by another character's name
            # e.g. 林岚 saying "我是周牧"
            for other in other_names:
                if f"我是{other}" in reply.text or f"我叫{other}" in reply.text:
                    issues.append(Issue(
                        round=round_num,
                        category="inconsistency",
                        severity="critical",
                        description=f"{own_name} ({cid}) claims to be {other} — identity confusion",
                        context=reply.text[:80],
                    ))

        return issues


# ─── Report generator ─────────────────────────────────────────────────

def print_report(
    detector: IssueDetector,
    rounds_played: int,
    max_rounds: int,
    strategy: str,
    elapsed_total: float,
    game_over: bool,
    ending: Optional[str],
):
    """Print a formatted playtest report."""

    print()
    print(f"{C.BOLD}{'=' * 64}{C.RESET}")
    print(f"{C.BOLD}  PLAYTEST REPORT{C.RESET}")
    print(f"{'=' * 64}")
    print()

    # Summary
    print(f"  Strategy       : {C.CYAN}{strategy}{C.RESET}")
    print(f"  Rounds played  : {C.CYAN}{rounds_played}/{max_rounds}{C.RESET}")
    print(f"  Total time     : {C.CYAN}{elapsed_total:.1f}s{C.RESET} ({elapsed_total/max(rounds_played,1):.1f}s/turn avg)")
    print(f"  Game ended     : {C.GREEN if game_over else C.YELLOW}{'Yes' if game_over else 'No (ran out of rounds)'}{C.RESET}")
    if ending:
        print(f"  Ending         : {C.MAGENTA}{ending}{C.RESET}")
    print()

    # Clue progression
    clue_counts = [r.new_clues for r in detector.turn_records]
    total_clues_found = sum(len(c) for c in clue_counts)
    print(f"  Clues found    : {C.CYAN}{total_clues_found}{C.RESET}")

    # Scenes visited
    scenes_visited = set(r.scene for r in detector.turn_records)
    print(f"  Scenes visited : {C.CYAN}{', '.join(scenes_visited)}{C.RESET}")

    # Tension arc
    tensions = [r.tension for r in detector.turn_records]
    if tensions:
        print(f"  Tension arc    : {tensions[0]} -> {tensions[-1]} (min={min(tensions)}, max={max(tensions)})")

    # NPCs talked to
    npcs_seen = set()
    for r in detector.turn_records:
        for cid, cname, _ in r.npc_replies:
            npcs_seen.add(cname)
    print(f"  NPCs engaged   : {C.CYAN}{', '.join(npcs_seen) if npcs_seen else 'None'}{C.RESET}")

    # Issue summary
    print()
    critical = [i for i in detector.issues if i.severity == "critical"]
    warnings = [i for i in detector.issues if i.severity == "warning"]
    infos = [i for i in detector.issues if i.severity == "info"]

    total_issues = len(detector.issues)
    if total_issues == 0:
        print(f"  {C.GREEN}No issues found. Clean playtest!{C.RESET}")
    else:
        print(f"  Issues found   : {C.BOLD}{total_issues}{C.RESET}")
        if critical:
            print(f"    {C.RED}CRITICAL : {len(critical)}{C.RESET}")
        if warnings:
            print(f"    {C.YELLOW}WARNING  : {len(warnings)}{C.RESET}")
        if infos:
            print(f"    {C.DIM}INFO     : {len(infos)}{C.RESET}")

    # Detailed issues
    if detector.issues:
        print()
        print(f"  {C.BOLD}--- Issue Details ---{C.RESET}")

        by_category: dict[str, list[Issue]] = {}
        for issue in detector.issues:
            by_category.setdefault(issue.category, []).append(issue)

        category_labels = {
            "contradiction": "NPC Self-Contradiction",
            "leakage": "Information Leakage",
            "inconsistency": "Narrative Inconsistency",
            "dead_end": "Dead End / Player Stuck",
            "empty_response": "Empty/Short Response",
            "error": "Runtime Error",
        }

        for cat, cat_issues in by_category.items():
            label = category_labels.get(cat, cat)
            print()
            print(f"  {C.BOLD}[{label}]{C.RESET} ({len(cat_issues)} occurrences)")
            for issue in cat_issues:
                sev_color = {
                    "critical": C.RED,
                    "warning": C.YELLOW,
                    "info": C.DIM,
                }.get(issue.severity, C.WHITE)
                print(f"    {sev_color}R{issue.round} [{issue.severity.upper()}]{C.RESET} {issue.description}")
                if issue.context:
                    print(f"       {C.DIM}{issue.context}{C.RESET}")

    # Turn-by-turn summary
    print()
    print(f"  {C.BOLD}--- Turn Log ---{C.RESET}")
    for r in detector.turn_records:
        clue_indicator = f" +{len(r.new_clues)} clue(s)" if r.new_clues else ""
        npc_names = ", ".join(cname for _, cname, _ in r.npc_replies) if r.npc_replies else "no NPC"
        err = f" {C.RED}ERR{C.RESET}" if r.error else ""
        print(
            f"    {C.DIM}R{r.round:02d}{C.RESET} "
            f"T={r.tension:3d} "
            f"{C.BLUE}{r.scene:15s}{C.RESET} "
            f"{r.action[:30]:30s} "
            f"-> {npc_names}"
            f"{C.GREEN}{clue_indicator}{C.RESET}{err}"
        )

    print()
    print(f"{'=' * 64}")

    # Exit code hint
    if critical:
        print(f"  {C.RED}RESULT: FAIL ({len(critical)} critical issues){C.RESET}")
    elif warnings:
        print(f"  {C.YELLOW}RESULT: PASS WITH WARNINGS ({len(warnings)} warnings){C.RESET}")
    else:
        print(f"  {C.GREEN}RESULT: PASS{C.RESET}")
    print(f"{'=' * 64}")
    print()


# ─── Main playtest runner ────────────────────────────────────────────

async def run_playtest(strategy: str = "thorough", max_rounds: int = 20):
    """Run a full automated playtest."""

    config = Config()
    if config.provider == LLMProvider.FALLBACK:
        print(f"{C.RED}ERROR: Playtest requires an LLM provider.{C.RESET}")
        print("Set LLM_API_KEY (+ LLM_BASE_URL, LLM_MODEL) or ANTHROPIC_API_KEY.")
        sys.exit(1)

    engine = TurnEngine(config)
    detective = PlaytestDetective(config, strategy)
    detector = IssueDetector()

    # Create session
    session_id = "playtest-auto-001"
    state = create_initial_state(session_id)
    sessions[session_id] = state
    engine.init_world(session_id)

    print()
    print(f"{C.BOLD}{'=' * 64}{C.RESET}")
    print(f"{C.BOLD}  AUTO PLAYTEST: {state.title}{C.RESET}")
    print(f"{'=' * 64}")
    print(f"  Provider  : {config.provider.value}")
    print(f"  Model     : {config.model}")
    print(f"  Strategy  : {strategy}")
    print(f"  Max rounds: {max_rounds}")
    print(f"{'=' * 64}")
    print()

    total_start = time.time()
    rounds_played = 0

    for round_num in range(1, max_rounds + 1):
        if state.game_over:
            break

        rounds_played = round_num

        # Get redacted state for the detective (same view as a real player)
        visible_state = redact_game_state(state)

        # Detective decides action
        try:
            action = await detective.decide_action(visible_state, round_num, max_rounds)
        except Exception as e:
            print(f"  {C.RED}[R{round_num}] Detective LLM error: {e}{C.RESET}")
            detector.issues.append(Issue(
                round=round_num,
                category="error",
                severity="critical",
                description=f"Detective LLM call failed: {e}",
            ))
            break

        # Print action
        print(f"  {C.BOLD}[Round {round_num:02d}]{C.RESET} {C.CYAN}Detective:{C.RESET} {action}")

        # Process turn through the engine
        turn_start = time.time()
        try:
            result = await engine.process_turn(session_id, action)
            turn_ms = int((time.time() - turn_start) * 1000)

            # Print key results
            print(f"           {C.DIM}Scene: {result.scene} | Tension: {result.tension} | Phase: {result.phase}{C.RESET}")

            if result.director_note:
                note_preview = result.director_note[:80]
                if len(result.director_note) > 80:
                    note_preview += "..."
                print(f"           {C.YELLOW}DM: {note_preview}{C.RESET}")

            for reply in result.npc_replies:
                text_preview = reply.text[:60]
                if len(reply.text) > 60:
                    text_preview += "..."
                print(f"           {C.MAGENTA}{reply.character_name}: {text_preview}{C.RESET}")

            for event in result.npc_events:
                event_preview = event.text[:60]
                if len(event.text) > 60:
                    event_preview += "..."
                print(f"           {C.DIM}[Event] {event_preview}{C.RESET}")

            if result.new_clues:
                for clue in result.new_clues:
                    clue_preview = clue[:60] + ("..." if len(clue) > 60 else "")
                    print(f"           {C.GREEN}[Clue] {clue_preview}{C.RESET}")

            if result.system_narration:
                narr_preview = result.system_narration[:60]
                if len(result.system_narration) > 60:
                    narr_preview += "..."
                print(f"           {C.BLUE}[Narration] {narr_preview}{C.RESET}")

            print(f"           {C.DIM}({turn_ms}ms){C.RESET}")

            # Record turn result for detective context
            detective.record_turn_result(action, result)

            # Refresh state from sessions dict (engine mutates it in-place)
            state = sessions[session_id]

            # Run issue detection
            turn_issues = detector.check_turn(round_num, action, result, state)
            for issue in turn_issues:
                sev_color = C.RED if issue.severity == "critical" else C.YELLOW
                print(f"           {sev_color}[ISSUE:{issue.category}] {issue.description}{C.RESET}")

            # Update turn record with timing
            if detector.turn_records:
                detector.turn_records[-1].elapsed_ms = turn_ms

            # Check game over
            if result.game_over:
                print()
                print(f"  {C.GREEN}{C.BOLD}Game Over!{C.RESET} Ending: {result.ending or 'unknown'}")
                break

        except Exception as e:
            turn_ms = int((time.time() - turn_start) * 1000)
            print(f"           {C.RED}ERROR: {e}{C.RESET} ({turn_ms}ms)")
            detector.issues.append(Issue(
                round=round_num,
                category="error",
                severity="critical",
                description=f"Turn processing exception: {e}",
                context=f"action={action!r}",
            ))
            detector.turn_records.append(TurnRecord(
                round=round_num,
                action=action,
                error=str(e),
                elapsed_ms=turn_ms,
            ))

        print()  # blank line between rounds

    total_elapsed = time.time() - total_start

    # Print the final report
    print_report(
        detector=detector,
        rounds_played=rounds_played,
        max_rounds=max_rounds,
        strategy=strategy,
        elapsed_total=total_elapsed,
        game_over=state.game_over,
        ending=state.ending,
    )

    # Return exit code based on severity
    critical_count = sum(1 for i in detector.issues if i.severity == "critical")
    return 1 if critical_count > 0 else 0


# ─── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Auto Playtest -- LLM plays as detective to find narrative bugs."
    )
    parser.add_argument(
        "--strategy",
        default="thorough",
        choices=["thorough", "aggressive", "random", "speedrun"],
        help="Detective play strategy (default: thorough)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=20,
        help="Maximum number of rounds to play (default: 20)",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_playtest(args.strategy, args.rounds))
    sys.exit(exit_code)
