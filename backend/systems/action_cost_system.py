"""
Action Cost System — Action points per turn.

Pure rules, zero LLM calls. Adds tactical depth by making players
choose which actions to spend their limited points on each turn.
"""

from typing import Optional


# ── Action costs by category ──
ACTION_COSTS = {
    "investigate": 1,
    "social": 1,
    "confront": 1,
    "stealth": 1,
    "manipulate": 1,
    "environmental": 1,
    "move": 0,        # Movement is free
    "communicate": 0,  # Basic conversation is free
    "observe": 0,      # Looking around is free
    "ask": 0,          # Asking questions is free (social is deeper)
    "other": 1,
    # Legacy intent types
    "search": 1,
    "accuse": 1,
    "bluff": 1,
    "eavesdrop": 1,
    "hide": 1,
}

DEFAULT_ACTION_POINTS = 2
DEFAULT_MAX_ACTION_POINTS = 2


class ActionCostSystem:
    """Pure-rule system for action point management."""

    def get_cost(self, action_category: str) -> int:
        """Get the cost of an action category."""
        return ACTION_COSTS.get(action_category, 1)

    def can_afford(self, action_points: int, action_category: str) -> bool:
        """Check if the player can afford this action."""
        cost = self.get_cost(action_category)
        return action_points >= cost

    def spend(self, action_points: int, action_category: str) -> int:
        """Spend action points. Returns new remaining points."""
        cost = self.get_cost(action_category)
        return max(0, action_points - cost)

    def reset(self, max_action_points: int) -> int:
        """Reset action points at start of turn."""
        return max_action_points

    def get_blocked_message(self, action_category: str) -> str:
        """Get the message when player can't afford an action."""
        cost = self.get_cost(action_category)
        return (
            f"你的行动力不足（需要{cost}点，但已用完）。"
            f"你可以选择移动到其他地点或与人交谈，这些不消耗行动力。"
        )
