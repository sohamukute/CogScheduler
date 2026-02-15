import { useState } from "react";
import { Send, Loader2, Clock, Brain, BedDouble, Gauge } from "lucide-react";

const CHRONOTYPES = ["early", "normal", "late"];

export default function ChatForm({ onSubmit, loading }) {
  const [message, setMessage] = useState("");
  const [sleepHours, setSleepHours] = useState(7);
  const [stressLevel, setStressLevel] = useState(2);
  const [chronotype, setChronotype] = useState("normal");
  const [lecturesToday, setLecturesToday] = useState(0);
  const [availableFrom, setAvailableFrom] = useState("09:00");
  const [availableTo, setAvailableTo] = useState("22:00");
  const [breaksAt, setBreaksAt] = useState("13:00-14:00");
  const [showAdvanced, setShowAdvanced] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!message.trim() || loading) return;
    onSubmit({
      message: message.trim(),
      sleep_hours: sleepHours,
      stress_level: stressLevel,
      chronotype,
      lectures_today: lecturesToday,
      available_from: availableFrom,
      available_to: availableTo,
      breaks_at: breaksAt
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* ── Message ─────────────────────────────── */}
      <div>
        <label className="block text-sm font-medium mb-1.5 text-foreground">
          Describe your tasks
        </label>
        <textarea
          rows={4}
          placeholder="e.g. I need to study graph theory for 2 hours, finish my ML assignment (90 min), and review organic chemistry notes (45 min)..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-sm
                     placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring
                     resize-none transition"
        />
      </div>

      {/* ── Core fields row ─────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Sleep */}
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1">
            <BedDouble size={14} /> Sleep (hrs)
          </label>
          <input
            type="number"
            min={0}
            max={24}
            step={0.5}
            value={sleepHours}
            onChange={(e) => setSleepHours(parseFloat(e.target.value))}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-ring transition"
          />
        </div>

        {/* Stress */}
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1">
            <Gauge size={14} /> Stress (1-5)
          </label>
          <input
            type="range"
            min={1}
            max={5}
            value={stressLevel}
            onChange={(e) => setStressLevel(parseInt(e.target.value))}
            className="w-full accent-primary mt-1"
          />
          <div className="text-center text-xs font-mono text-muted-foreground">
            {stressLevel}
          </div>
        </div>

        {/* Chronotype */}
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1">
            <Brain size={14} /> Chronotype
          </label>
          <select
            value={chronotype}
            onChange={(e) => setChronotype(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-ring transition"
          >
            {CHRONOTYPES.map((c) => (
              <option key={c} value={c}>
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Lectures */}
        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-1">
            <Clock size={14} /> Lectures
          </label>
          <input
            type="number"
            min={0}
            value={lecturesToday}
            onChange={(e) => setLecturesToday(parseInt(e.target.value))}
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-ring transition"
          />
        </div>
      </div>

      {/* ── Advanced toggle ─────────────────────── */}
      <button
        type="button"
        onClick={() => setShowAdvanced((v) => !v)}
        className="text-xs text-primary hover:underline cursor-pointer"
      >
        {showAdvanced ? "Hide" : "Show"} advanced options
      </button>

      {showAdvanced && (
        <div className="grid grid-cols-3 gap-3 p-3 rounded-lg bg-muted/50">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">
              From
            </label>
            <input
              type="time"
              value={availableFrom}
              onChange={(e) => setAvailableFrom(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-ring transition"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">
              To
            </label>
            <input
              type="time"
              value={availableTo}
              onChange={(e) => setAvailableTo(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-ring transition"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">
              Breaks (comma-sep)
            </label>
            <input
              type="text"
              placeholder="13:00-14:00"
              value={breaksAt}
              onChange={(e) => setBreaksAt(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-ring transition"
            />
          </div>
        </div>
      )}

      {/* ── Submit ──────────────────────────────── */}
      <button
        type="submit"
        disabled={loading || !message.trim()}
        className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5
                   text-primary-foreground font-medium text-sm shadow-sm
                   hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                   transition cursor-pointer"
      >
        {loading ? (
          <>
            <Loader2 size={16} className="animate-spin" /> Generating schedule…
          </>
        ) : (
          <>
            <Send size={16} /> Generate Schedule
          </>
        )}
      </button>
    </form>
  );
}
