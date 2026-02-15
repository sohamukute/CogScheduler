"""
Timetable extraction using Gemini multimodal.

Accepts PDF or image of a college/school timetable,
uses Gemini vision to intelligently extract and analyze it.
"""

from __future__ import annotations

import os
import io
import base64
import json
import logging
from typing import Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# System prompt — the full intelligent extraction logic
# ──────────────────────────────────────────────────────────────

TIMETABLE_SYSTEM_PROMPT = """\
You are an intelligent academic timetable analysis and personalization assistant.

Your goal is to work with ANY student timetable (PDF or image) from ANY institution.

--------------------------------------------------
STEP 1 — Intelligent Extraction
--------------------------------------------------

From the uploaded timetable, extract:

• Days (Mon–Sun if present)
• Time slots (exact time ranges)
• Subject names
• Lab names
• Faculty names/initials (if present)
• Batch/group labels (G1, Batch A, Section B, etc.)
• Elective options (if multiple subjects appear in same slot)
• Project tracks (if applicable)
• Color coding or structural patterns
• Notes/legends (if present)

--------------------------------------------------
STEP 2 — Detect Academic Patterns
--------------------------------------------------

Infer categories based on patterns:

A) If multiple subjects appear in the same time slot → Likely elective options.
B) If subjects are labeled with groups (G1/G2/Batch A) → Likely group-based sessions.
C) If subject repeats across all groups → Likely mandatory/core subject.
D) If subject contains keywords like Lab, Practical, Workshop, Studio → Classify as practical/lab.
E) If subject contains Project, MDM, Capstone, Mini Project → Classify as project-type.
F) If subject labeled OE, PE, Elective, Open Elective → Classify as selectable elective.

--------------------------------------------------
STEP 3 — Questions to Ask User
--------------------------------------------------

Identify what questions the user needs to answer to personalize:

1) If group-based sessions detected: "Which group/batch are you in?"
2) If elective slot detected: "Select your subject for this elective slot:"
3) If project tracks detected: "Select your project/track:"
If NO selectable patterns are detected, return an empty questions array.

--------------------------------------------------
OUTPUT FORMAT — Respond ONLY with valid JSON:
--------------------------------------------------

{
  "institution_name": "Detected institution name or 'Unknown'",
  "days": ["Monday", "Tuesday", ...],
  "time_slots": ["09:00-10:00", "10:00-11:00", ...],
  "subjects": [
    {
      "name": "Subject Name",
      "code": "CS101 or null",
      "type": "core | elective | lab | project",
      "faculty": "Faculty name or null",
      "groups": ["G1", "G2"] or null
    }
  ],
  "schedule": [
    {
      "day": "Monday",
      "time": "09:00-10:00",
      "subject": "Subject Name",
      "type": "core | elective | lab | project | break",
      "group": "G1 or null (null means all groups)",
      "faculty": "Faculty or null",
      "room": "Room or null"
    }
  ],
  "detected_groups": ["G1", "G2", "Batch A", ...] or [],
  "detected_electives": [
    {
      "slot_day": "Monday",
      "slot_time": "14:00-15:00",
      "options": ["Subject A", "Subject B", "Subject C"]
    }
  ],
  "questions_for_user": [
    {
      "id": "group",
      "question": "Which group/batch are you in?",
      "options": ["G1", "G2", "Batch A"]
    },
    {
      "id": "elective_mon_14",
      "question": "Select your elective for Monday 14:00-15:00:",
      "options": ["Subject A", "Subject B"]
    }
  ],
  "weekly_summary": {
    "Monday": {"classes": 5, "hours": 5.0, "labs": 1},
    "Tuesday": {"classes": 4, "hours": 4.5, "labs": 0}
  },
  "notes": "Any additional observations about the timetable"
}

IMPORTANT:
- Respond ONLY with the JSON object, no markdown fences, no extra text.
- If the image/PDF is unclear, extract what you can and note issues in "notes".
- Be robust — handle messy layouts, merged cells, color-coded entries.
"""


# ──────────────────────────────────────────────────────────────
# Main extraction function
# ──────────────────────────────────────────────────────────────

async def extract_timetable(file_bytes: bytes, file_type: str) -> dict:
    """
    Extract timetable from PDF or image bytes using Gemini vision.

    Args:
        file_bytes: Raw file content
        file_type: MIME type (image/png, image/jpeg, application/pdf)

    Returns:
        Parsed timetable dict with schedule, groups, electives, questions
    """
    # For PDFs, convert pages to images first
    if file_type == "application/pdf":
        images = _pdf_to_images(file_bytes)
        if not images:
            raise ValueError("Could not extract images from PDF. Try uploading a screenshot instead.")
    else:
        # Single image
        images = [(file_bytes, file_type)]

    # Build multimodal message with all pages
    content_parts = []
    for i, (img_bytes, mime) in enumerate(images):
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
        if len(images) > 1:
            content_parts.append({
                "type": "text",
                "text": f"(Page {i + 1} of {len(images)})",
            })

    # Gemma 3 is multimodal and doesn't support SystemMessage,
    # so we merge the system prompt into the user content.
    content_parts.append({
        "type": "text",
        "text": TIMETABLE_SYSTEM_PROMPT
            + "\n\nAnalyze this timetable and extract all information as specified. Return ONLY valid JSON.",
    })

    # Try models in order: gemma (higher limits) → flash-lite → flash
    _TIMETABLE_MODELS = ["gemma-3-27b-it", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    last_err = None
    response = None

    for model_name in _TIMETABLE_MODELS:
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.1,
                max_retries=1,
            )
            response = await llm.ainvoke([
                HumanMessage(content=content_parts),
            ])
            logger.info(f"Timetable extracted using model: {model_name}")
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning(f"{model_name} rate-limited for timetable, trying next...")
                last_err = e
                continue
            raise

    if response is None:
        raise last_err or RuntimeError("All models exhausted for timetable extraction")

    # Parse JSON from response
    text = response.content.strip()
    # Strip markdown fences if present
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
        else:
            raise ValueError(f"Gemini response was not valid JSON: {text[:300]}")

    return result


def _pdf_to_images(pdf_bytes: bytes) -> list[tuple[bytes, str]]:
    """Convert PDF pages to PNG images. Returns list of (bytes, mime)."""
    try:
        from PyPDF2 import PdfReader
        from PIL import Image

        # PyPDF2 can extract images but not render pages well
        # Use a simpler approach: extract embedded images if any
        reader = PdfReader(io.BytesIO(pdf_bytes))
        images = []

        for page in reader.pages[:5]:  # Max 5 pages
            if hasattr(page, "images"):
                for img in page.images:
                    images.append((img.data, "image/png"))

        # If no embedded images, send PDF as-is to Gemini (it handles PDFs)
        if not images:
            # Gemini 2.0 supports PDF input directly
            return [(pdf_bytes, "application/pdf")]

        return images

    except Exception as e:
        logger.error(f"PDF processing error: {e}")
        # Fallback: send raw PDF bytes — Gemini can handle it
        return [(pdf_bytes, "application/pdf")]


# ──────────────────────────────────────────────────────────────
# Personalize timetable based on user answers
# ──────────────────────────────────────────────────────────────

def personalize_timetable(timetable_data: dict, user_answers: dict) -> dict:
    """
    Filter timetable based on user's group/elective selections.

    Args:
        timetable_data: Full extracted timetable dict
        user_answers: {"group": "G1", "elective_mon_14": "Subject A", ...}

    Returns:
        Filtered timetable with only the user's classes
    """
    selected_group = user_answers.get("group")
    schedule = timetable_data.get("schedule", [])

    filtered = []
    for entry in schedule:
        entry_group = entry.get("group")

        # Include if:
        # 1. No group specified (common class)
        # 2. Matches selected group
        # 3. User didn't select a group (include all)
        if entry_group is None or not selected_group or entry_group == selected_group:
            # Check elective selection
            entry_type = entry.get("type", "")
            if entry_type == "elective":
                # Find the matching elective question
                slot_key = f"elective_{entry['day'][:3].lower()}_{entry['time'].split('-')[0].replace(':', '')}"
                selected_subject = user_answers.get(slot_key)
                if selected_subject and entry["subject"] != selected_subject:
                    continue  # Skip non-selected elective

            filtered.append(entry)

    personalized = {**timetable_data, "schedule": filtered}

    # Generate free time slots
    personalized["free_slots"] = _compute_free_slots(filtered, timetable_data.get("days", []))

    # Generate daily summary
    personalized["daily_summary"] = _compute_daily_summary(filtered)

    return personalized


def _compute_free_slots(schedule: list[dict], days: list[str]) -> dict[str, list[str]]:
    """Find free time slots for each day."""
    free = {}
    for day in days:
        day_entries = [e for e in schedule if e["day"] == day and e["type"] != "break"]
        if not day_entries:
            free[day] = ["All day free"]
            continue

        # Sort by time
        day_entries.sort(key=lambda e: e["time"])
        busy_ranges = []
        for e in day_entries:
            parts = e["time"].split("-")
            if len(parts) == 2:
                busy_ranges.append((parts[0].strip(), parts[1].strip()))

        # Find gaps
        free_ranges = []
        prev_end = "08:00"
        for start, end in sorted(busy_ranges):
            if start > prev_end:
                free_ranges.append(f"{prev_end}-{start}")
            prev_end = max(prev_end, end)
        if prev_end < "20:00":
            free_ranges.append(f"{prev_end}-20:00")

        free[day] = free_ranges if free_ranges else ["Fully booked"]

    return free


def _compute_daily_summary(schedule: list[dict]) -> dict:
    """Compute hours per day."""
    summary = {}
    for entry in schedule:
        day = entry["day"]
        if day not in summary:
            summary[day] = {"classes": 0, "hours": 0.0, "labs": 0}

        parts = entry["time"].split("-")
        if len(parts) == 2:
            try:
                sh, sm = map(int, parts[0].strip().split(":"))
                eh, em = map(int, parts[1].strip().split(":"))
                hrs = (eh * 60 + em - sh * 60 - sm) / 60
                summary[day]["hours"] += hrs
            except ValueError:
                summary[day]["hours"] += 1.0

        summary[day]["classes"] += 1
        if entry.get("type") in ("lab", "practical"):
            summary[day]["labs"] += 1

    return summary


# ──────────────────────────────────────────────────────────────
# Convert timetable to daily commitments for the scheduler
# ──────────────────────────────────────────────────────────────

def timetable_to_commitments(timetable_data: dict, day: str | None = None) -> list[str]:
    """
    Convert personalized timetable entries for a specific day
    into the daily_commitments format expected by the scheduler.

    Returns: ["09:00-10:00 Math Lecture", "14:00-16:00 CS Lab", ...]
    """
    import datetime as dt

    if day is None:
        day = dt.datetime.now().strftime("%A")

    schedule = timetable_data.get("schedule", [])
    commitments = []

    for entry in schedule:
        if entry["day"] == day and entry.get("type") != "break":
            time_range = entry["time"]
            subject = entry["subject"]
            entry_type = entry.get("type", "core")
            label = f"{time_range} {subject}"
            if entry_type == "lab":
                label += " (Lab)"
            commitments.append(label)

    return commitments
