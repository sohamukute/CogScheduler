"""
Supabase client for user data persistence.

Tables expected in Supabase:
  - users: id (uuid, PK), email, name, google_id, avatar_url, created_at
  - profiles: user_id (FK→users.id), role, chronotype, wake_time, sleep_time,
              sleep_hours, stress_level, daily_commitments (jsonb),
              break_preferences (jsonb), lectures_today, timetable_data (jsonb),
              updated_at
  - schedules: id (uuid), user_id (FK), schedule_data (jsonb),
               created_at, calendar_synced (bool)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # anon or service-role key

_client = None


def get_supabase():
    """Lazy-init Supabase client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured — running in local-only mode")
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialised")
        return _client
    except Exception as e:
        logger.error(f"Failed to init Supabase: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# User CRUD
# ──────────────────────────────────────────────────────────────

def upsert_user(google_id: str, email: str, name: str, avatar_url: str = "") -> dict | None:
    """Create or update user from Google login. Returns user row."""
    sb = get_supabase()
    if not sb:
        return None
    try:
        data = {
            "google_id": google_id,
            "email": email,
            "name": name,
            "avatar_url": avatar_url,
        }
        result = sb.table("users").upsert(data, on_conflict="google_id").execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"upsert_user failed: {e}")
        return None


def get_user_by_google_id(google_id: str) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        result = sb.table("users").select("*").eq("google_id", google_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"get_user_by_google_id failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Profile CRUD
# ──────────────────────────────────────────────────────────────

def upsert_profile(user_id: str, profile_data: dict) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        payload = {
            "user_id": user_id,
            **profile_data,
            "updated_at": datetime.utcnow().isoformat(),
        }
        result = sb.table("profiles").upsert(payload, on_conflict="user_id").execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"upsert_profile failed: {e}")
        return None


def get_profile(user_id: str) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        result = sb.table("profiles").select("*").eq("user_id", user_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"get_profile failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Schedule persistence
# ──────────────────────────────────────────────────────────────

def save_schedule(user_id: str, schedule_data: dict) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        payload = {
            "user_id": user_id,
            "schedule_data": schedule_data,
            "created_at": datetime.utcnow().isoformat(),
            "calendar_synced": False,
        }
        result = sb.table("schedules").insert(payload).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"save_schedule failed: {e}")
        return None


def get_latest_schedule(user_id: str) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        result = (
            sb.table("schedules")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"get_latest_schedule failed: {e}")
        return None


def mark_calendar_synced(schedule_id: str) -> None:
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table("schedules").update({"calendar_synced": True}).eq("id", schedule_id).execute()
    except Exception as e:
        logger.error(f"mark_calendar_synced failed: {e}")
