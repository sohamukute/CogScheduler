"""
Greedy Scheduler — places tasks where Capacity ≥ Load.

Algorithm:
  1. Parse available_from/to + breaks_at → free TimeSlots
  2. Discretize into 15-min quanta
  3. Sort tasks by cognitive_load DESC (hardest first)
  4. For each task, find the window with the highest capacity sum
  5. Insert breaks when fatigue thresholds are crossed
  6. Build energy_curve and fatigue_curve for visualization
"""

from __future__ import annotations

import math
from models import Task, ScheduledBlock, TimeSlot, CurvePoint
from config import CogConfig
from energy import (
    compute_energy,
    compute_fatigue,
    apply_break_recovery,
    arousal_cap,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _parse_time(t: str) -> int:
    """'HH:MM' → minutes from midnight."""
    parts = t.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _fmt_time(m: int) -> str:
    """minutes from midnight → 'HH:MM'."""
    return f"{m // 60:02d}:{m % 60:02d}"


def parse_free_slots(
    available_from: str,
    available_to: str,
    breaks_at: list[str],
) -> list[TimeSlot]:
    """
    Convert user availability + fixed breaks into a sorted list of free TimeSlots.
    """
    start = _parse_time(available_from)
    end = _parse_time(available_to)

    # Parse break windows
    break_windows: list[tuple[int, int]] = []
    for b in breaks_at:
        if "-" in b:
            parts = b.split("-")
            bs = _parse_time(parts[0])
            be = _parse_time(parts[1])
            break_windows.append((bs, be))

    # Sort breaks
    break_windows.sort()

    # Build free slots by subtracting breaks from [start, end]
    slots: list[TimeSlot] = []
    cursor = start
    for bs, be in break_windows:
        if bs > cursor:
            slots.append(TimeSlot(start_min=cursor, end_min=min(bs, end)))
        cursor = max(cursor, be)
    if cursor < end:
        slots.append(TimeSlot(start_min=cursor, end_min=end))

    return slots


def _should_insert_break(
    consec_deep_min: int,
    total_deep_min: int,
    fatigue: float,
    cfg: CogConfig,
) -> bool:
    """Decide if a break should be inserted now."""
    if fatigue >= cfg.fatigue_force_break:
        return True
    if consec_deep_min >= cfg.consec_threshold_min:
        return True
    if consec_deep_min >= cfg.short_break_trigger_min and fatigue > 0.5:
        return True
    return False


def _break_duration(deep_block_count: int, cfg: CogConfig) -> int:
    """Short (15 min) or long (25 min) break."""
    if deep_block_count >= 3:
        return cfg.long_break_duration
    return cfg.short_break_duration


# ──────────────────────────────────────────────────────────────
# Main scheduler
# ──────────────────────────────────────────────────────────────

def schedule(
    tasks: list[Task],
    available_from: str,
    available_to: str,
    breaks_at: list[str],
    sleep_hours: float,
    stress_level: int,
    lectures_today: int,
    chronotype: str = "normal",
    cfg: CogConfig | None = None,
) -> tuple[list[ScheduledBlock], list[CurvePoint], list[CurvePoint], bool, list[str]]:
    """
    Greedy scheduling algorithm.

    Returns:
        blocks         – ordered list of ScheduledBlock (tasks + breaks)
        energy_curve   – [{time, value}, ...]
        fatigue_curve  – [{time, value}, ...]
        overload       – True if any task couldn't be placed
        warnings       – list of warning strings
    """
    if cfg is None:
        cfg = CogConfig()

    Q = cfg.quantum_min  # 15 min
    warnings: list[str] = []

    # ── Parse free time ──
    free_slots = parse_free_slots(available_from, available_to, breaks_at)
    if not free_slots:
        return [], [], [], True, ["No free time available in the given window."]

    # ── Build quantum timeline ──
    # Each quantum is (start_min, end_min) and tracks occupancy
    quanta: list[dict] = []
    for slot in free_slots:
        t = slot.start_min
        while t + Q <= slot.end_min:
            quanta.append({"start": t, "end": t + Q, "occupied": False})
            t += Q

    if not quanta:
        return [], [], [], True, ["Available window too short for any tasks."]

    # ── Sort tasks by cognitive_load DESC (hardest first) ──
    sorted_tasks = sorted(tasks, key=lambda t: t.cognitive_load, reverse=True)

    # ── Pre-compute energy for every quantum (used for smart placement) ──
    for q in quanta:
        hour = q["start"] / 60.0
        q["energy"] = compute_energy(
            hour, sleep_hours, stress_level, lectures_today,
            0.0, chronotype, cfg,  # base energy without accumulated fatigue
        )

    # ── State trackers ──
    consec_deep_min = 0
    total_deep_min = 0
    deep_block_count = 0
    current_fatigue = 0.0

    blocks: list[ScheduledBlock] = []
    overload = False

    # ── Warnings based on user state ──
    if sleep_hours < 7:
        warnings.append(
            f"⚠️ Low sleep ({sleep_hours}h) — reduced capacity, "
            f"deep tasks capped at {cfg.consec_threshold_min} min blocks"
        )
    if stress_level >= cfg.stress_cap_threshold:
        warnings.append(
            f"⚠️ High stress (level {stress_level}) — "
            f"cognitive load will be capped at {cfg.max_load_under_stress}"
        )

    # ── Place each task ──
    for task in sorted_tasks:
        needed_quanta = math.ceil(task.duration_minutes / Q)
        task_load = task.cognitive_load
        is_deep = task_load >= cfg.deep_work_load_threshold

        # Check arousal cap
        cap = arousal_cap(stress_level, current_fatigue, cfg)
        if cap is not None and task_load > cap:
            task_load = cap
            warnings.append(
                f"⚠️ Yerkes-Dodson cap: '{task.title}' load capped "
                f"from {task.cognitive_load:.1f} to {cap:.1f}"
            )

        # ── Find best contiguous window ──
        # Strategy: for high-load tasks → pick the window with highest average
        # energy (peak energy time). For low-load tasks → pick the window with
        # lowest-but-sufficient energy (save peak energy for harder tasks).
        best_start_idx = -1
        best_score = -1.0
        remaining = needed_quanta

        for i in range(len(quanta)):
            if i + remaining > len(quanta):
                break

            contiguous = True
            window_energy_sum = 0.0
            for j in range(remaining):
                q = quanta[i + j]
                if q["occupied"]:
                    contiguous = False
                    break
                if j > 0 and quanta[i + j]["start"] != quanta[i + j - 1]["end"]:
                    contiguous = False
                    break
                # Use pre-computed base energy for scoring
                if q["energy"] <= 0.02:
                    contiguous = False
                    break
                window_energy_sum += q["energy"]

            if not contiguous:
                continue

            avg_energy = window_energy_sum / remaining

            # Score: high-load tasks want highest energy windows,
            # low-load tasks want lowest-sufficient-energy windows
            # This naturally spreads tasks throughout the day.
            if is_deep:
                # Deep work → maximize energy match
                score = avg_energy
            else:
                # Light work → prefer lower-energy windows (save peaks)
                # But still needs min energy, so use inverted score
                score = 1.0 - avg_energy + 0.01  # small offset to avoid zero

            if score > best_score:
                best_score = score
                best_start_idx = i

        if best_start_idx < 0:
            # Can't place this task
            overload = True
            warnings.append(
                f"⚠️ Could not schedule '{task.title}' — "
                f"insufficient capacity in available time"
            )
            continue

        # ── Check if break needed before placing ──
        if is_deep and _should_insert_break(consec_deep_min, total_deep_min, current_fatigue, cfg):
            # Find a free quantum for the break right before the task
            brk_dur = _break_duration(deep_block_count, cfg)
            brk_quanta_needed = math.ceil(brk_dur / Q)

            # Try to insert break just before the task window
            brk_start_idx = best_start_idx
            # Check if we have room
            if brk_start_idx >= 0 and brk_start_idx + brk_quanta_needed + remaining <= len(quanta):
                # Check break quanta are free and contiguous
                brk_ok = True
                for bi in range(brk_quanta_needed):
                    q = quanta[brk_start_idx + bi]
                    if q["occupied"]:
                        brk_ok = False
                        break
                    if bi > 0 and quanta[brk_start_idx + bi]["start"] != quanta[brk_start_idx + bi - 1]["end"]:
                        brk_ok = False
                        break

                if brk_ok:
                    # Place break
                    brk_start = quanta[brk_start_idx]["start"]
                    brk_end = quanta[brk_start_idx + brk_quanta_needed - 1]["end"]
                    for bi in range(brk_quanta_needed):
                        quanta[brk_start_idx + bi]["occupied"] = True

                    blocks.append(ScheduledBlock(
                        task_title="🧘 Recovery Break",
                        start_min=brk_start,
                        end_min=brk_end,
                        cognitive_load=0.0,
                        energy_at_start=compute_energy(
                            brk_start / 60.0, sleep_hours, stress_level,
                            lectures_today, current_fatigue, chronotype, cfg,
                        ),
                        fatigue_at_start=current_fatigue,
                        is_break=True,
                        explanation=f"{consec_deep_min} min deep work threshold — recovery needed",
                    ))

                    # Apply break recovery
                    current_fatigue = apply_break_recovery(current_fatigue, cfg.break_recovery_factor)
                    consec_deep_min = 0
                    deep_block_count = 0

                    # Shift task placement after break
                    best_start_idx = brk_start_idx + brk_quanta_needed

        # ── Verify task still fits after potential break insertion ──
        can_place = True
        if best_start_idx + remaining > len(quanta):
            can_place = False
        else:
            for j in range(remaining):
                if quanta[best_start_idx + j]["occupied"]:
                    can_place = False
                    break
                if j > 0 and quanta[best_start_idx + j]["start"] != quanta[best_start_idx + j - 1]["end"]:
                    can_place = False
                    break

        if not can_place:
            overload = True
            warnings.append(
                f"⚠️ Could not schedule '{task.title}' after inserting break"
            )
            continue

        # ── Place the task ──
        task_start = quanta[best_start_idx]["start"]
        task_end = quanta[best_start_idx + remaining - 1]["end"]

        # Use accumulator-based fatigue for display (matches scoring)
        display_fatigue = compute_fatigue(consec_deep_min, total_deep_min, cfg)
        energy_at_start = compute_energy(
            task_start / 60.0, sleep_hours, stress_level,
            lectures_today, display_fatigue, chronotype, cfg,
        )

        # Determine explanation
        hour = task_start / 60.0
        if 8 <= hour <= 11:
            explanation = "Peak morning energy — ideal for high-load tasks"
        elif 14 <= hour <= 16:
            explanation = "Afternoon peak after lunch recovery"
        elif 11 < hour < 14:
            explanation = "Midday slot — moderate energy"
        else:
            explanation = "Available slot — energy managed by breaks"

        for j in range(remaining):
            quanta[best_start_idx + j]["occupied"] = True

        blocks.append(ScheduledBlock(
            task_title=task.title,
            start_min=task_start,
            end_min=task_end,
            cognitive_load=task_load,
            energy_at_start=round(energy_at_start, 2),
            fatigue_at_start=round(display_fatigue, 2),
            is_break=False,
            explanation=explanation,
        ))

        # ── Update state ──
        duration_placed = task_end - task_start
        if is_deep:
            consec_deep_min += duration_placed
            total_deep_min += duration_placed
            deep_block_count += 1
        else:
            consec_deep_min = 0  # Non-deep resets consecutive counter

        current_fatigue = compute_fatigue(consec_deep_min, total_deep_min, cfg)

        # ── Auto-insert break after task if fatigue is high ──
        if _should_insert_break(consec_deep_min, total_deep_min, current_fatigue, cfg):
            brk_dur = _break_duration(deep_block_count, cfg)
            brk_quanta_needed = math.ceil(brk_dur / Q)
            after_idx = best_start_idx + remaining

            if after_idx + brk_quanta_needed <= len(quanta):
                brk_ok = True
                for bi in range(brk_quanta_needed):
                    q = quanta[after_idx + bi]
                    if q["occupied"]:
                        brk_ok = False
                        break
                    if bi > 0 and quanta[after_idx + bi]["start"] != quanta[after_idx + bi - 1]["end"]:
                        brk_ok = False
                        break

                if brk_ok:
                    brk_start = quanta[after_idx]["start"]
                    brk_end = quanta[after_idx + brk_quanta_needed - 1]["end"]
                    for bi in range(brk_quanta_needed):
                        quanta[after_idx + bi]["occupied"] = True

                    blocks.append(ScheduledBlock(
                        task_title="🧘 Recovery Break",
                        start_min=brk_start,
                        end_min=brk_end,
                        cognitive_load=0.0,
                        energy_at_start=compute_energy(
                            brk_start / 60.0, sleep_hours, stress_level,
                            lectures_today, current_fatigue, chronotype, cfg,
                        ),
                        fatigue_at_start=round(current_fatigue, 2),
                        is_break=True,
                        explanation=f"{consec_deep_min} min deep work — recovery cycle triggered",
                    ))

                    current_fatigue = apply_break_recovery(current_fatigue, cfg.break_recovery_factor)
                    consec_deep_min = 0
                    deep_block_count = 0

    # ── Sort blocks by start time ──
    blocks.sort(key=lambda b: b.start_min)

    # ── Build energy & fatigue curves ──
    energy_curve: list[CurvePoint] = []
    fatigue_curve: list[CurvePoint] = []
    running_consec = 0
    running_total = 0
    running_fatigue = 0.0

    timeline_start = _parse_time(available_from)
    timeline_end = _parse_time(available_to)

    for t_min in range(timeline_start, timeline_end + 1, Q):
        # Check if this quantum is inside a block
        in_block = False
        is_break_block = False
        block_load = 0.0
        for b in blocks:
            if b.start_min <= t_min < b.end_min:
                in_block = True
                is_break_block = b.is_break
                block_load = b.cognitive_load
                break

        if in_block and not is_break_block:
            is_deep_q = block_load >= cfg.deep_work_load_threshold
            if is_deep_q:
                running_consec += Q
                running_total += Q
        elif is_break_block:
            running_consec = 0
            running_fatigue = apply_break_recovery(running_fatigue, cfg.break_recovery_factor)

        running_fatigue = compute_fatigue(running_consec, running_total, cfg)
        e = compute_energy(
            t_min / 60.0, sleep_hours, stress_level,
            lectures_today, running_fatigue, chronotype, cfg,
        )

        energy_curve.append(CurvePoint(time=_fmt_time(t_min), value=round(e, 3)))
        fatigue_curve.append(CurvePoint(time=_fmt_time(t_min), value=round(running_fatigue, 3)))

    return blocks, energy_curve, fatigue_curve, overload, warnings


# ──────────────────────────────────────────────────────────────
# Rebalance — cap loads and split long tasks
# ──────────────────────────────────────────────────────────────

def rebalance_tasks(
    tasks: list[Task],
    stress_level: int,
    cfg: CogConfig | None = None,
) -> list[Task]:
    """
    Cap cognitive loads under stress (Yerkes-Dodson) and split tasks
    that exceed the consecutive threshold into parts.
    """
    if cfg is None:
        cfg = CogConfig()

    result: list[Task] = []
    for task in tasks:
        load = task.cognitive_load

        # Cap under high stress
        if stress_level >= cfg.stress_cap_threshold:
            load = min(load, cfg.max_load_under_stress)

        # Split long tasks
        if task.duration_minutes > cfg.consec_threshold_min:
            n_parts = math.ceil(task.duration_minutes / cfg.consec_threshold_min)
            part_duration = math.ceil(task.duration_minutes / n_parts)
            for i in range(n_parts):
                result.append(Task(
                    title=f"{task.title} (Part {i + 1})",
                    description=task.description,
                    category=task.category,
                    difficulty=task.difficulty,
                    duration_minutes=part_duration,
                    cognitive_load=load,
                ))
        else:
            result.append(Task(
                title=task.title,
                description=task.description,
                category=task.category,
                difficulty=task.difficulty,
                duration_minutes=task.duration_minutes,
                cognitive_load=load,
            ))

    return result
