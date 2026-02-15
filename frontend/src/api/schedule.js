import api from "./client";

/* ── POST /chat ────────────────────────────────────────────── */
export async function postChat(payload) {
  const { data } = await api.post("/chat", payload);
  return data;
}

/* ── POST /converse ────────────────────────────────────────── */
export async function postConverse(payload) {
  const { data } = await api.post("/converse", payload);
  return data;
}

/* ── POST /schedule ────────────────────────────────────────── */
export async function postSchedule(payload) {
  const { data } = await api.post("/schedule", payload);
  return data;
}

/* ── POST /tlx-feedback ────────────────────────────────────── */
export async function postTLXFeedback(payload) {
  const { data } = await api.post("/tlx-feedback", payload);
  return data;
}

/* ── GET /config ───────────────────────────────────────────── */
export async function getConfig() {
  const { data } = await api.get("/config");
  return data;
}

/* ── PUT /config ───────────────────────────────────────────── */
export async function putConfig(updates) {
  const { data } = await api.put("/config", updates);
  return data;
}

/* ── GET /health ───────────────────────────────────────────── */
export async function getHealth() {
  const { data } = await api.get("/health");
  return data;
}

/* ── Profile ───────────────────────────────────────────────── */
export async function getProfile() {
  const { data } = await api.get("/profile");
  return data;
}

export async function putProfile(profile) {
  const { data } = await api.put("/profile", profile);
  return data;
}

/* ── Calendar export (ICS download) ────────────────────────── */
export function getCalendarExportUrl() {
  return `${api.defaults.baseURL}/calendar/export`;
}

/* ── Auth ──────────────────────────────────────────────────── */
export async function getGoogleAuthUrl() {
  const { data } = await api.get("/auth/google");
  return data; // { auth_url, session_id }
}

export async function getAuthMe() {
  const { data } = await api.get("/auth/me");
  return data; // { authenticated, google_id, email, name, avatar_url, session_id }
}

export async function postAuthLogout() {
  const { data } = await api.post("/auth/logout");
  return data;
}

/* ── Timetable ─────────────────────────────────────────────── */
export async function uploadTimetable(file) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/timetable/extract", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 180000, // 3 min — Gemini vision can be slow
  });
  return data;
}

export async function personalizeTimetable(answers) {
  const { data } = await api.post("/timetable/personalize", answers);
  return data;
}

export async function getTimetable() {
  const { data } = await api.get("/timetable");
  return data;
}

/* ── Google Calendar sync ──────────────────────────────────── */
export async function syncToGoogleCalendar() {
  const { data } = await api.post("/calendar/sync");
  return data; // { status, events_created, errors }
}

export async function getCalendarEvents() {
  const { data } = await api.get("/calendar/events");
  return data; // { events, count }
}
