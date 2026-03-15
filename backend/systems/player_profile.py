"""
Player Profile System — tracks detective style across sessions.

After each game, saves the player's behavior patterns. Next game,
NPCs adapt to the player's known strengths and weaknesses.

A player who always searches thoroughly → NPCs hide evidence better
A player who bluffs a lot → NPCs are more skeptical of claims
A player who's gentle → NPCs let guard down faster
"""

import json
import os
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PlayerProfile(BaseModel):
    """Persistent player data across game sessions."""
    games_played: int = 0
    best_rank: str = "F"
    best_score: int = 0
    avg_score: float = 0.0

    # Play style tracking
    total_searches: int = 0
    total_interrogations: int = 0
    total_bluffs: int = 0
    total_accusations: int = 0
    total_social_actions: int = 0
    total_stealth_actions: int = 0

    # Derived style
    primary_style: str = "unknown"     # searcher/interrogator/bluffer/socializer
    clues_per_game_avg: float = 0.0
    rounds_per_game_avg: float = 0.0
    lies_caught_total: int = 0

    # Which truths they've seen (for replayability)
    truths_seen: List[str] = Field(default_factory=list)

    # Win/loss record
    wins: int = 0
    losses: int = 0


PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "profiles")


class PlayerProfileSystem:
    """Manages persistent player profiles."""

    def __init__(self):
        os.makedirs(PROFILE_DIR, exist_ok=True)
        self._cache: Dict[str, PlayerProfile] = {}

    def _path(self, player_id: str) -> str:
        safe_id = "".join(c for c in player_id if c.isalnum() or c in "-_")
        return os.path.join(PROFILE_DIR, f"{safe_id}.json")

    def get_profile(self, player_id: str = "default") -> PlayerProfile:
        if player_id in self._cache:
            return self._cache[player_id]

        path = self._path(player_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                profile = PlayerProfile(**data)
        else:
            profile = PlayerProfile()

        self._cache[player_id] = profile
        return profile

    def save_profile(self, player_id: str = "default"):
        profile = self._cache.get(player_id)
        if not profile:
            return
        path = self._path(player_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)

    def update_after_game(
        self,
        player_id: str,
        score: int,
        rank: str,
        clues_found: int,
        rounds_used: int,
        lies_caught: int,
        truth_id: Optional[str],
        won: bool,
        action_counts: Dict[str, int],
    ):
        """Update profile after a game ends."""
        p = self.get_profile(player_id)
        p.games_played += 1

        if score > p.best_score:
            p.best_score = score
            p.best_rank = rank

        p.avg_score = (p.avg_score * (p.games_played - 1) + score) / p.games_played

        p.total_searches += action_counts.get("investigate", 0)
        p.total_interrogations += action_counts.get("social", 0) + action_counts.get("confront", 0)
        p.total_bluffs += action_counts.get("manipulate", 0)
        p.total_accusations += action_counts.get("confront", 0)
        p.total_social_actions += action_counts.get("social", 0)
        p.total_stealth_actions += action_counts.get("stealth", 0)

        p.clues_per_game_avg = (p.clues_per_game_avg * (p.games_played - 1) + clues_found) / p.games_played
        p.rounds_per_game_avg = (p.rounds_per_game_avg * (p.games_played - 1) + rounds_used) / p.games_played
        p.lies_caught_total += lies_caught

        if truth_id and truth_id not in p.truths_seen:
            p.truths_seen.append(truth_id)

        if won:
            p.wins += 1
        else:
            p.losses += 1

        # Derive primary style
        totals = {
            "searcher": p.total_searches,
            "interrogator": p.total_interrogations,
            "bluffer": p.total_bluffs,
            "socializer": p.total_social_actions,
            "shadow": p.total_stealth_actions,
        }
        p.primary_style = max(totals, key=lambda k: totals[k]) if any(totals.values()) else "unknown"

        self.save_profile(player_id)

    def get_npc_adaptation_hints(self, player_id: str = "default") -> str:
        """Get hints for NPC agents to adapt to this player's style."""
        p = self.get_profile(player_id)
        if p.games_played == 0:
            return ""

        hints = [f"【玩家档案——基于{p.games_played}局历史数据】"]

        style_desc = {
            "searcher": "这个侦探擅长搜证，会仔细翻找每个角落。你需要更好地隐藏证据。",
            "interrogator": "这个侦探擅长审讯，会反复追问同一个人。你需要更坚定地守住秘密。",
            "bluffer": "这个侦探喜欢虚张声势。小心——他说'我知道了'可能是在诈你。",
            "socializer": "这个侦探擅长套近乎。别被他的友善迷惑了——他在套话。",
            "shadow": "这个侦探喜欢偷听和暗中观察。注意你的一举一动——他可能在角落里看着。",
        }

        desc = style_desc.get(p.primary_style, "")
        if desc:
            hints.append(f"侦探类型: {p.primary_style} — {desc}")

        if p.best_rank in ("S", "A"):
            hints.append("警告: 这个侦探很厉害（历史最高评分{}级），你需要格外小心。".format(p.best_rank))

        if p.lies_caught_total >= 3:
            hints.append(f"这个侦探已经揭穿过{p.lies_caught_total}次谎言——说谎时要更加自然。")

        return "\n".join(hints)
