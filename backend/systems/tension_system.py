"""
TensionConductor — controls the emotional tension curve like a music conductor.

Creates waves of rising and falling tension instead of a linear increase, ensuring
the game experience has dramatic peaks and valleys that follow proper dramatic
pacing.  This is pure game logic — no LLM calls.

Usage:
    conductor = TensionConductor()
    adjustment = conductor.conduct(
        session_id="abc123",
        round_num=5,
        max_rounds=20,
        current_tension=35,
        raw_delta=8,
        discovered_clues_count=2,
        phase="自由试探",
    )
    # adjustment.adjusted_delta  -> the modified tension delta
    # adjustment.atmosphere      -> "calm" / "building" / "peak" / "release" / "climax"
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Dict, List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class TensionAdjustment(BaseModel):
    """Result of the TensionConductor's processing of a raw tension delta."""
    raw_delta: int           # Original delta from rule_judge
    adjusted_delta: int      # Modified delta after conducting
    reason: str              # Why adjustment was made
    atmosphere: str          # "calm" / "building" / "peak" / "release" / "climax"


# ---------------------------------------------------------------------------
# TensionConductor
# ---------------------------------------------------------------------------

class TensionConductor:
    """
    Controls the emotional tension curve for each game session.

    Instead of letting tension increase linearly, the conductor shapes a wave
    pattern with distinct phases:

        Round  1-5:   Gentle rise (exploration phase)
        Round  6-10:  Building waves (mid-game tension)
        Round 11-15:  Escalating peaks (late mid-game)
        Round 16-20:  Final crescendo (endgame)

    The conductor tracks per-session tension history and applies dampening,
    amplification, forced releases, and special boosts to maintain dramatic
    pacing.
    """

    def __init__(self) -> None:
        """Initialize with empty per-session tension histories."""
        # session_id -> list of (round_num, tension_after_adjustment)
        self._histories: Dict[str, List[int]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def conduct(
        self,
        session_id: str,
        round_num: int,
        max_rounds: int,
        current_tension: int,
        raw_delta: int,
        discovered_clues_count: int,
        phase: str,
    ) -> TensionAdjustment:
        """
        Process a raw tension delta and produce an adjusted delta that follows
        the conductor's wave-pattern rules.

        Args:
            session_id:             Game session identifier.
            round_num:              Current round number (1-based).
            max_rounds:             Maximum rounds in the game.
            current_tension:        Current tension value (0-100) before delta.
            raw_delta:              Raw delta from rule_judge (can be negative).
            discovered_clues_count: Number of clues discovered so far.
            phase:                  Current game phase string.

        Returns:
            A TensionAdjustment with the adjusted delta, reason, and atmosphere.
        """
        history = self._histories[session_id]
        adjusted = raw_delta
        reasons: List[str] = []

        # ----------------------------------------------------------
        # Phase 1: Apply wave-pattern rules based on round segment
        # ----------------------------------------------------------

        if round_num <= 5:
            # Gentle rise — cap increases, dampen if too high
            adjusted, phase_reasons = self._gentle_rise(
                adjusted, current_tension
            )
            reasons.extend(phase_reasons)

        elif round_num <= 10:
            # Building waves — allow normal deltas, force releases after peaks
            adjusted, phase_reasons = self._building_waves(
                adjusted, current_tension, history
            )
            reasons.extend(phase_reasons)

        elif round_num <= 15:
            # Escalating peaks — amplify deltas, small releases after peaks
            adjusted, phase_reasons = self._escalating_peaks(
                adjusted, current_tension, history
            )
            reasons.extend(phase_reasons)

        else:
            # Final crescendo — strong amplification, minimal releases
            adjusted, phase_reasons = self._final_crescendo(
                adjusted, current_tension, history
            )
            reasons.extend(phase_reasons)

        # ----------------------------------------------------------
        # Phase 2: Apply special rules
        # ----------------------------------------------------------

        # Rule: Never let tension hit 100 before round 15
        projected = current_tension + adjusted
        if projected >= 100 and round_num < 15:
            adjusted = max(0, 95 - current_tension)
            reasons.append(f"capped at 95 (round {round_num} < 15)")

        # Rule: Flat tension detection — inject a boost if tension has been
        # stagnant (within +/-3) for 3+ consecutive turns
        if self._is_flat(history, current_tension, window=3, tolerance=3):
            boost = random.randint(5, 8)
            adjusted = max(adjusted, boost)
            reasons.append(f"flat tension detected, injected +{boost} boost")

        # Rule: Ensure tension doesn't go below 0
        if current_tension + adjusted < 0:
            adjusted = -current_tension
            reasons.append("clamped to prevent negative tension")

        # Rule: Ensure tension doesn't exceed 100
        if current_tension + adjusted > 100:
            adjusted = 100 - current_tension
            reasons.append("clamped to ceiling 100")

        # ----------------------------------------------------------
        # Record history and determine atmosphere
        # ----------------------------------------------------------
        final_tension = current_tension + adjusted
        history.append(final_tension)

        atmosphere = self.get_atmosphere(final_tension)

        reason_str = "; ".join(reasons) if reasons else "no adjustment needed"

        return TensionAdjustment(
            raw_delta=raw_delta,
            adjusted_delta=adjusted,
            reason=reason_str,
            atmosphere=atmosphere,
        )

    def get_atmosphere(self, tension: int) -> str:
        """
        Map a tension value to an atmosphere label.

        Ranges:
             0-20:  "calm"
            21-40:  "building"
            41-60:  "peak"
            61-80:  "release" (brief valleys) — but contextually this can also
                    be "peak" when tension is rising; we use the label as a
                    signal to allow brief relief before the next escalation.
            81-100: "climax"
        """
        if tension <= 20:
            return "calm"
        elif tension <= 40:
            return "building"
        elif tension <= 60:
            return "peak"
        elif tension <= 80:
            return "release"
        else:
            return "climax"

    def get_session_history(self, session_id: str) -> List[int]:
        """Return the tension history for a session (list of tension values)."""
        return list(self._histories.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        """Clear the tension history for a session."""
        self._histories.pop(session_id, None)

    # ------------------------------------------------------------------
    # Wave-pattern phase implementations
    # ------------------------------------------------------------------

    def _gentle_rise(
        self, delta: int, current_tension: int
    ) -> tuple[int, List[str]]:
        """
        Rounds 1-5: Gentle rise phase.

        - Cap tension increase at +5 per turn.
        - If tension > 35, apply dampening (reduce delta by 50%).
        """
        reasons: List[str] = []
        adjusted = delta

        # Cap positive delta at +5
        if adjusted > 5:
            adjusted = 5
            reasons.append("gentle rise: capped increase at +5")

        # Dampen if tension is already above 35
        if current_tension > 35 and adjusted > 0:
            adjusted = max(1, adjusted // 2)
            reasons.append("gentle rise: dampened (tension > 35)")

        return adjusted, reasons

    def _building_waves(
        self, delta: int, current_tension: int, history: List[int]
    ) -> tuple[int, List[str]]:
        """
        Rounds 6-10: Building waves phase.

        - Allow normal deltas.
        - After 3 consecutive rises, force a release of -3 to -5.
        - Target tension range: 30-55.
        """
        reasons: List[str] = []
        adjusted = delta

        # Check for 3 consecutive rises — if so, force a release
        consecutive_rises = self._count_consecutive_rises(history)
        if consecutive_rises >= 3 and adjusted > 0:
            release = random.randint(-5, -3)
            adjusted = release
            reasons.append(
                f"building waves: forced release ({release}) after "
                f"{consecutive_rises} consecutive rises"
            )
            return adjusted, reasons

        # Soft guidance toward target range 30-55
        if current_tension < 30 and adjusted < 3:
            # Below target range — nudge upward
            adjusted = max(adjusted, 3)
            reasons.append("building waves: nudged up (below target 30)")
        elif current_tension > 55 and adjusted > 0:
            # Above target range — dampen
            adjusted = max(0, adjusted // 2)
            reasons.append("building waves: dampened (above target 55)")

        return adjusted, reasons

    def _escalating_peaks(
        self, delta: int, current_tension: int, history: List[int]
    ) -> tuple[int, List[str]]:
        """
        Rounds 11-15: Escalating peaks phase.

        - Amplify deltas by 1.3x.
        - After a peak (3 consecutive rises), small release of -2 to -3.
        - Target tension range: 50-75.
        """
        reasons: List[str] = []
        adjusted = delta

        # Check for consecutive rises — small release after peak
        consecutive_rises = self._count_consecutive_rises(history)
        if consecutive_rises >= 3 and adjusted > 0:
            release = random.randint(-3, -2)
            adjusted = release
            reasons.append(
                f"escalating peaks: small release ({release}) after "
                f"{consecutive_rises} consecutive rises"
            )
            return adjusted, reasons

        # Amplify positive deltas by 1.3x
        if adjusted > 0:
            amplified = int(math.ceil(adjusted * 1.3))
            if amplified != adjusted:
                reasons.append(
                    f"escalating peaks: amplified {adjusted} -> {amplified} (1.3x)"
                )
            adjusted = amplified

        # Soft guidance toward target range 50-75
        if current_tension < 50 and adjusted < 5:
            adjusted = max(adjusted, 5)
            reasons.append("escalating peaks: nudged up (below target 50)")
        elif current_tension > 75 and adjusted > 0:
            adjusted = max(1, int(adjusted * 0.7))
            reasons.append("escalating peaks: dampened (above target 75)")

        return adjusted, reasons

    def _final_crescendo(
        self, delta: int, current_tension: int, history: List[int]
    ) -> tuple[int, List[str]]:
        """
        Rounds 16-20: Final crescendo phase.

        - Amplify positive deltas by 1.5x.
        - Minimal releases (tension should trend toward climax).
        - Target tension range: 65-90.
        """
        reasons: List[str] = []
        adjusted = delta

        # Amplify positive deltas by 1.5x
        if adjusted > 0:
            amplified = int(math.ceil(adjusted * 1.5))
            if amplified != adjusted:
                reasons.append(
                    f"final crescendo: amplified {adjusted} -> {amplified} (1.5x)"
                )
            adjusted = amplified

        # Prevent negative deltas larger than -2 (minimal releases only)
        if adjusted < -2:
            adjusted = -2
            reasons.append("final crescendo: limited release to -2")

        # Nudge up if below target range
        if current_tension < 65 and adjusted < 5:
            adjusted = max(adjusted, 5)
            reasons.append("final crescendo: nudged up (below target 65)")

        return adjusted, reasons

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _count_consecutive_rises(self, history: List[int]) -> int:
        """
        Count how many consecutive tension increases have occurred at the
        end of the history.

        Returns 0 if history has fewer than 2 entries.
        """
        if len(history) < 2:
            return 0

        count = 0
        for i in range(len(history) - 1, 0, -1):
            if history[i] > history[i - 1]:
                count += 1
            else:
                break

        return count

    def _is_flat(
        self,
        history: List[int],
        current_tension: int,
        window: int = 3,
        tolerance: int = 3,
    ) -> bool:
        """
        Check if tension has been flat (within +/-tolerance) for the last
        `window` turns.

        A flat tension curve means the player is not making progress and the
        game feels stale, so we should inject a boost.
        """
        if len(history) < window:
            return False

        recent = history[-window:]
        # Check if all recent values are within tolerance of each other
        min_val = min(recent)
        max_val = max(recent)

        # Also check against current tension
        all_values = recent + [current_tension]
        return (max(all_values) - min(all_values)) <= tolerance
