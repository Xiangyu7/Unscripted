"""
Score System — rates the player's detective performance.

After each game, shows a score breakdown that makes players want to replay
for a better rating. This is the core "one more game" mechanic.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel


class ScoreBreakdown(BaseModel):
    """Detailed score after game ends."""
    # Evidence gathering (max 40 points)
    clues_found: int = 0
    total_clues: int = 9
    clue_score: int = 0

    # Deduction quality (max 30 points)
    truth_accuracy: float = 0.0    # 0-1, how close to truth
    deduction_score: int = 0

    # Investigation efficiency (max 15 points)
    rounds_used: int = 20
    max_rounds: int = 20
    efficiency_score: int = 0

    # NPC interaction (max 15 points)
    lies_caught: int = 0
    confrontations_won: int = 0
    interaction_score: int = 0

    # Total
    total_score: int = 0
    max_score: int = 100
    rank: str = "F"
    rank_title: str = ""
    summary: str = ""


# Rank definitions
RANKS = [
    (90, "S", "传奇侦探", "你的推理能力令人叹为观止。福尔摩斯也不过如此。"),
    (80, "A", "金牌探长", "出色的调查能力。你几乎看穿了所有人的伪装。"),
    (70, "B", "资深探员", "不错的推理，但还有一些关键细节被你忽略了。"),
    (60, "C", "见习侦探", "你找到了一些线索，但真相比你想的更复杂。"),
    (40, "D", "业余爱好者", "调查方向基本正确，但缺乏关键证据支撑。"),
    (0, "F", "迷途旅客", "真相完全从你指缝间溜走了。再来一次？"),
]


def calculate_score(
    clues_found: int,
    total_clues: int,
    truth_accuracy: float,
    rounds_used: int,
    max_rounds: int,
    lies_caught: int,
    confrontations_won: int,
    game_over_reason: str,  # "deduction" / "vote" / "timeout" / "chaos"
) -> ScoreBreakdown:
    """Calculate the player's detective score."""

    # 1. Clue score (max 40)
    clue_pct = clues_found / max(total_clues, 1)
    clue_score = int(clue_pct * 40)

    # 2. Deduction score (max 30)
    deduction_score = int(truth_accuracy * 30)
    # Bonus for solving via deduction (not vote/timeout)
    if game_over_reason == "deduction":
        deduction_score = min(30, deduction_score + 5)
    elif game_over_reason == "timeout":
        deduction_score = max(0, deduction_score - 10)
    elif game_over_reason == "chaos":
        deduction_score = 0

    # 3. Efficiency score (max 15)
    rounds_pct = 1.0 - (rounds_used / max_rounds)
    efficiency_score = int(max(0, rounds_pct) * 15)
    # Bonus for finishing early
    if rounds_used <= max_rounds * 0.6:
        efficiency_score = min(15, efficiency_score + 3)

    # 4. Interaction score (max 15)
    interaction_score = min(15, lies_caught * 4 + confrontations_won * 3)

    # Total
    total = clue_score + deduction_score + efficiency_score + interaction_score
    total = min(100, max(0, total))

    # Rank
    rank = "F"
    rank_title = "迷途旅客"
    summary = ""
    for threshold, r, title, desc in RANKS:
        if total >= threshold:
            rank = r
            rank_title = title
            summary = desc
            break

    return ScoreBreakdown(
        clues_found=clues_found,
        total_clues=total_clues,
        clue_score=clue_score,
        truth_accuracy=truth_accuracy,
        deduction_score=deduction_score,
        rounds_used=rounds_used,
        max_rounds=max_rounds,
        efficiency_score=efficiency_score,
        lies_caught=lies_caught,
        confrontations_won=confrontations_won,
        interaction_score=interaction_score,
        total_score=total,
        max_score=100,
        rank=rank,
        rank_title=rank_title,
        summary=summary,
    )
