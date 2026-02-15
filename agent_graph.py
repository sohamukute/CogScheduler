"""
LangGraph agent pipeline for the Cognitive-Aware Task Scheduler.

6 nodes:
  1. parse_input      — Gemini extracts tasks from NL  (LLM)
  2. predict_load     — Gemini predicts cognitive load  (LLM)
  3. compute_capacity — Builds Energy(t) and Fatigue(t) curves (deterministic)
  4. schedule         — Greedy fit: place tasks where Capacity ≥ Load (deterministic)
  5. rebalance        — Cap loads, split long tasks (deterministic)
  6. finalize         — Compute gamification, format response (deterministic)

Graph wiring:
  START → parse_input → predict_load → compute_capacity → schedule
  schedule → [overloaded? yes → rebalance → schedule]  (≤2 retries)
  schedule → [overloaded? no  → finalize → END]
"""

from __future__ import annotations

from typing import TypedDict, Any
from langgraph.graph import StateGraph, END

from models import Task, ScheduledBlock, CurvePoint, GamificationState
from config import CogConfig
from ml_engine import extract_tasks, predict_cognitive_load
from scheduler import schedule as run_schedule, rebalance_tasks
from energy import compute_energy, compute_fatigue
from gamification import compute_gamification


# ──────────────────────────────────────────────────────────────
# Agent State
# ──────────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # Inputs
    raw_message: str
    user_state: dict        # sleep_hours, stress_level, etc.
    config: dict            # serialized CogConfig overrides

    # Node outputs (accumulated)
    parsed_tasks: list      # list[Task]
    tasks_with_load: list   # list[Task] with cognitive_load filled
    blocks: list            # list[ScheduledBlock]
    energy_curve: list      # list[CurvePoint]
    fatigue_curve: list     # list[CurvePoint]
    overload_detected: bool
    rebalance_attempts: int
    warnings: list          # list[str]
    gamification: dict      # GamificationState as dict


# ──────────────────────────────────────────────────────────────
# Node 1 — parse_input (LLM)
# ──────────────────────────────────────────────────────────────

async def parse_input_node(state: AgentState) -> dict:
    """Extract tasks from free-text using Gemini NLP."""
    tasks = await extract_tasks(state["raw_message"])
    return {
        "parsed_tasks": [t.model_dump() for t in tasks],
        "warnings": state.get("warnings", []),
    }


# ──────────────────────────────────────────────────────────────
# Node 2 — predict_load (LLM)
# ──────────────────────────────────────────────────────────────

async def predict_load_node(state: AgentState) -> dict:
    """Predict cognitive load for each extracted task using Gemini ML."""
    user = state["user_state"]
    cfg_dict = state.get("config", {})
    cfg = CogConfig(**{k: v for k, v in cfg_dict.items() if hasattr(CogConfig, k)})

    tasks_with_load = []
    for td in state["parsed_tasks"]:
        task = Task(**td)
        load = await predict_cognitive_load(
            task,
            sleep_hours=user["sleep_hours"],
            stress_level=user["stress_level"],
            lectures_today=user.get("lectures_today", 0),
            cfg=cfg,
        )
        task.cognitive_load = load
        tasks_with_load.append(task.model_dump())

    return {"tasks_with_load": tasks_with_load}


# ──────────────────────────────────────────────────────────────
# Node 3 — compute_capacity (deterministic)
# ──────────────────────────────────────────────────────────────

async def compute_capacity_node(state: AgentState) -> dict:
    """
    Pre-compute energy/fatigue context. This node mainly validates and
    prepares the state for the scheduler. The actual curve computation
    happens inside the scheduler for accuracy.
    """
    # Nothing to compute here that the scheduler doesn't do,
    # but we can add warnings about capacity.
    user = state["user_state"]
    cfg_dict = state.get("config", {})
    cfg = CogConfig(**{k: v for k, v in cfg_dict.items() if hasattr(CogConfig, k)})
    warnings = list(state.get("warnings", []))

    sleep = user["sleep_hours"]
    stress = user["stress_level"]

    # Preview energy at available_from
    avail_from = user.get("available_from", "09:00")
    hour = int(avail_from.split(":")[0]) + int(avail_from.split(":")[1]) / 60
    initial_energy = compute_energy(
        hour, sleep, stress,
        user.get("lectures_today", 0),
        0.0,  # no fatigue yet
        user.get("chronotype", "normal"),
        cfg,
    )

    if initial_energy < 0.4:
        warnings.append(
            f"⚠️ Starting energy is low ({initial_energy:.2f}) — "
            f"consider lighter tasks first"
        )

    return {"warnings": warnings}


# ──────────────────────────────────────────────────────────────
# Node 4 — schedule (deterministic)
# ──────────────────────────────────────────────────────────────

async def schedule_node(state: AgentState) -> dict:
    """Run the greedy scheduler."""
    user = state["user_state"]
    cfg_dict = state.get("config", {})
    cfg = CogConfig(**{k: v for k, v in cfg_dict.items() if hasattr(CogConfig, k)})

    tasks = [Task(**td) for td in state["tasks_with_load"]]

    blocks, energy_curve, fatigue_curve, overload, sched_warnings = run_schedule(
        tasks=tasks,
        available_from=user.get("available_from", "09:00"),
        available_to=user.get("available_to", "22:00"),
        breaks_at=user.get("breaks_at", []),
        sleep_hours=user["sleep_hours"],
        stress_level=user["stress_level"],
        lectures_today=user.get("lectures_today", 0),
        chronotype=user.get("chronotype", "normal"),
        cfg=cfg,
    )

    warnings = list(state.get("warnings", []))
    warnings.extend(sched_warnings)

    # Deduplicate warnings (preserve order)
    seen = set()
    unique_warnings = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique_warnings.append(w)
    warnings = unique_warnings

    return {
        "blocks": [b.model_dump() for b in blocks],
        "energy_curve": [c.model_dump() for c in energy_curve],
        "fatigue_curve": [c.model_dump() for c in fatigue_curve],
        "overload_detected": overload,
        "rebalance_attempts": state.get("rebalance_attempts", 0),
        "warnings": warnings,
    }


# ──────────────────────────────────────────────────────────────
# Node 5 — rebalance (deterministic)
# ──────────────────────────────────────────────────────────────

async def rebalance_node(state: AgentState) -> dict:
    """Cap loads and split long tasks, then retry scheduling."""
    user = state["user_state"]
    cfg_dict = state.get("config", {})
    cfg = CogConfig(**{k: v for k, v in cfg_dict.items() if hasattr(CogConfig, k)})

    tasks = [Task(**td) for td in state["tasks_with_load"]]
    rebalanced = rebalance_tasks(tasks, user["stress_level"], cfg)

    # Don't accumulate rebalance warnings — just keep one
    return {
        "tasks_with_load": [t.model_dump() for t in rebalanced],
        "rebalance_attempts": state.get("rebalance_attempts", 0) + 1,
        "warnings": list(state.get("warnings", [])),
    }


# ──────────────────────────────────────────────────────────────
# Node 6 — finalize (deterministic)
# ──────────────────────────────────────────────────────────────

async def finalize_node(state: AgentState) -> dict:
    """Compute gamification and format response."""
    cfg_dict = state.get("config", {})
    cfg = CogConfig(**{k: v for k, v in cfg_dict.items() if hasattr(CogConfig, k)})

    blocks = [ScheduledBlock(**bd) for bd in state.get("blocks", [])]
    gam = compute_gamification(blocks, cfg)

    return {
        "gamification": gam.model_dump(),
    }


# ──────────────────────────────────────────────────────────────
# Conditional edge: overloaded → rebalance or finalize
# ──────────────────────────────────────────────────────────────

def should_rebalance(state: AgentState) -> str:
    """Route after schedule node."""
    if state.get("overload_detected", False) and state.get("rebalance_attempts", 0) < 2:
        return "rebalance"
    return "finalize"


# ──────────────────────────────────────────────────────────────
# Build the graph
# ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct and compile the LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("parse_input", parse_input_node)
    graph.add_node("predict_load", predict_load_node)
    graph.add_node("compute_capacity", compute_capacity_node)
    graph.add_node("schedule", schedule_node)
    graph.add_node("rebalance", rebalance_node)
    graph.add_node("finalize", finalize_node)

    # Wiring
    graph.set_entry_point("parse_input")
    graph.add_edge("parse_input", "predict_load")
    graph.add_edge("predict_load", "compute_capacity")
    graph.add_edge("compute_capacity", "schedule")

    # Conditional: schedule → rebalance or finalize
    graph.add_conditional_edges(
        "schedule",
        should_rebalance,
        {
            "rebalance": "rebalance",
            "finalize": "finalize",
        },
    )

    # Rebalance loops back to schedule
    graph.add_edge("rebalance", "schedule")

    # Finalize → END
    graph.add_edge("finalize", END)

    return graph.compile()


# ── Module-level compiled graph ───────────────────────────────

cognitive_graph = build_graph()
