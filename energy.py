"""
Energy & Fatigue model — pure math, no I/O.

Implements a Two-Process circadian model (Borbély 2022) with learned fatigue
weights (Steward 2024) and Yerkes-Dodson arousal capping.
"""

from __future__ import annotations

import math
from config import CogConfig


# ──────────────────────────────────────────────────────────────
# 1. Circadian base energy
# ──────────────────────────────────────────────────────────────

def circadian_base(hour: float, chronotype: str = "normal") -> float:
    """
    Bimodal sinusoid with peaks around 10 AM and 3 PM.

    ``chronotype`` shifts the curve:
      - "early"  → peaks 1 h earlier
      - "late"   → peaks 1 h later
      - "normal" → no shift

    Returns a value in [0, 1].
    """
    shift = {"early": -1.0, "normal": 0.0, "late": 1.0}.get(chronotype, 0.0)
    h = hour + shift

    # Primary peak ≈ 10 AM, secondary ≈ 15 PM (3 PM)
    primary = 0.55 + 0.35 * math.sin(math.pi * (h - 6) / 8)   # peak at h=10
    secondary = 0.50 + 0.25 * math.sin(math.pi * (h - 11) / 8)  # peak at h=15
    raw = max(primary, secondary)
    return max(0.0, min(1.0, raw))


# ──────────────────────────────────────────────────────────────
# 2. Sleep factor
# ──────────────────────────────────────────────────────────────

def sleep_factor(sleep_hours: float, baseline: float = 8.0) -> float:
    """clip(sleep / baseline, 0.5, 1.2)"""
    return max(0.5, min(sleep_hours / baseline, 1.2))


# ──────────────────────────────────────────────────────────────
# 3. Commitment load penalty
# ──────────────────────────────────────────────────────────────

def lecture_penalty(lectures: int, penalty_per: float = 0.02) -> float:
    """
    Light residual fatigue from having commitments (lectures/meetings) today.
    Kept small because commitments already block time slots directly.
    penalty_per reduced from 0.04 → 0.02 to avoid double-penalizing.
    """
    return min(lectures * penalty_per, 0.15)


# ──────────────────────────────────────────────────────────────
# 4. Fatigue (accumulated)
# ──────────────────────────────────────────────────────────────

def compute_fatigue(
    consec_deep_min: float,
    total_deep_min: float,
    cfg: CogConfig | None = None,
) -> float:
    """
    Fatigue(t) = a × (consec / 90) + b × (total / 180)

    ``a`` and ``b`` are online-learned from TLX feedback.
    Returns a value clipped to [0, 1].
    """
    if cfg is None:
        cfg = CogConfig()
    a = cfg.fatigue_consec_weight
    b = cfg.fatigue_total_weight
    raw = a * (consec_deep_min / cfg.consec_threshold_min) + \
          b * (total_deep_min / cfg.total_deep_threshold_min)
    return max(0.0, min(1.0, raw))


# ──────────────────────────────────────────────────────────────
# 5. Break recovery
# ──────────────────────────────────────────────────────────────

def apply_break_recovery(fatigue: float, recovery_factor: float = 0.30) -> float:
    """Post-break fatigue = fatigue × (1 - recovery_factor)."""
    return fatigue * (1 - recovery_factor)


# ──────────────────────────────────────────────────────────────
# 6. Composite energy
# ──────────────────────────────────────────────────────────────

def compute_energy(
    hour: float,
    sleep_hours: float,
    stress_level: int,
    lectures: int,
    fatigue: float,
    chronotype: str = "normal",
    cfg: CogConfig | None = None,
) -> float:
    """
    Energy(t) = circadian(t) × sleep_factor - lecture_penalty - fatigue

    Clipped to [0, 1].
    """
    if cfg is None:
        cfg = CogConfig()

    c = circadian_base(hour, chronotype)
    s = sleep_factor(sleep_hours, cfg.sleep_baseline)
    lp = lecture_penalty(lectures, cfg.lecture_penalty_per)

    # Stress also reduces effective energy slightly
    stress_penalty = max(0, (stress_level - 2)) * 0.03

    raw = c * s - lp - fatigue - stress_penalty
    return max(0.0, min(1.0, raw))


# ──────────────────────────────────────────────────────────────
# 7. Arousal cap (Yerkes-Dodson)
# ──────────────────────────────────────────────────────────────

def arousal_cap(
    stress_level: int,
    fatigue: float,
    cfg: CogConfig | None = None,
) -> float | None:
    """
    If stress ≥ threshold AND fatigue > 0.6, cap max cognitive load.
    Returns the cap value, or None if no cap applies.
    """
    if cfg is None:
        cfg = CogConfig()

    if stress_level >= cfg.stress_cap_threshold and fatigue > 0.6:
        return cfg.max_load_under_stress
    return None
