"""
FastAPI server for the Cognitive-Aware Task Scheduler.

Endpoints:
  POST /chat          — Full NL → schedule pipeline (LangGraph)
  POST /schedule      — Direct schedule (skip NLP, pass tasks directly)
  POST /tlx-feedback  — NASA-TLX feedback → online learning
  GET  /config        — Current CogConfig
  PUT  /config        — Update CogConfig parameters
"""

from __future__ import annotations

import math
import uuid
import json
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

from models import (
    ChatRequest,
    ScheduleResponse,
    ScheduleBlockOut,
    CurvePoint,
    GamificationOut,
    Task,
    TLXFeedback,
)
from config import CogConfig
from agent_graph import cognitive_graph
from scheduler import schedule as run_schedule, rebalance_tasks, _fmt_time
from gamification import compute_gamification
from ml_engine import recalibrate_from_tlx
import google_auth
import supabase_client as supa
import timetable_extractor as timetable

logger = logging.getLogger(__name__)


# ── Global config (mutable, per-user in production would be per-session) ──

_config = CogConfig()

# ── In-memory session store (per-session, persists during server life) ──

_profile: dict = {}
_last_schedule: dict | None = None
_timetable_data: dict | None = None
_current_session: str | None = None  # active Google session ID
_user_data: dict | None = None  # logged-in user info


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    print("🧠 Cognitive-Aware Task Scheduler starting…")
    yield
    print("👋 Shutting down.")


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Cognitive-Aware Task Scheduler",
    description="ML-powered study scheduler with Deep Work gamification",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────

def _block_to_out(bd: dict) -> ScheduleBlockOut:
    """Convert internal ScheduledBlock dict → ScheduleBlockOut."""
    return ScheduleBlockOut(
        task_title=bd["task_title"],
        start_time=_fmt_time(bd["start_min"]),
        end_time=_fmt_time(bd["end_min"]),
        cognitive_load=bd.get("cognitive_load", 0),
        energy_at_start=bd.get("energy_at_start", 0),
        fatigue_at_start=bd.get("fatigue_at_start", 0),
        is_break=bd.get("is_break", False),
        explanation=bd.get("explanation", ""),
    )


# ──────────────────────────────────────────────────────────────
# POST /chat — Full pipeline
# ──────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ScheduleResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Full NL → schedule pipeline:
    parse_input → predict_load → compute_capacity → schedule
    [→ rebalance if overloaded] → finalize
    """
    global _config

    initial_state = {
        "raw_message": req.message,
        "user_state": {
            "sleep_hours": req.sleep_hours,
            "stress_level": req.stress_level,
            "chronotype": req.chronotype,
            "lectures_today": req.lectures_today,
            "available_from": req.available_from,
            "available_to": req.available_to,
            "breaks_at": req.breaks_at,
        },
        "config": _config.to_dict(),
        "warnings": [],
        "rebalance_attempts": 0,
    }

    # Run the LangGraph pipeline
    result = await cognitive_graph.ainvoke(initial_state)

    # Format response
    blocks_out = [_block_to_out(bd) for bd in result.get("blocks", [])]
    energy_curve = [CurvePoint(**c) for c in result.get("energy_curve", [])]
    fatigue_curve = [CurvePoint(**c) for c in result.get("fatigue_curve", [])]

    parsed_tasks = result.get("parsed_tasks", [])
    # Merge cognitive_load from tasks_with_load
    twl = {t["title"]: t for t in result.get("tasks_with_load", [])}
    for pt in parsed_tasks:
        if pt["title"] in twl:
            pt["cognitive_load"] = twl[pt["title"]].get("cognitive_load", 0)

    gam_dict = result.get("gamification", {})

    return ScheduleResponse(
        parsed_tasks=parsed_tasks,
        schedule=blocks_out,
        energy_curve=energy_curve,
        fatigue_curve=fatigue_curve,
        warnings=result.get("warnings", []),
        gamification=GamificationOut(**gam_dict),
    )


# ──────────────────────────────────────────────────────────────
# POST /schedule — Direct (skip NLP)
# ──────────────────────────────────────────────────────────────

class DirectScheduleRequest(BaseModel):
    tasks: list[Task]
    sleep_hours: float = Field(..., ge=0, le=24)
    stress_level: int = Field(..., ge=1, le=5)
    chronotype: str = "normal"
    lectures_today: int = 0
    available_from: str = "09:00"
    available_to: str = "22:00"
    breaks_at: list[str] = Field(default_factory=list)


@app.post("/schedule", response_model=ScheduleResponse)
async def schedule_endpoint(req: DirectScheduleRequest):
    """Schedule pre-defined tasks (skip NLP extraction)."""
    global _config

    tasks = req.tasks

    blocks, energy_curve, fatigue_curve, overload, warnings = run_schedule(
        tasks=tasks,
        available_from=req.available_from,
        available_to=req.available_to,
        breaks_at=req.breaks_at,
        sleep_hours=req.sleep_hours,
        stress_level=req.stress_level,
        lectures_today=req.lectures_today,
        chronotype=req.chronotype,
        cfg=_config,
    )

    # Rebalance if overloaded (up to 2 attempts)
    if overload:
        for _ in range(2):
            tasks = rebalance_tasks(tasks, req.stress_level, _config)
            blocks, energy_curve, fatigue_curve, overload, w2 = run_schedule(
                tasks=tasks,
                available_from=req.available_from,
                available_to=req.available_to,
                breaks_at=req.breaks_at,
                sleep_hours=req.sleep_hours,
                stress_level=req.stress_level,
                lectures_today=req.lectures_today,
                chronotype=req.chronotype,
                cfg=_config,
            )
            warnings.extend(w2)
            if not overload:
                break

    from models import ScheduledBlock as SB
    sched_blocks = [SB(**b.model_dump()) for b in blocks]
    gam = compute_gamification(sched_blocks, _config)

    blocks_out = [
        ScheduleBlockOut(
            task_title=b.task_title,
            start_time=_fmt_time(b.start_min),
            end_time=_fmt_time(b.end_min),
            cognitive_load=b.cognitive_load,
            energy_at_start=b.energy_at_start,
            fatigue_at_start=b.fatigue_at_start,
            is_break=b.is_break,
            explanation=b.explanation,
        )
        for b in blocks
    ]

    return ScheduleResponse(
        parsed_tasks=[t.model_dump() for t in tasks],
        schedule=blocks_out,
        energy_curve=[c for c in energy_curve],
        fatigue_curve=[c for c in fatigue_curve],
        warnings=warnings,
        gamification=GamificationOut(**gam.model_dump()),
    )


# ──────────────────────────────────────────────────────────────
# POST /tlx-feedback — Online learning
# ──────────────────────────────────────────────────────────────

@app.post("/tlx-feedback")
async def tlx_feedback_endpoint(fb: TLXFeedback):
    """
    Accept NASA-TLX feedback and trigger online recalibration.
    """
    global _config

    _config.tlx_history.append({
        "block_index": fb.block_index,
        "mental_demand": fb.mental_demand,
        "effort": fb.effort,
    })

    _config = recalibrate_from_tlx(_config)

    return {
        "status": "ok",
        "tlx_entries": len(_config.tlx_history),
        "updated_weights": {
            "fatigue_consec_weight": round(_config.fatigue_consec_weight, 3),
            "fatigue_total_weight": round(_config.fatigue_total_weight, 3),
            "fatigue_force_break": round(_config.fatigue_force_break, 3),
        },
    }


# ──────────────────────────────────────────────────────────────
# GET / PUT /config
# ──────────────────────────────────────────────────────────────

@app.get("/config")
async def get_config():
    """Return the current scheduler configuration."""
    return _config.to_dict()


@app.put("/config")
async def update_config(updates: dict):
    """Update specific configuration parameters."""
    global _config
    for key, value in updates.items():
        if hasattr(_config, key) and key != "tlx_history":
            setattr(_config, key, value)
        else:
            raise HTTPException(400, f"Unknown config key: {key}")
    return _config.to_dict()


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cognitive-scheduler"}


# ──────────────────────────────────────────────────────────────
# Profile endpoints
# ──────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    name: str = ""
    role: str = "student"  # student | professional | researcher
    chronotype: str = "normal"  # early | normal | late
    wake_time: str = "07:00"
    sleep_time: str = "23:00"
    sleep_hours: float = 7.0
    stress_level: int = 2
    daily_commitments: list[str] = Field(default_factory=list)
    break_preferences: list[str] = Field(default_factory=list)
    lectures_today: int = 0
    # Professional fields
    occupation: str = ""  # e.g. "Software Engineer", "Doctor"
    work_hours: str = ""  # e.g. "09:00-17:00"
    meetings_today: int = 0
    occupation_busy_slots: list[str] = Field(default_factory=list)  # e.g. ["09:00-12:00 Client calls"]
    # Timetable
    has_timetable: bool = False
    timetable_answers: dict = Field(default_factory=dict)


@app.get("/profile")
async def get_profile():
    """Get user profile (or empty defaults). If logged in, load from Supabase."""
    global _profile

    # Try loading from Supabase if logged in and profile is empty
    if _user_data and not _profile.get("name"):
        db_user = supa.get_user_by_google_id(_user_data["google_id"])
        if db_user:
            saved = supa.get_profile(db_user["id"])
            if saved:
                _profile.update(saved)
                _profile["name"] = _user_data.get("name", _profile.get("name", ""))

    return _profile if _profile else UserProfile().model_dump()


@app.put("/profile")
async def update_profile(profile: UserProfile):
    """Set/update user profile. Persists to Supabase if logged in."""
    global _profile
    _profile = profile.model_dump()

    # Persist to Supabase
    if _user_data:
        db_user = supa.get_user_by_google_id(_user_data["google_id"])
        if db_user:
            supa.upsert_profile(db_user["id"], _profile)

    return _profile


# ──────────────────────────────────────────────────────────────
# Conversational chat — multi-turn aware
# ──────────────────────────────────────────────────────────────

class ConversationRequest(BaseModel):
    message: str
    # Profile fields auto-injected from saved profile, can override here
    sleep_hours: Optional[float] = None
    stress_level: Optional[int] = None
    chronotype: Optional[str] = None
    lectures_today: Optional[int] = None
    available_from: Optional[str] = None
    available_to: Optional[str] = None
    breaks_at: Optional[list[str]] = None


@app.post("/converse")
async def converse_endpoint(req: ConversationRequest):
    """
    Conversational endpoint: merges saved profile with request,
    runs the full pipeline, and stores the last schedule.
    """
    global _config, _last_schedule

    # Merge profile defaults with explicit overrides
    profile = UserProfile(**(_profile or {}))
    sleep = req.sleep_hours if req.sleep_hours is not None else profile.sleep_hours
    stress = req.stress_level if req.stress_level is not None else profile.stress_level
    chrono = req.chronotype or profile.chronotype
    avail_from = req.available_from or profile.wake_time
    avail_to = req.available_to or profile.sleep_time
    breaks = req.breaks_at if req.breaks_at is not None else profile.break_preferences

    # ── Merge daily_commitments + occupation_busy_slots as blocked time ──
    # These are time-blocked commitments (lectures, labs, work meetings) that
    # the scheduler must treat as unavailable windows.
    commitment_blocks = []
    for c in (profile.daily_commitments or []):
        # Format: "09:00-10:30 Math Lecture" or "09:00-10:30"
        if isinstance(c, str) and "-" in c:
            time_part = c.split()[0] if " " in c else c
            if "-" in time_part:
                commitment_blocks.append(time_part)
    for slot in (profile.occupation_busy_slots or []):
        if isinstance(slot, str) and "-" in slot:
            time_part = slot.split()[0] if " " in slot else slot
            if "-" in time_part:
                commitment_blocks.append(time_part)
    # Add commitments to breaks so the scheduler blocks those windows
    breaks = list(breaks) + commitment_blocks

    # Auto-derive lectures_today from actual commitment blocks
    # instead of relying on user-provided number
    lectures = len(commitment_blocks) if commitment_blocks else 0

    # Build chat request for existing pipeline
    chat_req = ChatRequest(
        message=req.message,
        sleep_hours=sleep,
        stress_level=max(1, min(5, stress)),
        chronotype=chrono,
        lectures_today=lectures,
        available_from=avail_from,
        available_to=avail_to,
        breaks_at=breaks,
    )

    initial_state = {
        "raw_message": chat_req.message,
        "user_state": {
            "sleep_hours": chat_req.sleep_hours,
            "stress_level": chat_req.stress_level,
            "chronotype": chat_req.chronotype,
            "lectures_today": chat_req.lectures_today,
            "available_from": chat_req.available_from,
            "available_to": chat_req.available_to,
            "breaks_at": chat_req.breaks_at,
        },
        "config": _config.to_dict(),
        "warnings": [],
        "rebalance_attempts": 0,
    }

    result = await cognitive_graph.ainvoke(initial_state)

    blocks_out = [_block_to_out(bd) for bd in result.get("blocks", [])]
    energy_curve = [CurvePoint(**c) for c in result.get("energy_curve", [])]
    fatigue_curve = [CurvePoint(**c) for c in result.get("fatigue_curve", [])]

    parsed_tasks = result.get("parsed_tasks", [])
    twl = {t["title"]: t for t in result.get("tasks_with_load", [])}
    for pt in parsed_tasks:
        if pt["title"] in twl:
            pt["cognitive_load"] = twl[pt["title"]].get("cognitive_load", 0)

    gam_dict = result.get("gamification", {})

    response = ScheduleResponse(
        parsed_tasks=parsed_tasks,
        schedule=blocks_out,
        energy_curve=energy_curve,
        fatigue_curve=fatigue_curve,
        warnings=result.get("warnings", []),
        gamification=GamificationOut(**gam_dict),
    )

    _last_schedule = response.model_dump()

    # Persist schedule to Supabase
    if _user_data:
        db_user = supa.get_user_by_google_id(_user_data["google_id"])
        if db_user:
            supa.save_schedule(db_user["id"], _last_schedule)

    return _last_schedule


# ──────────────────────────────────────────────────────────────
# Google OAuth2 flow
# ──────────────────────────────────────────────────────────────

@app.get("/auth/google")
async def google_login(response: Response):
    """Redirect user to Google consent screen."""
    if not google_auth.is_configured():
        raise HTTPException(501, "Google OAuth not configured — set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")
    session_id = str(uuid.uuid4())
    auth_url = google_auth.get_auth_url(session_id)
    return {"auth_url": auth_url, "session_id": session_id}


@app.get("/auth/google/callback")
async def google_callback(code: str, state: str):
    """Handle Google OAuth callback, exchange code for tokens."""
    global _current_session, _user_data, _profile

    try:
        user_info = google_auth.exchange_code(code, state)
    except Exception as e:
        logger.error(f"Google OAuth exchange failed: {e}")
        return RedirectResponse(f"{google_auth.FRONTEND_URL}?auth_error=exchange_failed")

    _current_session = state
    _user_data = user_info

    # Persist to Supabase
    db_user = supa.upsert_user(
        google_id=user_info["google_id"],
        email=user_info["email"],
        name=user_info["name"],
        avatar_url=user_info.get("avatar_url", ""),
    )

    # Load saved profile from Supabase if exists
    if db_user:
        saved_profile = supa.get_profile(db_user["id"])
        if saved_profile:
            _profile.update(saved_profile)
            _profile["name"] = user_info["name"]

    # Redirect back to frontend with session info
    redirect_url = (
        f"{google_auth.FRONTEND_URL}"
        f"?auth_success=true"
        f"&session_id={state}"
        f"&name={user_info['name']}"
        f"&email={user_info['email']}"
        f"&avatar={user_info.get('avatar_url', '')}"
    )
    return RedirectResponse(redirect_url)


@app.get("/auth/me")
async def auth_me():
    """Return current logged-in user info."""
    if not _user_data:
        return {"authenticated": False}
    return {
        "authenticated": True,
        **_user_data,
        "session_id": _current_session,
    }


@app.post("/auth/logout")
async def auth_logout():
    """Clear session."""
    global _current_session, _user_data
    _current_session = None
    _user_data = None
    return {"status": "logged_out"}


# ──────────────────────────────────────────────────────────────
# Timetable extraction (PDF / Image upload)
# ──────────────────────────────────────────────────────────────

@app.post("/timetable/extract")
async def extract_timetable_endpoint(file: UploadFile = File(...)):
    """
    Upload a college/school timetable (PDF or image).
    Uses Gemini multimodal to extract subjects, schedule, groups, electives.
    """
    global _timetable_data

    allowed_types = {
        "application/pdf",
        "image/png", "image/jpeg", "image/jpg",
        "image/webp", "image/gif",
    }
    content_type = file.content_type or ""
    if content_type not in allowed_types:
        raise HTTPException(
            400,
            f"Unsupported file type: {content_type}. Use PDF, PNG, JPG, or WEBP."
        )

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "File too large. Maximum 10MB.")

    try:
        result = await timetable.extract_timetable(file_bytes, content_type)
        _timetable_data = result
        return result
    except Exception as e:
        logger.error(f"Timetable extraction failed: {e}")
        raise HTTPException(500, f"Failed to extract timetable: {str(e)}")


@app.post("/timetable/personalize")
async def personalize_timetable_endpoint(answers: dict):
    """
    Personalize timetable based on user's group/elective selections.
    Expects: {"group": "G1", "elective_mon_14": "Subject A", ...}
    """
    global _timetable_data, _profile

    if not _timetable_data:
        raise HTTPException(404, "No timetable uploaded. Upload one first via /timetable/extract.")

    personalized = timetable.personalize_timetable(_timetable_data, answers)
    _timetable_data = personalized

    # Auto-populate daily commitments from today's timetable
    commitments = timetable.timetable_to_commitments(personalized)
    _profile["daily_commitments"] = commitments
    _profile["lectures_today"] = len(commitments)

    return {
        "personalized_schedule": personalized.get("schedule", []),
        "free_slots": personalized.get("free_slots", {}),
        "daily_summary": personalized.get("daily_summary", {}),
        "todays_commitments": commitments,
    }


@app.get("/timetable")
async def get_timetable():
    """Get the currently loaded timetable data."""
    if not _timetable_data:
        return {"loaded": False}
    return {"loaded": True, "data": _timetable_data}


# ──────────────────────────────────────────────────────────────
# Google Calendar — push schedule
# ──────────────────────────────────────────────────────────────

@app.post("/calendar/sync")
async def sync_to_google_calendar():
    """Push the last generated schedule to Google Calendar."""
    if not _current_session:
        raise HTTPException(401, "Not authenticated with Google. Login first.")
    if not _last_schedule or not _last_schedule.get("schedule"):
        raise HTTPException(404, "No schedule generated yet.")

    result = google_auth.push_schedule_to_calendar(
        _current_session,
        _last_schedule["schedule"],
    )
    if "error" in result:
        raise HTTPException(401, result["error"])

    # Mark as synced in Supabase
    if _user_data:
        db_user = supa.get_user_by_google_id(_user_data["google_id"])
        if db_user:
            latest = supa.get_latest_schedule(db_user["id"])
            if latest:
                supa.mark_calendar_synced(latest["id"])

    return {
        "status": "synced",
        "events_created": result["created"],
        "errors": result.get("errors", 0),
    }


@app.get("/calendar/events")
async def get_calendar_events():
    """Fetch today's events from the user's Google Calendar."""
    if not _current_session:
        raise HTTPException(401, "Not authenticated with Google.")
    events = google_auth.get_today_events(_current_session)
    return {"events": events, "count": len(events)}


# ──────────────────────────────────────────────────────────────
# Google Calendar ICS export
# ──────────────────────────────────────────────────────────────

@app.get("/calendar/export")
async def export_calendar():
    """
    Export the last generated schedule as an ICS file.
    Users can import this into Google Calendar, Apple Calendar, Outlook, etc.
    """
    if not _last_schedule or not _last_schedule.get("schedule"):
        raise HTTPException(404, "No schedule generated yet. Generate a schedule first.")

    today = datetime.now().strftime("%Y%m%d")
    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CogScheduler//HackXcelerate2026//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:CogScheduler - {datetime.now().strftime('%b %d')}",
    ]

    for block in _last_schedule["schedule"]:
        uid = str(uuid.uuid4())
        start_hhmm = block["start_time"].replace(":", "")
        end_hhmm = block["end_time"].replace(":", "")
        summary = block["task_title"]
        desc = block.get("explanation", "")
        if not block.get("is_break", False):
            desc += f"\\nCognitive Load: {block.get('cognitive_load', 0):.1f}/10"
            desc += f"\\nEnergy: {block.get('energy_at_start', 0)*100:.0f}%"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{today}T{start_hhmm}00",
            f"DTEND:{today}T{end_hhmm}00",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "STATUS:CONFIRMED",
        ])

        if block.get("is_break", False):
            lines.append("CATEGORIES:Break")
        else:
            load = block.get("cognitive_load", 0)
            cat = "Deep Work" if load >= 7 else "Light Work"
            lines.append(f"CATEGORIES:{cat}")

        # Add alarm/reminder 5 min before
        lines.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT5M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Starting: {summary}",
            "END:VALARM",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    ics_content = "\r\n".join(lines)
    return PlainTextResponse(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="cogschedule-{today}.ics"'},
    )
