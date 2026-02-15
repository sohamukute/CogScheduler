"""
CogConfig — every tunable coefficient for the scheduler.

All defaults are sourced from literature (Borbély, Steward, Ogut, Yerkes-Dodson).
Online learning (TLX feedback) updates ``fatigue_consec_weight`` and
``fatigue_total_weight`` at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CogConfig:
    # ── Sleep & circadian ──────────────────────────────────
    sleep_baseline: float = 8.0  # Borbély 2022

    # ── Fatigue accumulation weights (tuned by TLX) ────────
    fatigue_consec_weight: float = 0.6  # Steward 2024
    fatigue_total_weight: float = 0.4   # Steward 2024

    # ── Thresholds ─────────────────────────────────────────
    consec_threshold_min: int = 90    # max consecutive deep-work minutes before forced break
    total_deep_threshold_min: int = 180  # saturation marker

    # ── Break durations ────────────────────────────────────
    short_break_trigger_min: int = 60   # Ogut et al.
    short_break_duration: int = 15      # Ogut et al.
    long_break_duration: int = 25       # after 3+ deep blocks

    # ── Fatigue force-break ────────────────────────────────
    fatigue_force_break: float = 0.8    # force break when fatigue ≥ this

    # ── Stress / Yerkes-Dodson ─────────────────────────────
    stress_cap_threshold: int = 4       # stress level that triggers cap
    max_load_under_stress: float = 5.0  # Yerkes-Dodson cap

    # ── Lectures ───────────────────────────────────────────
    lecture_penalty_per: float = 0.02   # light residual fatigue per commitment block

    # ── Break recovery factor ──────────────────────────────
    break_recovery_factor: float = 0.30

    # ── Quantum size (minutes) ─────────────────────────────
    quantum_min: int = 15

    # ── Deep work threshold (cognitive_load ≥ this) ────────
    deep_work_load_threshold: float = 7.0

    # ── TLX history (for online learning) ──────────────────
    tlx_history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            k: v
            for k, v in self.__dict__.items()
            if k != "tlx_history"
        }
