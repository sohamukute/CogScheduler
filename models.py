"""
Pydantic schemas for the Cognitive-Aware Task Scheduler.

Three groups:
  A. User-facing I/O (ChatRequest, ScheduleResponse)
  B. Internal data (Task, TimeSlot, ScheduledBlock, GamificationState, TLXFeedback)
  C. Gemini structured-output schemas (ParsedTaskList, CogLoadEstimate)
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# A. User-facing I/O
# ──────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Payload sent by the user for every /chat request."""

    message: str = Field(..., description="Natural-language task description")
    sleep_hours: float = Field(..., ge=0, le=24, description="Hours slept last night")
    stress_level: int = Field(..., ge=1, le=5, description="Self-reported stress 1-5")

    # Optional — sensible defaults
    chronotype: str = Field(
        default="normal",
        pattern="^(early|normal|late)$",
        description="Chronotype: early / normal / late",
    )
    lectures_today: int = Field(default=0, ge=0, description="Lectures attended today")
    available_from: str = Field(default="09:00", description="Free-time start HH:MM")
    available_to: str = Field(default="22:00", description="Free-time end HH:MM")
    breaks_at: list[str] = Field(
        default_factory=list,
        description='Fixed break windows, e.g. ["13:00-14:00"]',
    )


class ScheduleBlockOut(BaseModel):
    """A single block in the returned schedule."""

    task_title: str
    start_time: str
    end_time: str
    cognitive_load: float = Field(default=0.0, ge=0, le=10)
    energy_at_start: float = Field(default=0.0, ge=0, le=1)
    fatigue_at_start: float = Field(default=0.0, ge=0, le=1)
    is_break: bool = False
    explanation: str = ""


class GamificationOut(BaseModel):
    xp: int = 0
    level: str = "Student"
    streak: int = 0
    badges: list[str] = Field(default_factory=list)


class CurvePoint(BaseModel):
    time: str
    value: float


class ScheduleResponse(BaseModel):
    """Full payload returned to the user."""

    parsed_tasks: list[dict] = Field(default_factory=list)
    schedule: list[ScheduleBlockOut] = Field(default_factory=list)
    energy_curve: list[CurvePoint] = Field(default_factory=list)
    fatigue_curve: list[CurvePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gamification: GamificationOut = Field(default_factory=GamificationOut)


# ──────────────────────────────────────────────────────────────
# B. Internal data
# ──────────────────────────────────────────────────────────────


class Task(BaseModel):
    """A single extracted / user-supplied task."""

    title: str
    description: str = ""
    category: str = "general"
    difficulty: float = Field(default=5.0, ge=1, le=10)
    duration_minutes: int = Field(default=60, ge=5)
    cognitive_load: float = Field(default=0.0, ge=0, le=10)


class TimeSlot(BaseModel):
    """A contiguous free window (minutes from midnight)."""

    start_min: int
    end_min: int


class ScheduledBlock(BaseModel):
    """Internal representation of a placed block."""

    task_title: str
    start_min: int
    end_min: int
    cognitive_load: float = 0.0
    energy_at_start: float = 0.0
    fatigue_at_start: float = 0.0
    is_break: bool = False
    explanation: str = ""


class GamificationState(BaseModel):
    xp: int = 0
    level: str = "Student"
    streak: int = 0
    badges: list[str] = Field(default_factory=list)


class TLXFeedback(BaseModel):
    """NASA-TLX style feedback for a completed block."""

    block_index: int = Field(..., ge=0)
    mental_demand: int = Field(..., ge=1, le=7)
    effort: int = Field(..., ge=1, le=7)


# ──────────────────────────────────────────────────────────────
# C. Gemini structured-output schemas
# ──────────────────────────────────────────────────────────────


class ParsedTask(BaseModel):
    """Single task extracted by Gemini."""

    title: str
    description: str = ""
    category: str = "general"
    difficulty: float = Field(default=5.0, ge=1, le=10)
    duration_minutes: int = Field(default=60, ge=5)


class ParsedTaskList(BaseModel):
    """What Gemini returns for NLP task extraction."""

    tasks: list[ParsedTask]


class CogLoadEstimate(BaseModel):
    """What Gemini returns for cognitive-load prediction."""

    cognitive_load: float = Field(..., ge=1, le=10)
    reasoning: str = ""
