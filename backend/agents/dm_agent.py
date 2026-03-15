"""
DM (Dungeon Master) Agent — the central coordinator that sits ABOVE all expert agents.

In a sandbox interactive mystery game with 15+ specialized agents, multiple agents
can generate conflicting outputs simultaneously: Story Architect says "slow down"
while Conspiracy Agent triggers a dramatic betrayal, Psychology Agent fires a
breakdown, and NPC Autonomy has 3 characters acting at once.  The result is chaos.

The DM Agent receives ALL agent proposals for a given turn and outputs a single
coherent ``DMDirective`` — the final, authoritative decision on what actually
happens this turn.

Architecture position::

    All expert agents generate proposals
            |
       [DM Agent] -- receives everything, decides what actually happens
            |
       Final TurnResponse to player

Usage:
    dm = DMAgent(config)
    proposals = AgentProposals(
        action_narration="...",
        architect_events=["..."],
        breaking_points={"linlan": "emotional_breakdown"},
        betrayal_events=["..."],
        ...
    )
    directive = await dm.adjudicate(proposals, session_id="abc123")
    # directive.approved_events, directive.system_narration, etc.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import Config, LLMProvider


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AgentProposals(BaseModel):
    """Collected proposals from all expert agents for this turn."""

    # From Open Action Engine
    action_narration: str = ""
    action_category: str = ""
    action_feasible: bool = True
    action_tension_delta: int = 0

    # From Story Architect
    current_act: int = 1
    current_beat: str = "setup"
    pacing: str = "sustain"                # accelerate / sustain / slow_down / climax
    architect_director_note: str = ""
    architect_narration: str = ""
    architect_events: List[str] = Field(default_factory=list)
    hint_level: str = "none"

    # From Tension Conductor
    tension_adjusted_delta: int = 0
    tension_atmosphere: str = "calm"

    # From NPC Autonomy
    visible_npc_actions: List[str] = Field(default_factory=list)
    hidden_npc_actions: List[str] = Field(default_factory=list)
    npc_evidence: List[str] = Field(default_factory=list)

    # From Psychology
    breaking_points: Dict[str, str] = Field(default_factory=dict)
    psych_directives: Dict[str, dict] = Field(default_factory=dict)

    # From Conspiracy
    conspiracy_events: List[str] = Field(default_factory=list)
    betrayal_events: List[str] = Field(default_factory=list)

    # Game state context
    round_num: int = 1
    max_rounds: int = 20
    tension: int = 20
    phase: str = "\u81ea\u7531\u8bd5\u63a2"
    discovered_clues: int = 0
    total_clues: int = 6
    player_action: str = ""
    stuck_turns: int = 0
    act_reveal_count: int = 0
    reveal_budget: int = 0
    reveal_budget_remaining: int = 0
    event_cooldowns: Dict[str, int] = Field(default_factory=dict)
    recent_high_intensity_turns: int = 0
    stuck_recovery_level: int = 0


class DMDirective(BaseModel):
    """The DM's final decision for this turn."""

    # Narration control
    system_narration: str              # Final narration text (Chinese)
    director_note: str                 # Final atmospheric note (Chinese)

    # Event control -- DM picks which events actually happen
    approved_events: List[str] = Field(default_factory=list)    # Max 2
    suppressed_events: List[str] = Field(default_factory=list)
    deferred_events: List[str] = Field(default_factory=list)

    # Tension control
    final_tension_delta: int = 0

    # Pacing control
    turn_mood: str = "neutral"         # calm / building / tense / explosive / aftermath
    allow_clue_discovery: bool = True

    # NPC control
    npc_visibility: Dict[str, bool] = Field(default_factory=dict)
    force_npc_reaction: Optional[str] = None

    # Hint control
    hint_text: Optional[str] = None

    # Special directives
    inject_twist: Optional[str] = None
    atmosphere_override: Optional[str] = None

    # Meta
    dm_reasoning: str = ""


# ---------------------------------------------------------------------------
# Hint pools (Chinese, contextual to the Gu family case)
# ---------------------------------------------------------------------------

LOW_HINTS: List[str] = [
    "\u58c1\u7089\u7684\u706b\u5149\u6620\u7167\u7740\u5899\u4e0a\u7684\u5168\u5bb6\u798f\uff0c\u4f60\u6ce8\u610f\u5230\u7167\u7247\u91cc\u987e\u8a00\u7684\u7b11\u5bb9\u6709\u4e9b\u52c9\u5f3a\u3002",
    "\u8001\u5b85\u7684\u7a7a\u6c14\u4e2d\u4f3c\u4e4e\u6b8b\u7559\u7740\u4ec0\u4e48\u2014\u2014\u4e0d\u662f\u7070\u5c18\uff0c\u66f4\u50cf\u662f\u67d0\u79cd\u79d8\u5bc6\u7684\u6c14\u5473\u3002",
    "\u4f60\u603b\u89c9\u5f97\u8fd9\u680b\u623f\u5b50\u91cc\u6709\u4e9b\u5730\u65b9\u8fd8\u6ca1\u6709\u63a2\u7d22\u8fc7\u2026\u2026",
    "\u7a97\u5916\u7684\u96e8\u8d8a\u4e0b\u8d8a\u5927\uff0c\u6709\u4e9b\u58f0\u97f3\u88ab\u63a9\u76d6\u4f4f\u4e86\u3002",
    "\u65f6\u949f\u7684\u6ef4\u7b54\u58f0\u5728\u7a7a\u65f7\u7684\u8d70\u5eca\u91cc\u683c\u5916\u6e05\u6670\u2014\u2014\u63d0\u9192\u4f60\u65f6\u95f4\u5728\u6d41\u901d\u3002",
]

MID_HINTS: List[str] = [
    "\u4f60\u6ce8\u610f\u5230\u6797\u5c9a\u6bcf\u9694\u4e00\u4f1a\u513f\u5c31\u4f1a\u770b\u5411\u8d70\u5eca\u7684\u65b9\u5411\u2014\u2014\u90a3\u91cc\u901a\u5f80\u9152\u7a96\u3002",
    "\u5468\u7267\u63d0\u5230\u6628\u665a\u65f6\uff0c\u4ed6\u7684\u624b\u4e0d\u81ea\u89c9\u5730\u6478\u4e86\u6478\u53e3\u888b\u91cc\u7684\u4e1c\u897f\u3002",
    "\u5b8b\u77e5\u5fae\u7684\u8868\u60c5\u544a\u8bc9\u4f60\uff0c\u5979\u53ef\u80fd\u77e5\u9053\u4e00\u4e9b\u4f60\u8fd8\u4e0d\u77e5\u9053\u7684\u4e8b\u3002",
    "\u6709\u4eba\u5728\u8bf4\u8c0e\u2014\u2014\u800c\u8bf4\u8c0e\u7684\u4eba\u603b\u4f1a\u5728\u67d0\u4e9b\u7ec6\u8282\u4e0a\u81ea\u76f8\u77db\u76fe\u3002",
    "\u4e5f\u8bb8\u6362\u4e2a\u5730\u65b9\u627e\u627e\u4f1a\u6709\u65b0\u7684\u53d1\u73b0\u3002\u4e66\u623f\u548c\u9152\u7a96\u4f3c\u4e4e\u90fd\u503c\u5f97\u4ed4\u7ec6\u770b\u770b\u3002",
]

HIGH_HINTS: List[str] = [
    "\u4f60\u9690\u7ea6\u542c\u5230\u9152\u7a96\u65b9\u5411\u4f20\u6765\u5fae\u5f31\u7684\u58f0\u54cd\u2014\u2014\u8fd9\u4e0d\u6b63\u5e38\u3002",
    "\u6797\u5c9a\u4f3c\u4e4e\u5728\u9690\u7792\u5173\u4e8e\u4e66\u623f\u7684\u4ec0\u4e48\u4e8b\u60c5\u2014\u2014\u4e5f\u8bb8\u8be5\u53bb\u90a3\u91cc\u627e\u627e\u3002",
    "\u8fd9\u6574\u4ef6\u4e8b\u4ece\u5934\u5230\u5c3e\u90fd\u900f\u7740\u8e4a\u8df7\u2014\u2014\u4f1a\u4e0d\u4f1a\u6839\u672c\u5c31\u6ca1\u6709\u72af\u7f6a\uff1f",
    "\u987e\u8a00\u5931\u8e2a\u7684\u65b9\u5f0f\u592a\u5e72\u51c0\u4e86\u2014\u2014\u50cf\u662f\u6709\u4eba\u7cbe\u5fc3\u7b56\u5212\u7684\u3002",
    "\u9152\u7a96\u7684\u6df1\u5904\uff0c\u4f3c\u4e4e\u6709\u4ec0\u4e48\u88ab\u9057\u5fd8\u7684\u89d2\u843d\u7b49\u5f85\u88ab\u53d1\u73b0\u3002",
]

# ---------------------------------------------------------------------------
# Twist pool (Chinese, rare events)
# ---------------------------------------------------------------------------

TWIST_POOL: List[str] = [
    "\u4f60\u7684\u624b\u673a\u7a81\u7136\u6536\u5230\u4e00\u6761\u533f\u540d\u77ed\u4fe1\uff1a\u2018\u522b\u76f8\u4fe1\u4efb\u4f55\u4eba\u3002\u2014\u2014\u4e00\u4e2a\u670b\u53cb\u2019",
    "\u8d70\u5eca\u5c3d\u5934\u7684\u706f\u7a81\u7136\u706d\u4e86\uff0c\u51e0\u79d2\u540e\u91cd\u65b0\u4eae\u8d77\u2014\u2014\u4f46\u4f60\u786e\u5b9a\u6709\u4ec0\u4e48\u4e1c\u897f\u79fb\u52a8\u8fc7\u3002",
    "\u4f60\u6ce8\u610f\u5230\u82b1\u56ed\u7684\u77f3\u51f3\u4e0b\u9762\u591a\u4e86\u4e00\u4e2a\u4e4b\u524d\u6ca1\u6709\u7684\u4fe1\u5c01\u3002",
    "\u7ba1\u5bb6\u7a81\u7136\u51fa\u73b0\u5728\u8d70\u5eca\u4e0a\uff0c\u6b32\u8a00\u53c8\u6b62\u5730\u770b\u4e86\u4f60\u4e00\u773c\uff0c\u7136\u540e\u5feb\u6b65\u79bb\u5f00\u4e86\u3002",
    "\u4f60\u65e0\u610f\u4e2d\u542c\u5230\u624b\u673a\u94c3\u58f0\u4ece\u9152\u7a96\u65b9\u5411\u4f20\u6765\u2014\u2014\u4f46\u6240\u6709\u4eba\u90fd\u5728\u8fd9\u91cc\u3002",
]

# ---------------------------------------------------------------------------
# LLM system prompt (Chinese)
# ---------------------------------------------------------------------------

DM_SYSTEM_PROMPT = """\u4f60\u662f\u4e00\u4e2a\u4e92\u52a8\u63a8\u7406\u6e38\u620f\u7684DM\uff08\u4e3b\u6301\u4eba/\u5bfc\u6f14\uff09\u3002\u4f60\u7684\u4efb\u52a1\u662f\u534f\u8c03\u6240\u6709AI\u4ee3\u7406\u7684\u8f93\u51fa\uff0c\
\u786e\u4fdd\u73a9\u5bb6\u83b7\u5f97\u6700\u4f73\u4f53\u9a8c\u3002

\u4f60\u7684\u6838\u5fc3\u539f\u5219\uff1a
1. \u6bcf\u56de\u5408\u6700\u591a\u53d1\u751f2\u4ef6\u91cd\u5927\u4e8b\u4ef6\uff08\u591a\u4e86\u73a9\u5bb6\u6d88\u5316\u4e0d\u4e86\uff09
2. \u8282\u594f\u50cf\u547c\u5438\u2014\u2014\u6709\u5f20\u6709\u5f1b\uff0c\u4e0d\u80fd\u4e00\u76f4\u7d27\u5f20
3. \u91cd\u8981\u7684\u63ed\u793a\u5e94\u8be5\u6709\u94fa\u57ab\uff0c\u4e0d\u8981\u7a81\u5140
4. \u4fdd\u62a4\u201c\u60ca\u559c\u65f6\u523b\u201d\u2014\u2014\u5982\u679c\u4e00\u4e2a\u91cd\u5927\u4e8b\u4ef6\u8981\u53d1\u751f\uff0c\u786e\u4fdd\u4e4b\u524d\u6709\u8db3\u591f\u7684\u94fa\u57ab
5. \u73a9\u5bb6\u7684\u884c\u52a8\u5e94\u8be5\u662f\u7126\u70b9\u2014\u2014NPC\u4e8b\u4ef6\u662f\u914d\u83dc\uff0c\u4e0d\u80fd\u55a7\u5bbe\u593a\u4e3b
6. \u5f53\u591a\u4e2a\u5927\u4e8b\u4ef6\u7ade\u4e89\u540c\u4e00\u56de\u5408\u65f6\uff0c\u9009\u62e9\u6700\u6709\u620f\u5267\u6027\u4e14\u6700\u5408\u65f6\u5b9c\u7684\u90a3\u4e2a
7. \u6c38\u8fdc\u4e0d\u8981\u540c\u65f6\u89e6\u53d1\u201c\u89d2\u8272\u5d29\u6e83\u201d\u548c\u201c\u8054\u76df\u80cc\u53db\u201d\u2014\u2014\u9009\u4e00\u4e2a
8. \u5982\u679c\u73a9\u5bb6\u5361\u4f4f\u4e86(stuck_turns >= 3)\uff0c\u4e3b\u52a8\u7ed9\u4e88\u63d0\u793a
9. \u5982\u679c\u73a9\u5bb6\u505a\u4e86\u521b\u610f\u884c\u4e3a\uff0c\u7ed9\u4e88\u4e30\u5bcc\u7684\u53cd\u9988\u548c\u5956\u52b1
10. \u63a7\u5236\u4fe1\u606f\u91ca\u653e\u8282\u594f\u2014\u2014\u4e0d\u8981\u4e00\u6b21\u7ed9\u592a\u591a\u7ebf\u7d22

\u4f60\u5fc5\u987b\u4ee5JSON\u683c\u5f0f\u56de\u590d\uff0c\u5305\u542b\u4ee5\u4e0b\u5b57\u6bb5\uff1a
- system_narration: \u6700\u7ec8\u53d9\u4e8b\u6587\u672c\uff08\u4e2d\u6587\uff0c\u4e0d\u8d85\u8fc7120\u5b57\uff09
- director_note: \u6c1b\u56f4\u63d0\u793a\uff08\u4e2d\u6587\uff0c\u4e0d\u8d85\u8fc760\u5b57\uff09
- approved_events: \u672c\u56de\u5408\u5b9e\u9645\u53d1\u751f\u7684\u4e8b\u4ef6\u6570\u7ec4\uff08\u6700\u591a2\u4e2a\uff09
- suppressed_events: \u88ab\u538b\u5236\u7684\u4e8b\u4ef6\u6570\u7ec4
- deferred_events: \u5ef6\u8fdf\u5230\u4ee5\u540e\u56de\u5408\u7684\u4e8b\u4ef6\u6570\u7ec4
- final_tension_delta: \u6700\u7ec8\u7d27\u5f20\u5ea6\u53d8\u5316
- turn_mood: \u56de\u5408\u60c5\u7eea\uff08calm/building/tense/explosive/aftermath\uff09
- allow_clue_discovery: \u662f\u5426\u5141\u8bb8\u53d1\u73b0\u7ebf\u7d22
- hint_text: \u7ed9\u73a9\u5bb6\u7684\u63d0\u793a\uff08\u53ef\u4e3anull\uff09
- inject_twist: \u60c5\u8282\u53cd\u8f6c\uff08\u53ef\u4e3anull\uff0c\u6781\u5c11\u4f7f\u7528\uff09
- atmosphere_override: \u6c1b\u56f4\u8986\u76d6\uff08\u53ef\u4e3anull\uff09
- dm_reasoning: \u4f60\u7684\u5185\u90e8\u63a8\u7406\u8fc7\u7a0b\uff08\u7528\u4e8e\u8c03\u8bd5\uff09"""


# ---------------------------------------------------------------------------
# DMAgent
# ---------------------------------------------------------------------------

class DMAgent:
    """
    Central coordinator that sits above all expert agents and makes final
    decisions for each turn.

    Receives an ``AgentProposals`` bundle containing recommendations from
    every expert agent and produces a single ``DMDirective`` -- the
    authoritative, coherent instruction set for the turn.

    The agent supports two paths:
    * **LLM path** (OpenAI-compatible or Anthropic) -- sends the full
      proposal context to an LLM and parses a structured JSON response.
    * **Fallback path** -- applies deterministic, rule-based logic when
      no LLM is available or the LLM call fails.

    Per-session state is tracked for mood history, twist usage, and
    deferred events.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = None

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
        elif config.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_key)

        # Per-session state
        self._previous_moods: Dict[str, List[str]] = defaultdict(list)
        self._twist_used: Dict[str, bool] = defaultdict(bool)
        self._deferred_events: Dict[str, List[str]] = defaultdict(list)
        self._used_events: Dict[str, set] = defaultdict(set)  # Track events already shown

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def adjudicate(
        self,
        proposals: AgentProposals,
        session_id: str = "default",
    ) -> DMDirective:
        """
        The main method.  Receives ALL agent proposals for a turn and
        produces a single coherent ``DMDirective``.

        Tries the LLM path first; falls back to rule-based logic on any
        failure or when the provider is ``FALLBACK``.

        Args:
            proposals:  Aggregated proposals from every expert agent.
            session_id: Game session identifier (for per-session state).

        Returns:
            A ``DMDirective`` with final decisions for the turn.
        """
        if self.config.provider != LLMProvider.FALLBACK:
            try:
                directive = await self._adjudicate_with_llm(proposals, session_id)
                self._record_mood(session_id, directive.turn_mood)
                return directive
            except Exception as e:
                print(f"[DMAgent] LLM call failed: {e}, falling back to rules")

        directive = self._adjudicate_with_rules(proposals, session_id)
        self._record_mood(session_id, directive.turn_mood)
        return directive

    # ------------------------------------------------------------------
    # LLM-based adjudication
    # ------------------------------------------------------------------

    async def _adjudicate_with_llm(
        self,
        proposals: AgentProposals,
        session_id: str,
    ) -> DMDirective:
        """Send all proposals as structured context to the LLM and parse
        the JSON response into a ``DMDirective``."""

        user_prompt = self._build_llm_prompt(proposals, session_id)

        if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": DM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=800,
            )
            raw = response.choices[0].message.content

        elif self.config.provider == LLMProvider.ANTHROPIC:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=800,
                system=DM_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.7,
            )
            raw = response.content[0].text

        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        # Parse JSON (handle possible markdown wrapping)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]
        parsed = json.loads(raw)

        return DMDirective(
            system_narration=parsed.get("system_narration", proposals.action_narration)[:120],
            director_note=parsed.get("director_note", proposals.architect_director_note)[:60],
            approved_events=parsed.get("approved_events", [])[:2],
            suppressed_events=parsed.get("suppressed_events", []),
            deferred_events=parsed.get("deferred_events", []),
            final_tension_delta=parsed.get("final_tension_delta", proposals.tension_adjusted_delta),
            turn_mood=parsed.get("turn_mood", "neutral"),
            allow_clue_discovery=parsed.get("allow_clue_discovery", True),
            npc_visibility=parsed.get("npc_visibility", {}),
            force_npc_reaction=parsed.get("force_npc_reaction"),
            hint_text=parsed.get("hint_text"),
            inject_twist=parsed.get("inject_twist"),
            atmosphere_override=parsed.get("atmosphere_override"),
            dm_reasoning=parsed.get("dm_reasoning", ""),
        )

    def _build_llm_prompt(
        self,
        proposals: AgentProposals,
        session_id: str,
    ) -> str:
        """Build the user message that describes all proposals for the LLM."""

        recent_moods = self._previous_moods.get(session_id, [])
        deferred = self._deferred_events.get(session_id, [])
        twist_used = self._twist_used.get(session_id, False)

        # Pre-compute values that cannot go inside f-string expressions
        psych_directives_str = (
            json.dumps(proposals.psych_directives, ensure_ascii=False)
            if proposals.psych_directives
            else "\u65e0"
        )
        recent_moods_slice = recent_moods[-3:] if recent_moods else []

        return (
            f"\u3010\u5f53\u524d\u56de\u5408\u72b6\u6001\u3011\n"
            f"- \u56de\u5408\uff1a{proposals.round_num}/{proposals.max_rounds}\n"
            f"- \u7d27\u5f20\u5ea6\uff1a{proposals.tension}/100\n"
            f"- \u9636\u6bb5\uff1a{proposals.phase}\n"
            f"- \u5df2\u53d1\u73b0\u7ebf\u7d22\uff1a{proposals.discovered_clues}/{proposals.total_clues}\n"
            f"- \u5f53\u5e55\u5df2\u63ed\u793a\u7ebf\u7d22\uff1a{proposals.act_reveal_count}/{proposals.reveal_budget}\n"
            f"- \u7ebf\u7d22\u9884\u7b97\u5269\u4f59\uff1a{proposals.reveal_budget_remaining}\n"
            f"- \u73a9\u5bb6\u5361\u4f4f\u56de\u5408\u6570\uff1a{proposals.stuck_turns}\n"
            f"- \u5361\u5173\u5e72\u9884\u7ea7\u522b\uff1a{proposals.stuck_recovery_level}\n"
            f"- \u73a9\u5bb6\u884c\u52a8\uff1a{proposals.player_action}\n"
            f"\n"
            f"\u3010\u884c\u52a8\u5f15\u64ce\u63d0\u8bae\u3011\n"
            f"- \u53d9\u4e8b\uff1a{proposals.action_narration}\n"
            f"- \u7c7b\u522b\uff1a{proposals.action_category}\n"
            f"- \u53ef\u884c\uff1a{proposals.action_feasible}\n"
            f"- \u7d27\u5f20\u5ea6\u53d8\u5316\uff1a{proposals.action_tension_delta}\n"
            f"\n"
            f"\u3010\u6545\u4e8b\u5efa\u7b51\u5e08\u63d0\u8bae\u3011\n"
            f"- \u5f53\u524d\u5e55\uff1a\u7b2c{proposals.current_act}\u5e55\n"
            f"- \u8282\u62cd\uff1a{proposals.current_beat}\n"
            f"- \u8282\u594f\uff1a{proposals.pacing}\n"
            f"- \u5bfc\u6f14\u624b\u8bb0\uff1a{proposals.architect_director_note}\n"
            f"- \u53d9\u4e8b\uff1a{proposals.architect_narration}\n"
            f"- \u5efa\u8bae\u4e8b\u4ef6\uff1a{proposals.architect_events}\n"
            f"- \u63d0\u793a\u7b49\u7ea7\uff1a{proposals.hint_level}\n"
            f"\n"
            f"\u3010\u7d27\u5f20\u5ea6\u6307\u6325\u5bb6\u63d0\u8bae\u3011\n"
            f"- \u8c03\u6574\u540e\u53d8\u5316\uff1a{proposals.tension_adjusted_delta}\n"
            f"- \u6c1b\u56f4\uff1a{proposals.tension_atmosphere}\n"
            f"\n"
            f"\u3010NPC\u81ea\u4e3b\u884c\u4e3a\u3011\n"
            f"- \u53ef\u89c1\u884c\u52a8\uff1a{proposals.visible_npc_actions}\n"
            f"- \u9690\u85cf\u884c\u52a8\uff1a{proposals.hidden_npc_actions}\n"
            f"- \u7559\u4e0b\u7684\u8bc1\u636e\uff1a{proposals.npc_evidence}\n"
            f"\n"
            f"\u3010\u5fc3\u7406\u4ee3\u7406\u3011\n"
            f"- \u5d29\u6e83\u70b9\uff1a{proposals.breaking_points}\n"
            f"- \u884c\u4e3a\u6307\u4ee4\uff1a{psych_directives_str}\n"
            f"\n"
            f"\u3010\u9634\u8c0b\u4ee3\u7406\u3011\n"
            f"- \u9634\u8c0b\u4e8b\u4ef6\uff1a{proposals.conspiracy_events}\n"
            f"- \u80cc\u53db\u4e8b\u4ef6\uff1a{proposals.betrayal_events}\n"
            f"\n"
            f"\u3010DM\u5386\u53f2\u72b6\u6001\u3011\n"
            f"- \u6700\u8fd1\u60c5\u7eea\u5e8f\u5217\uff1a{recent_moods_slice}\n"
            f"- \u5df2\u4f7f\u7528\u53cd\u8f6c\uff1a{twist_used}\n"
            f"- \u5ef6\u8fdf\u4e8b\u4ef6\u961f\u5217\uff1a{deferred}\n"
            f"- \u4e8b\u4ef6\u51b7\u5374\uff1a{proposals.event_cooldowns}\n"
            f"- \u6700\u8fd1\u9ad8\u5f3a\u5ea6\u56de\u5408\uff1a{proposals.recent_high_intensity_turns}\n"
            f"\n"
            f"\u8bf7\u7efc\u5408\u4ee5\u4e0a\u6240\u6709\u63d0\u8bae\uff0c\u505a\u51fa\u6700\u7ec8\u51b3\u7b56\u3002\u4ee5JSON\u683c\u5f0f\u56de\u590d\u3002"
        )

    # ------------------------------------------------------------------
    # Rule-based fallback adjudication
    # ------------------------------------------------------------------

    def _adjudicate_with_rules(
        self,
        proposals: AgentProposals,
        session_id: str,
    ) -> DMDirective:
        """Apply deterministic rules when no LLM is available."""

        reasoning_parts: List[str] = []

        # (a) Determine act-based max events
        act = proposals.current_act
        if act == 1:
            max_events = 1
        else:
            max_events = 2
        if proposals.recent_high_intensity_turns >= 2:
            max_events = 1
            reasoning_parts.append("Reduced max events due to recent high-intensity streak")

        # (a) Select events
        approved, deferred = self._select_events(proposals, max_events)
        reasoning_parts.append(
            f"Event selection: {len(approved)} approved, {len(deferred)} deferred"
        )

        # Merge with previously deferred events (inject at most 1 old deferred)
        session_deferred = self._deferred_events.get(session_id, [])
        if session_deferred and len(approved) < max_events:
            reinjected = session_deferred.pop(0)
            approved.append(reinjected)
            reasoning_parts.append(f"Re-injected deferred event: {reinjected[:30]}...")

        # Store newly deferred events
        self._deferred_events[session_id] = (
            self._deferred_events.get(session_id, []) + deferred
        )
        # Trim to prevent unbounded growth
        self._deferred_events[session_id] = self._deferred_events[session_id][:10]

        # All candidate events that were not approved
        all_candidates = self._gather_all_events(proposals)
        suppressed = [e for e in all_candidates if e not in approved and e not in deferred]

        # (b) Pacing / mood
        turn_mood = self._determine_mood(proposals, session_id)
        reasoning_parts.append(f"Mood: {turn_mood}")

        # (c) Tension override
        final_tension_delta = self._apply_tension_override(
            proposals, turn_mood, session_id
        )
        reasoning_parts.append(f"Tension delta: {final_tension_delta}")

        # (d) Hint system
        hint_text = self._generate_hint(proposals)
        if hint_text:
            reasoning_parts.append(f"Hint provided: {hint_text[:30]}...")

        # (e) Twist injection
        inject_twist = self._should_inject_twist(session_id, proposals)
        if inject_twist:
            reasoning_parts.append("Twist injected!")

        # (f) Narration assembly
        system_narration, director_note, atmosphere_override = (
            self._assemble_narration(proposals, hint_text)
        )

        # (g) NPC visibility
        npc_visibility = self._determine_npc_visibility(proposals)

        # Clue discovery control: suppress in Act 1 if pacing says slow_down
        allow_clue_discovery = True
        if act == 1 and proposals.pacing == "slow_down":
            allow_clue_discovery = False
            reasoning_parts.append("Clue discovery suppressed (Act 1, slow_down)")
        if proposals.reveal_budget_remaining <= 0:
            allow_clue_discovery = False
            reasoning_parts.append("Clue discovery suppressed (reveal budget exhausted)")
        if proposals.event_cooldowns.get("major_clue", 0) > 0:
            allow_clue_discovery = False
            reasoning_parts.append("Clue discovery suppressed (major clue cooldown)")
        if proposals.stuck_recovery_level >= 2 and proposals.discovered_clues < proposals.total_clues:
            allow_clue_discovery = True
            reasoning_parts.append("Clue discovery re-enabled for stuck recovery")

        # Force NPC reaction in specific scenarios
        force_npc_reaction: Optional[str] = None
        if proposals.breaking_points and turn_mood in ("tense", "explosive"):
            # Force the character with the breaking point to react
            bp_char = next(iter(proposals.breaking_points))
            force_npc_reaction = bp_char
            reasoning_parts.append(f"Forcing NPC reaction from: {bp_char}")

        return DMDirective(
            system_narration=system_narration,
            director_note=director_note,
            approved_events=approved,
            suppressed_events=suppressed,
            deferred_events=deferred,
            final_tension_delta=final_tension_delta,
            turn_mood=turn_mood,
            allow_clue_discovery=allow_clue_discovery,
            npc_visibility=npc_visibility,
            force_npc_reaction=force_npc_reaction,
            hint_text=hint_text,
            inject_twist=inject_twist,
            atmosphere_override=atmosphere_override,
            dm_reasoning="; ".join(reasoning_parts),
        )

    # ------------------------------------------------------------------
    # (a) Event selection
    # ------------------------------------------------------------------

    def _select_events(
        self,
        proposals: AgentProposals,
        max_events: int,
    ) -> Tuple[List[str], List[str]]:
        """
        Select which events fire and which are deferred.

        Priority order:
            breaking_points > visible NPC actions > conspiracy_events > architect_events

        Special conflict rules:
            - If breaking_point AND betrayal both want to fire, pick breaking_point
              and defer betrayal.
            - If 3+ events compete, pick the top ``max_events`` most dramatic,
              defer the rest.

        Returns:
            ``(approved, deferred)`` -- two lists of event strings.
        """
        act = proposals.current_act

        # Build a priority-ordered list of (priority, event_text) tuples
        # Lower priority number = higher priority
        candidates: List[Tuple[int, str]] = []

        # Breaking points are highest priority (but suppressed in Act 1)
        for char_id, event_type in proposals.breaking_points.items():
            if act == 1:
                # Too early for characters to break -- suppress
                continue
            if (
                event_type == "partial_confession"
                and proposals.event_cooldowns.get("confession", 0) > 0
            ):
                continue
            event_text = self._breaking_point_to_text(char_id, event_type)
            candidates.append((0, event_text))

        # Visible NPC actions
        for action in proposals.visible_npc_actions:
            candidates.append((1, action))

        # Conspiracy events
        for event in proposals.conspiracy_events:
            candidates.append((2, event))

        # Betrayal events (suppressed in Act 1)
        for event in proposals.betrayal_events:
            if act == 1:
                continue
            if proposals.event_cooldowns.get("betrayal", 0) > 0:
                continue
            candidates.append((3, event))

        # Architect events
        for event in proposals.architect_events:
            candidates.append((4, event))

        # Filter out events already shown in previous turns
        session_used = self._used_events.get(proposals.session_id if hasattr(proposals, 'session_id') else "default", set())
        candidates = [(p, e) for p, e in candidates if e not in session_used]

        # Conflict rule: never fire breaking_point AND betrayal in the same turn
        has_breaking = any(p == 0 for p, _ in candidates)
        has_betrayal = any(p == 3 for p, _ in candidates)
        if has_breaking and has_betrayal:
            # Remove betrayal from candidates; they will be deferred
            candidates = [(p, e) for p, e in candidates if p != 3]

        # Sort by priority (ascending = higher priority first)
        candidates.sort(key=lambda x: x[0])

        # Dedup: remove events that are too similar
        # (same event text repeated, or events sharing >50% of characters)
        seen_texts: set = set()
        unique_candidates: List[Tuple[int, str]] = []
        for priority, event_text in candidates:
            # Exact dedup
            if event_text in seen_texts:
                continue
            # Fuzzy dedup: skip if >60% of text overlaps with an existing event
            is_dup = False
            for seen in seen_texts:
                overlap = sum(1 for c in event_text if c in seen)
                if len(event_text) > 0 and overlap / len(event_text) > 0.6:
                    is_dup = True
                    break
            if not is_dup:
                unique_candidates.append((priority, event_text))
                seen_texts.add(event_text)
        candidates = unique_candidates

        approved: List[str] = []
        deferred: List[str] = []

        for _priority, event_text in candidates:
            if len(approved) < max_events:
                approved.append(event_text)
            else:
                deferred.append(event_text)

        # Also defer betrayal events that were removed due to conflict
        if has_breaking and has_betrayal:
            for event in proposals.betrayal_events:
                if event not in deferred:
                    deferred.append(event)

        return approved, deferred

    @staticmethod
    def _breaking_point_to_text(char_id: str, event_type: str) -> str:
        """Convert a breaking_point entry into a narrative event string."""
        char_names = {
            "linlan": "\u6797\u5c9a",
            "zhoumu": "\u5468\u7267",
            "songzhi": "\u5b8b\u77e5\u5fae",
        }
        name = char_names.get(char_id, char_id)

        if event_type == "partial_confession":
            return f"{name}\u7ec8\u4e8e\u6491\u4e0d\u4f4f\u4e86\uff0c\u58f0\u97f3\u98a4\u6296\u7740\u8bf4\u51fa\u4e86\u4e00\u4e9b\u9690\u85cf\u7684\u4fe1\u606f\u3002"
        elif event_type == "emotional_breakdown":
            return f"{name}\u7a81\u7136\u5d29\u6e83\u4e86\uff0c\u53cc\u624b\u6382\u7740\u8138\uff0c\u80a9\u8180\u4e0d\u505c\u5730\u98a4\u6296\u3002"
        elif event_type == "aggressive_outburst":
            return f"{name}\u731b\u5730\u7ad9\u8d77\u6765\uff0c\u62cd\u4e86\u4e00\u4e0b\u684c\u5b50\uff1a\u300c\u591f\u4e86\uff01\u4f60\u5230\u5e95\u60f3\u600e\u6837\uff1f\uff01\u300d"
        else:
            return f"{name}\u7684\u60c5\u7eea\u51fa\u73b0\u4e86\u5f02\u5e38\u6ce2\u52a8\u3002"

    def _gather_all_events(self, proposals: AgentProposals) -> List[str]:
        """Gather all candidate event texts from proposals."""
        events: List[str] = []

        for char_id, event_type in proposals.breaking_points.items():
            events.append(self._breaking_point_to_text(char_id, event_type))

        events.extend(proposals.visible_npc_actions)
        events.extend(proposals.conspiracy_events)
        events.extend(proposals.betrayal_events)
        events.extend(proposals.architect_events)
        return events

    # ------------------------------------------------------------------
    # (b) Mood determination
    # ------------------------------------------------------------------

    def _determine_mood(
        self,
        proposals: AgentProposals,
        session_id: str,
    ) -> str:
        """
        Determine the turn's overall mood based on act, tension, and
        recent mood history.

        Pacing rules by act:
            Act 1 (rounds 1-6):  mostly "calm" or "building"
            Act 2 (rounds 7-15): alternates "building" -> "tense" -> "building"
            Act 3 (rounds 16-20): escalates "tense" -> "explosive"

        Additional rules:
            - If the previous turn was "tense", force "building" (breathing room)
            - Never allow 3 consecutive "explosive" turns
        """
        act = proposals.current_act
        tension = proposals.tension
        recent_moods = self._previous_moods.get(session_id, [])
        last_mood = recent_moods[-1] if recent_moods else "neutral"

        # --- Base mood from act and tension ---
        if act == 1:
            if tension <= 25:
                mood = "calm"
            else:
                mood = "building"

        elif act == 2:
            if tension >= 70:
                mood = "tense"
            elif tension >= 45:
                mood = "building"
            else:
                mood = "calm"

            # Alternate: if last was "tense", force breathing room
            if last_mood == "tense":
                mood = "building"

        else:  # act == 3
            if tension >= 80:
                mood = "explosive"
            elif tension >= 60:
                mood = "tense"
            else:
                mood = "building"

        if proposals.recent_high_intensity_turns >= 2 and mood == "explosive":
            mood = "tense"

        # --- Global constraints ---

        # If last turn was "tense", give breathing room
        if last_mood == "tense" and mood == "tense":
            mood = "building"

        # Never allow 3 consecutive "explosive" turns
        if mood == "explosive" and len(recent_moods) >= 2:
            if recent_moods[-1] == "explosive" and recent_moods[-2] == "explosive":
                mood = "tense"

        # After an "explosive" turn, allow an "aftermath" beat
        if last_mood == "explosive" and mood not in ("explosive", "tense"):
            mood = "aftermath"

        return mood

    # ------------------------------------------------------------------
    # (c) Tension override
    # ------------------------------------------------------------------

    def _apply_tension_override(
        self,
        proposals: AgentProposals,
        turn_mood: str,
        session_id: str,
    ) -> int:
        """
        Apply pacing-based overrides to the tension delta.

        Rules:
            - If pacing says "slow_down" but delta > 5: cap at 3
            - If pacing says "climax" but delta < 3: boost to 5
            - If turn just had a "tense" mood last turn: force breathing room
              (cap at 2)
            - Never let 3 consecutive turns all be "explosive" (handled by mood,
              but also cap tension growth)
        """
        delta = proposals.tension_adjusted_delta
        pacing = proposals.pacing
        recent_moods = self._previous_moods.get(session_id, [])
        last_mood = recent_moods[-1] if recent_moods else "neutral"

        # Pacing slow_down: cap tension growth
        if pacing == "slow_down" and delta > 5:
            delta = 3

        # Pacing climax: ensure minimum tension growth
        if pacing == "climax" and delta < 3:
            delta = 5

        # Breathing room after "tense" turn
        if last_mood == "tense" and delta > 2:
            delta = 2

        # Cap growth during "calm" mood
        if turn_mood == "calm" and delta > 3:
            delta = 3

        # Aftermath mood: allow slight tension decrease
        if turn_mood == "aftermath" and delta > 0:
            delta = -2
        if proposals.recent_high_intensity_turns >= 2 and delta > 1:
            delta = 1

        return delta

    # ------------------------------------------------------------------
    # (d) Hint system
    # ------------------------------------------------------------------

    def _generate_hint(self, proposals: AgentProposals) -> Optional[str]:
        """
        Generate a contextual hint if the player is stuck.

        Rules:
            - stuck_turns >= 2 AND discovered_clues < total/2: subtle hint
            - stuck_turns >= 4: moderate hint
            - round_num >= max_rounds - 3 AND discovered_clues < 4: strong hint
        """
        stuck = proposals.stuck_turns
        discovered = proposals.discovered_clues
        total = proposals.total_clues
        round_num = proposals.round_num
        max_rounds = proposals.max_rounds

        # Strong hint: running out of time with few clues
        if round_num >= max_rounds - 3 and discovered < 4:
            return random.choice(HIGH_HINTS)

        if proposals.stuck_recovery_level >= 3:
            return random.choice(HIGH_HINTS)

        # Moderate hint: stuck for a long time
        if stuck >= 4 or proposals.stuck_recovery_level >= 2:
            return random.choice(MID_HINTS)

        # Subtle hint: somewhat stuck with low progress
        if stuck >= 2 and discovered < total / 2:
            return random.choice(LOW_HINTS)

        return None

    # ------------------------------------------------------------------
    # (e) Twist injection
    # ------------------------------------------------------------------

    def _should_inject_twist(
        self,
        session_id: str,
        proposals: AgentProposals,
    ) -> Optional[str]:
        """
        Decide if a plot twist should be injected.

        Conditions (ALL must be met):
            - Act 2 or Act 3
            - Tension between 40 and 70
            - Twist not already used this session
            - Random chance (30%) -- twists should be rare

        Returns:
            A twist string, or ``None``.
        """
        # Already used a twist this session
        if self._twist_used.get(session_id, False):
            return None
        if proposals.event_cooldowns.get("twist", 0) > 0:
            return None

        act = proposals.current_act
        tension = proposals.tension

        # Only in Act 2-3
        if act < 2:
            return None

        # Tension sweet spot
        if tension < 40 or tension > 70:
            return None
        if proposals.recent_high_intensity_turns >= 2:
            return None

        # Random gate: 30% chance when conditions are met
        if random.random() > 0.30:
            return None

        # Select and mark as used
        twist = random.choice(TWIST_POOL)
        self._twist_used[session_id] = True
        return twist

    # ------------------------------------------------------------------
    # (f) Narration assembly
    # ------------------------------------------------------------------

    def _assemble_narration(
        self,
        proposals: AgentProposals,
        hint_text: Optional[str],
    ) -> Tuple[str, str, Optional[str]]:
        """
        Assemble the final system_narration, director_note, and optional
        atmosphere_override.

        Rules:
            - system_narration = action_narration + architect_narration
            - director_note = architect_director_note (or hint_text if hinting)
            - Trim to length limits

        Returns:
            ``(system_narration, director_note, atmosphere_override)``
        """
        # Narration: combine action narration with architect narration
        parts = []
        if proposals.action_narration:
            parts.append(proposals.action_narration.strip())
        if proposals.architect_narration:
            parts.append(proposals.architect_narration.strip())

        system_narration = " ".join(parts) if parts else "\u4f60\u73af\u987e\u56db\u5468\uff0c\u8001\u5b85\u4e00\u5207\u5982\u5e38\u3002"

        # Trim narration to 120 characters
        if len(system_narration) > 120:
            system_narration = system_narration[:117] + "\u2026\u2026\u2026"

        # Director note: prefer hint_text when providing a hint
        if hint_text:
            director_note = hint_text
        elif proposals.architect_director_note:
            director_note = proposals.architect_director_note
        else:
            director_note = ""

        # Trim director note to 60 characters
        if len(director_note) > 60:
            director_note = director_note[:57] + "\u2026\u2026\u2026"

        # Atmosphere override: only set if tension atmosphere conflicts with pacing
        atmosphere_override: Optional[str] = None
        if (
            proposals.pacing == "slow_down"
            and proposals.tension_atmosphere in ("peak", "climax")
        ):
            atmosphere_override = "\u7a7a\u6c14\u4e2d\u7684\u7d27\u5f20\u611f\u7a0d\u7a0d\u7f13\u548c\u4e86\u4e00\u4e9b\uff0c\u4f46\u6697\u6d41\u4ecd\u5728\u6d8c\u52a8\u3002"

        return system_narration, director_note, atmosphere_override

    # ------------------------------------------------------------------
    # (g) NPC visibility
    # ------------------------------------------------------------------

    def _determine_npc_visibility(
        self,
        proposals: AgentProposals,
    ) -> Dict[str, bool]:
        """
        Determine which NPC autonomous actions to reveal.

        Rules:
            - Show visible NPC actions (always True)
            - For hidden NPC actions: only show evidence, not the action itself
            - If Song Zhi scooped a location: evidence visible when player visits
        """
        visibility: Dict[str, bool] = {}

        # Visible actions are always shown
        for i, action in enumerate(proposals.visible_npc_actions):
            visibility[f"visible_{i}"] = True

        # Hidden actions are never directly shown
        for i, action in enumerate(proposals.hidden_npc_actions):
            visibility[f"hidden_{i}"] = False

        # Evidence is always shown (it's what the player discovers)
        for i, evidence in enumerate(proposals.npc_evidence):
            visibility[f"evidence_{i}"] = True

        return visibility

    # ------------------------------------------------------------------
    # Session state helpers
    # ------------------------------------------------------------------

    def _record_mood(self, session_id: str, mood: str) -> None:
        """Record the mood for this turn, keeping a rolling window of 5."""
        moods = self._previous_moods[session_id]
        moods.append(mood)
        if len(moods) > 5:
            self._previous_moods[session_id] = moods[-5:]

    def record_used_events(self, session_id: str, events: List[str]) -> None:
        """Record events that were shown to the player so they don't repeat."""
        for evt in events:
            self._used_events[session_id].add(evt)
        # Keep set bounded
        if len(self._used_events[session_id]) > 50:
            # Remove oldest (convert to list, trim, convert back)
            items = list(self._used_events[session_id])
            self._used_events[session_id] = set(items[-30:])

    def get_deferred_events(self, session_id: str) -> List[str]:
        """Return the list of deferred events for a session (for debugging)."""
        return list(self._deferred_events.get(session_id, []))

    def get_mood_history(self, session_id: str) -> List[str]:
        """Return the mood history for a session (for debugging)."""
        return list(self._previous_moods.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        """Clear all per-session state for a given session."""
        self._previous_moods.pop(session_id, None)
        self._twist_used.pop(session_id, None)
        self._deferred_events.pop(session_id, None)
        self._used_events.pop(session_id, None)
