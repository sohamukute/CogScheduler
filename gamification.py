"""
Gamification engine — Deep Work mechanics.

Mechanics:
  - XP per task block: 10 + cognitive_load × 5
  - Deep Work streak: +1 per deep block (load ≥ 7) consecutively
  - Streak bonus: streak × 15 XP
  - Recovery bonus: +20 XP for taking a suggested break
  - Levels: Student(0) → Scholar(200) → Genius(600) → Mastermind(1200)
  - Badges: "Early Bird", "Night Owl", "Marathon Focus", "Brain Recharger"
"""

from __future__ import annotations

from models import ScheduledBlock, GamificationState
from config import CogConfig


# ── Level thresholds ──────────────────────────────────────────

LEVELS = [
    (0, "Student"),
    (200, "Scholar"),
    (600, "Genius"),
    (1200, "Mastermind"),
]


def _level_for_xp(xp: int) -> str:
    level = "Student"
    for threshold, name in LEVELS:
        if xp >= threshold:
            level = name
    return level


# ── Badge rules ───────────────────────────────────────────────

def _compute_badges(
    blocks: list[ScheduledBlock],
    streak: int,
) -> list[str]:
    badges: list[str] = []

    has_early = any(
        not b.is_break and b.start_min < 9 * 60  # before 09:00
        for b in blocks
    )
    has_late = any(
        not b.is_break and b.end_min > 21 * 60  # after 21:00
        for b in blocks
    )
    has_break = any(b.is_break for b in blocks)

    deep_blocks = [b for b in blocks if not b.is_break and b.cognitive_load >= 7]
    total_deep_min = sum(b.end_min - b.start_min for b in deep_blocks)

    if has_early:
        badges.append("Early Bird")
    if has_late:
        badges.append("Night Owl")
    if total_deep_min >= 180:
        badges.append("Marathon Focus")
    if has_break:
        badges.append("Brain Recharger")
    if streak >= 3:
        badges.append("Deep Streak Master")

    return badges


# ── Main gamification function ────────────────────────────────

def compute_gamification(
    blocks: list[ScheduledBlock],
    cfg: CogConfig | None = None,
) -> GamificationState:
    """
    Compute XP, level, streak, and badges from a schedule.
    """
    if cfg is None:
        cfg = CogConfig()

    xp = 0
    streak = 0
    max_streak = 0
    prev_was_deep = False

    for block in blocks:
        if block.is_break:
            # Recovery bonus
            xp += 20
            prev_was_deep = False
            continue

        # XP per task block
        block_xp = 10 + int(block.cognitive_load * 5)
        xp += block_xp

        # Deep work streak
        is_deep = block.cognitive_load >= cfg.deep_work_load_threshold
        if is_deep:
            if prev_was_deep:
                streak += 1
            else:
                streak = 1
            prev_was_deep = True
        else:
            prev_was_deep = False
            streak = 0

        max_streak = max(max_streak, streak)

    # Streak bonus
    xp += max_streak * 15

    # Badges
    badges = _compute_badges(blocks, max_streak)

    return GamificationState(
        xp=xp,
        level=_level_for_xp(xp),
        streak=max_streak,
        badges=badges,
    )
