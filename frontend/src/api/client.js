import axios from "axios";

// In production (Vercel), VITE_API_URL points to the Railway backend.
// In dev, the Vite proxy rewrites /api → localhost:8000.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  headers: { "Content-Type": "application/json" },
  timeout: 120_000, // LLM calls can be slow
});

export default api;
