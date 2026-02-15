"""
ML Engine — Gemini-powered AI/ML core.

Components:
  1. extract_tasks()       — LLM structured generation (NLP task extraction)
  2. predict_cognitive_load() — LLM as zero-shot predictor + online calibration
  3. recalibrate_from_tlx()  — online weight learning from NASA-TLX labels
"""

from __future__ import annotations

import os
import json
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from models import Task, ParsedTaskList, CogLoadEstimate
from config import CogConfig

load_dotenv()

logger = logging.getLogger(__name__)

# ── Model fallback chain ──────────────────────────────────────
# Primary: gemma-3-27b-it   (higher rate limits, good quality)
# Fallback: gemini-2.0-flash-lite (lighter model, separate quota)
# Last:     gemini-2.0-flash (best quality but strict 15 RPM limit)

MODEL_CHAIN = ["gemma-3-27b-it", "gemini-2.0-flash-lite", "gemini-2.0-flash"]

_llm_cache: dict[str, ChatGoogleGenerativeAI] = {}
_active_model: str | None = None


def _get_llm(model: str | None = None) -> ChatGoogleGenerativeAI:
    """Get or create an LLM instance, with model fallback support."""
    global _active_model
    model_name = model or _active_model or MODEL_CHAIN[0]

    if model_name not in _llm_cache:
        _llm_cache[model_name] = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.2,
            max_retries=1,  # Don't retry endlessly on rate limits
        )
    _active_model = model_name
    return _llm_cache[model_name]


async def _invoke_with_fallback(messages, schema=None):
    """
    Invoke LLM with automatic model fallback on rate-limit errors.
    Tries each model in MODEL_CHAIN until one succeeds.
    Gemma models don't support SystemMessage or JSON mode, so we handle
    those cases with manual parsing.
    """
    last_error = None
    for model_name in MODEL_CHAIN:
        try:
            llm = _get_llm(model_name)
            is_gemma = "gemma" in model_name.lower()

            # Gemma: merge system msgs into user prompt
            msgs = _merge_system_into_user(messages) if is_gemma else messages

            if schema and not is_gemma:
                # Structured output (Gemini models)
                structured = llm.with_structured_output(schema)
                result = await structured.ainvoke(msgs)
            elif schema and is_gemma:
                # Gemma: no JSON mode — ask for JSON in prompt, parse manually
                json_instruction = (
                    f"\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema, "
                    f"no markdown fences, no explanation:\n"
                    f"{schema.model_json_schema()}\n"
                )
                # Append JSON instruction to the last message
                patched = list(msgs)
                last_msg = patched[-1]
                patched[-1] = HumanMessage(content=last_msg.content + json_instruction)
                raw_result = await llm.ainvoke(patched)
                result = _parse_json_response(raw_result.content, schema)
            else:
                result = await llm.ainvoke(msgs)

            logger.info(f"Using model: {model_name}")
            return result
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning(f"{model_name} rate-limited, trying fallback...")
                last_error = e
                continue
            elif "400" in err_str and ("Developer instruction" in err_str or "JSON mode" in err_str):
                logger.warning(f"{model_name} unsupported feature, trying fallback...")
                last_error = e
                continue
            else:
                raise
    raise last_error or RuntimeError("All models exhausted")


def _parse_json_response(text: str, schema):
    """Parse JSON from raw LLM text output and validate against Pydantic schema."""
    import re
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object/array in the text
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            raise ValueError(f"Could not parse JSON from model response: {text[:200]}")

    return schema.model_validate(data)


def _merge_system_into_user(messages) -> list:
    """Merge SystemMessage into HumanMessage for models that don't support system instructions."""
    merged = []
    system_content = ""
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_content += msg.content + "\n\n"
        elif isinstance(msg, HumanMessage):
            if system_content:
                merged.append(HumanMessage(content=system_content + msg.content))
                system_content = ""
            else:
                merged.append(msg)
        else:
            merged.append(msg)
    return merged


# ──────────────────────────────────────────────────────────────
# 1. NLP Task Extraction
# ──────────────────────────────────────────────────────────────

EXTRACT_SYSTEM_PROMPT = """\
You are a task-extraction engine for a cognitive study scheduler.

Given a user's message, extract ONLY the tasks they EXPLICITLY mentioned.
Do NOT invent, assume, or add tasks that the user did not clearly state.
Do NOT break a single task into sub-tasks unless the user listed them separately.

For each task provide:
  - title: concise name matching what the user said (e.g. "Study Calculus")
  - description: brief detail only if the user mentioned it, else empty string
  - category: one of [math, science, programming, writing, reading, general]
  - difficulty: 1-10 estimate based on subject complexity
  - duration_minutes: extract from text if user specified, else use a sensible default (60)

Rules:
  - ONLY extract tasks the user explicitly asked for. Never invent extra tasks.
  - If user says "study calculus for 2 hours" → ONE task, 120 minutes.
  - If user says "study X and finish Y" → TWO tasks (X and Y), nothing more.
  - If user says "plan my day" or "help me plan" with no specific tasks → return ZERO tasks.
  - If user mentions a vague goal like "be productive" → return ZERO tasks.
  - Return valid JSON matching the schema.
"""


async def extract_tasks(message: str) -> list[Task]:
    """Use Gemini to extract tasks from a natural-language message."""
    result: ParsedTaskList = await _invoke_with_fallback(
        [
            SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
            HumanMessage(content=message),
        ],
        schema=ParsedTaskList,
    )

    # Convert ParsedTask → Task (with cognitive_load=0, filled later)
    tasks = []
    for pt in result.tasks:
        tasks.append(
            Task(
                title=pt.title,
                description=pt.description,
                category=pt.category,
                difficulty=pt.difficulty,
                duration_minutes=pt.duration_minutes,
                cognitive_load=0.0,
            )
        )
    return tasks


# ──────────────────────────────────────────────────────────────
# 2. Cognitive Load Prediction
# ──────────────────────────────────────────────────────────────

COG_LOAD_SYSTEM_PROMPT = """\
You are a cognitive-load prediction model.

Given a task and the user's current state, predict the cognitive load on a
scale of 1-10 (float). Consider:
  - Harder subjects → higher load
  - Longer duration → slightly higher load
  - User fatigue (low sleep, high stress, many lectures) makes tasks feel harder
  - Programming / math / science tasks tend to be higher load than reading / writing

Return your prediction as a JSON object with:
  - cognitive_load: float (1-10)
  - reasoning: short explanation (one sentence)
"""


def _build_cog_load_prompt(
    task: Task,
    sleep_hours: float,
    stress_level: int,
    lectures_today: int,
    tlx_examples: list[dict] | None = None,
) -> str:
    """Build the user prompt for cognitive-load prediction."""
    prompt = (
        f"Task: {task.title}\n"
        f"  Description: {task.description or 'N/A'}\n"
        f"  Category: {task.category}\n"
        f"  Difficulty: {task.difficulty}/10\n"
        f"  Estimated duration: {task.duration_minutes} minutes\n"
        f"  Description word-count: {len((task.description or '').split())}\n\n"
        f"User state:\n"
        f"  Sleep: {sleep_hours}h (baseline 8h)\n"
        f"  Stress: {stress_level}/5\n"
        f"  Lectures today: {lectures_today}\n"
    )

    # Online calibration: include past TLX→load correlations as few-shot examples
    if tlx_examples:
        prompt += "\nPast feedback (TLX → actual cognitive load):\n"
        for ex in tlx_examples[-5:]:  # last 5
            prompt += (
                f"  - mental_demand={ex['mental_demand']}, "
                f"effort={ex['effort']} → predicted_load was {ex.get('predicted_load', 'N/A')}\n"
            )
        prompt += "Use this calibration data to refine your prediction.\n"

    return prompt


async def predict_cognitive_load(
    task: Task,
    sleep_hours: float,
    stress_level: int,
    lectures_today: int,
    cfg: CogConfig | None = None,
) -> float:
    """Use Gemini as a zero-shot/few-shot predictor for cognitive load."""
    if cfg is None:
        cfg = CogConfig()

    tlx_examples = cfg.tlx_history if cfg.tlx_history else None

    user_prompt = _build_cog_load_prompt(
        task, sleep_hours, stress_level, lectures_today, tlx_examples
    )

    result: CogLoadEstimate = await _invoke_with_fallback(
        [
            SystemMessage(content=COG_LOAD_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ],
        schema=CogLoadEstimate,
    )

    return result.cognitive_load


# ──────────────────────────────────────────────────────────────
# 3. Online Learning — TLX Recalibration
# ──────────────────────────────────────────────────────────────


def recalibrate_from_tlx(cfg: CogConfig) -> CogConfig:
    """
    After ≥3 TLX labels, adjust fatigue weights.

    - If avg mental_demand > 4.5 → increase fatigue sensitivity
    - If avg mental_demand < 2.5 → decrease fatigue sensitivity

    This is online learning — the model adapts per-user.
    """
    history = cfg.tlx_history
    if len(history) < 3:
        return cfg

    recent = history[-10:]  # use last 10 entries
    avg_mental = sum(e["mental_demand"] for e in recent) / len(recent)
    avg_effort = sum(e["effort"] for e in recent) / len(recent)

    # Adjust fatigue weights
    if avg_mental > 4.5:
        # User reports high mental demand → tasks are harder than predicted
        # Increase fatigue sensitivity so scheduler gives more breaks
        delta = 0.05
        cfg.fatigue_consec_weight = min(1.0, cfg.fatigue_consec_weight + delta)
        cfg.fatigue_total_weight = min(1.0, cfg.fatigue_total_weight + delta * 0.5)
    elif avg_mental < 2.5:
        # User finds tasks easy → reduce fatigue sensitivity
        delta = 0.05
        cfg.fatigue_consec_weight = max(0.1, cfg.fatigue_consec_weight - delta)
        cfg.fatigue_total_weight = max(0.1, cfg.fatigue_total_weight - delta * 0.5)

    # Effort also informs: high effort → user is pushing hard
    if avg_effort > 5.0:
        cfg.fatigue_force_break = max(0.5, cfg.fatigue_force_break - 0.05)
    elif avg_effort < 2.5:
        cfg.fatigue_force_break = min(0.95, cfg.fatigue_force_break + 0.05)

    return cfg
