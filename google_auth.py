"""
Google OAuth2 + Calendar + Gmail integration.

Flow:
  1. Frontend redirects to /auth/google → Google consent screen
  2. Google redirects back to /auth/google/callback with auth code
  3. Backend exchanges code for tokens, stores in session
  4. Tokens used for Calendar push + optional Gmail reading

Env vars needed:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI   (e.g. http://localhost:8000/auth/google/callback)
  FRONTEND_URL          (e.g. http://localhost:5173)
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

load_dotenv()

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# In-memory token store  {session_id: {credentials, user_info}}
# In production → Redis or DB
_sessions: dict[str, dict] = {}


def is_configured() -> bool:
    """Check if Google OAuth is configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def _get_client_config():
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_auth_url(session_id: str) -> str:
    """Generate Google OAuth2 consent URL."""
    flow = Flow.from_client_config(_get_client_config(), scopes=SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=session_id,
    )
    return auth_url


def exchange_code(code: str, session_id: str) -> dict:
    """Exchange auth code for tokens. Returns user info dict."""
    flow = Flow.from_client_config(_get_client_config(), scopes=SCOPES)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    flow.fetch_token(code=code)

    creds = flow.credentials

    # Get user info
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()

    # Store session
    _sessions[session_id] = {
        "credentials": _creds_to_dict(creds),
        "user_info": user_info,
    }

    return {
        "google_id": user_info.get("id", ""),
        "email": user_info.get("email", ""),
        "name": user_info.get("name", ""),
        "avatar_url": user_info.get("picture", ""),
    }


def get_session(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def get_credentials(session_id: str) -> Credentials | None:
    """Get valid Google credentials for a session."""
    session = _sessions.get(session_id)
    if not session:
        return None
    creds_dict = session.get("credentials")
    if not creds_dict:
        return None
    return Credentials(**creds_dict)


def _creds_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }


# ──────────────────────────────────────────────────────────────
# Google Calendar — push schedule events
# ──────────────────────────────────────────────────────────────

def push_schedule_to_calendar(
    session_id: str,
    schedule_blocks: list[dict],
    date_str: str | None = None,
) -> dict:
    """
    Push schedule blocks as Google Calendar events.
    Returns {created: int, errors: int, calendar_id: str}
    """
    creds = get_credentials(session_id)
    if not creds:
        return {"error": "Not authenticated with Google"}

    service = build("calendar", "v3", credentials=creds)
    date = date_str or datetime.now().strftime("%Y-%m-%d")

    created = 0
    errors = 0

    for block in schedule_blocks:
        try:
            start_time = f"{date}T{block['start_time']}:00"
            end_time = f"{date}T{block['end_time']}:00"

            is_break = block.get("is_break", False)
            load = block.get("cognitive_load", 0)

            # Color: green for breaks, red for heavy, blue for light
            color_id = "2" if is_break else ("11" if load >= 7 else "9")

            description = ""
            if not is_break:
                description = (
                    f"Cognitive Load: {load:.1f}/10\n"
                    f"Energy: {block.get('energy_at_start', 0) * 100:.0f}%\n"
                )
                if block.get("explanation"):
                    description += f"\n{block['explanation']}"
            description += "\n\n📅 Scheduled by CogScheduler"

            event = {
                "summary": f"{'☕ ' if is_break else '📚 '}{block['task_title']}",
                "description": description,
                "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
                "colorId": color_id,
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 5}],
                },
            }

            service.events().insert(calendarId="primary", body=event).execute()
            created += 1

        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
            errors += 1

    return {"created": created, "errors": errors, "calendar_id": "primary"}


# ──────────────────────────────────────────────────────────────
# Google Calendar — read existing events (for clash detection)
# ──────────────────────────────────────────────────────────────

def get_today_events(session_id: str, date_str: str | None = None) -> list[dict]:
    """Fetch today's events from Google Calendar."""
    creds = get_credentials(session_id)
    if not creds:
        return []

    try:
        service = build("calendar", "v3", credentials=creds)
        date = date_str or datetime.now().strftime("%Y-%m-%d")
        time_min = f"{date}T00:00:00Z"
        time_max = f"{date}T23:59:59Z"

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for ev in result.get("items", []):
            start = ev.get("start", {}).get("dateTime", "")
            end = ev.get("end", {}).get("dateTime", "")
            events.append({
                "summary": ev.get("summary", ""),
                "start": start,
                "end": end,
                "source": "google_calendar",
            })
        return events
    except Exception as e:
        logger.error(f"get_today_events failed: {e}")
        return []
