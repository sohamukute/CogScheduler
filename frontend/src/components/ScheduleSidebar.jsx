import { useState } from "react";
import {
  Coffee,
  BookOpen,
  Calendar,
  Download,
  Activity,
  Trophy,
  Flame,
  Award,
  ChevronDown,
  ChevronUp,
  BarChart3,
  ClipboardCheck,
  Loader2,
  CheckCircle2,
  CloudUpload,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getCalendarExportUrl, syncToGoogleCalendar } from "../api/schedule";
import TLXFeedback from "./TLXFeedback";
import toast from "react-hot-toast";

/* ─── helpers ─────────────────────────────────────────────── */
function loadColor(load) {
  if (load >= 8) return "text-destructive";
  if (load >= 6) return "text-chart-1";
  if (load >= 4) return "text-chart-5";
  return "text-chart-2";
}

function energyDot(val) {
  const pct = Math.round(val * 100);
  const color =
    pct >= 60 ? "bg-green-500" : pct >= 35 ? "bg-yellow-500" : "bg-red-500";
  return (
    <span className="flex items-center gap-1">
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      <span className="font-mono">{pct}%</span>
    </span>
  );
}

const LEVEL_COLORS = {
  Student: "from-secondary to-muted",
  Scholar: "from-chart-5 to-secondary",
  Genius: "from-chart-1 to-chart-5",
  Mastermind: "from-primary to-chart-1",
};

/* ─── Google Calendar sync button ─────────────────────────── */
function CalendarSyncBtn({ isLoggedIn }) {
  const [syncing, setSyncing] = useState(false);
  const [synced, setSynced] = useState(false);

  async function handleSync() {
    if (!isLoggedIn) {
      toast.error("Sign in with Google first to sync calendar");
      return;
    }
    setSyncing(true);
    try {
      const res = await syncToGoogleCalendar();
      setSynced(true);
      toast.success(`${res.events_created} events added to Google Calendar!`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Calendar sync failed");
    } finally {
      setSyncing(false);
    }
  }

  if (synced) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-green-600 dark:text-green-400 font-medium">
        <CheckCircle2 size={10} /> Synced
      </span>
    );
  }

  return (
    <button
      onClick={handleSync}
      disabled={syncing}
      className="flex items-center gap-1 rounded-lg bg-primary/10 text-primary px-2.5 py-1
                 text-[10px] font-medium hover:bg-primary/20 transition cursor-pointer
                 disabled:opacity-50"
      title={isLoggedIn ? "Push to Google Calendar" : "Sign in first"}
    >
      {syncing ? <Loader2 size={10} className="animate-spin" /> : <CloudUpload size={10} />}
      {syncing ? "Syncing…" : "Sync Calendar"}
    </button>
  );
}

/* ─── collapsible section ─────────────────────────────────── */
function Section({ title, icon: Icon, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold
                   text-muted-foreground hover:text-foreground transition cursor-pointer"
      >
        <span className="flex items-center gap-1.5">
          {Icon && <Icon size={13} />} {title}
        </span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

/* ─── Daily motivation quotes ─────────────────────────────── */
const DAILY_QUOTES = [
  "Small steps every day lead to big results. 🌱",
  "You don't have to be perfect, just consistent. 💪",
  "Plan the work, work the plan. 📋",
  "A 25-minute focused session beats 2 hours of distraction. 🎯",
  "Your future self will thank you for starting today. ⭐",
  "Progress, not perfection. 🚀",
  "The best time to start was yesterday. The next best is now. ⏰",
  "One task at a time. You've got this. 💛",
];

function getDailyQuote() {
  const day = new Date().getDate();
  return DAILY_QUOTES[day % DAILY_QUOTES.length];
}

function getDateStr() {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

/* ─── main component ──────────────────────────────────────── */
export default function ScheduleSidebar({ result, profile, isLoggedIn }) {
  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
          <Calendar size={28} className="text-primary/60" />
        </div>
        <p className="text-[11px] text-muted-foreground/60 mb-3">{getDateStr()}</p>
        <h3 className="text-sm font-semibold text-foreground mb-2">
          What's on your plate today?
        </h3>
        <p className="text-xs text-muted-foreground/70 max-w-[220px] mb-5">
          Tell me your tasks in the chat and I'll build a schedule that works with your energy levels.
        </p>
        <div className="rounded-xl bg-muted/30 border border-border/50 px-4 py-3 max-w-[240px]">
          <p className="text-[10px] text-muted-foreground italic">
            "{getDailyQuote()}"
          </p>
        </div>
      </div>
    );
  }

  const { schedule: blocks, energy_curve, fatigue_curve, gamification, warnings } = result;
  const taskBlocks = blocks?.filter((b) => !b.is_break) ?? [];
  const breakBlocks = blocks?.filter((b) => b.is_break) ?? [];
  const totalMinutes = taskBlocks.reduce((acc, b) => {
    const [sh, sm] = b.start_time.split(":").map(Number);
    const [eh, em] = b.end_time.split(":").map(Number);
    return acc + (eh * 60 + em) - (sh * 60 + sm);
  }, 0);

  /* build mini curve data */
  const curveData = [];
  const eMap = new Map();
  energy_curve?.forEach(({ time, value }) => {
    if (!eMap.has(time)) eMap.set(time, { time });
    eMap.get(time).energy = +(value * 100).toFixed(0);
  });
  fatigue_curve?.forEach(({ time, value }) => {
    if (!eMap.has(time)) eMap.set(time, { time });
    eMap.get(time).fatigue = +(value * 100).toFixed(0);
  });
  const sortedCurve = [...eMap.values()].sort((a, b) => a.time.localeCompare(b.time));

  return (
    <div className="h-full flex flex-col overflow-y-auto">
      {/* ── Header stats ───────────────── */}
      <div className="px-4 pt-4 pb-3 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold flex items-center gap-1.5">
            <Calendar size={15} className="text-primary" /> Today's Schedule
          </h2>
          <div className="flex items-center gap-1.5">
            <CalendarSyncBtn isLoggedIn={isLoggedIn} />
            <a
              href={getCalendarExportUrl()}
              download
              className="flex items-center gap-1 rounded-lg bg-muted/60 text-muted-foreground px-2 py-1
                         text-[10px] font-medium hover:bg-muted transition"
              title="Download .ics file"
            >
              <Download size={10} /> .ics
            </a>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg bg-muted/50 p-2">
            <p className="text-lg font-bold text-foreground">{taskBlocks.length}</p>
            <p className="text-[10px] text-muted-foreground">Tasks</p>
          </div>
          <div className="rounded-lg bg-muted/50 p-2">
            <p className="text-lg font-bold text-foreground">{breakBlocks.length}</p>
            <p className="text-[10px] text-muted-foreground">Breaks</p>
          </div>
          <div className="rounded-lg bg-muted/50 p-2">
            <p className="text-lg font-bold text-foreground">{Math.round(totalMinutes / 60 * 10) / 10}h</p>
            <p className="text-[10px] text-muted-foreground">Study time</p>
          </div>
        </div>
      </div>

      {/* ── Tips (soft, not alarming) ──── */}
      {warnings?.length > 0 && (
        <div className="px-4 py-2 bg-muted/30 border-b border-border">
          <p className="text-[10px] font-medium text-muted-foreground mb-0.5">💡 Tips</p>
          {warnings.filter((_, i) => i < 3).map((w, i) => (
            <p key={i} className="text-[10px] text-muted-foreground/80 flex items-start gap-1">
              <span className="mt-0.5 shrink-0">·</span> {w.replace(/^⚠️\s*/, "").replace(/^🔄\s*/, "")}
            </p>
          ))}
          {warnings.length > 3 && (
            <p className="text-[10px] text-muted-foreground/50 mt-0.5">
              +{warnings.length - 3} more
            </p>
          )}
        </div>
      )}

      {/* ── Timeline ───────────────────── */}
      <Section title="Timeline" icon={Activity} defaultOpen={true}>
        <div className="space-y-1.5">
          {blocks?.map((block, i) => (
            <div
              key={i}
              className={`flex items-start gap-2.5 rounded-lg p-2 text-xs transition
                ${block.is_break
                  ? "bg-accent/30 border border-accent/40"
                  : "bg-card border border-border"
                }`}
            >
              <div className="w-[52px] shrink-0 text-center">
                <span className="font-mono font-semibold text-[11px]">
                  {block.start_time}
                </span>
                <br />
                <span className="font-mono text-muted-foreground text-[10px]">
                  {block.end_time}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1 mb-0.5">
                  {block.is_break ? (
                    <Coffee size={11} className="text-accent-foreground shrink-0" />
                  ) : (
                    <BookOpen size={11} className="text-primary shrink-0" />
                  )}
                  <span className="font-semibold truncate">{block.task_title}</span>
                </div>
                {!block.is_break && (
                  <div className="flex items-center gap-2 text-muted-foreground text-[10px]">
                    <span className={`font-medium ${loadColor(block.cognitive_load)}`}>
                      Load {block.cognitive_load.toFixed(1)}
                    </span>
                    <span className="flex items-center gap-0.5">
                      E {energyDot(block.energy_at_start)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Energy curve (mini) ─────────── */}
      {sortedCurve.length > 0 && (
        <Section title="Energy & Fatigue" icon={BarChart3} defaultOpen={false}>
          <div className="h-[120px] -mx-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sortedCurve} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 8, fill: "var(--muted-foreground)" }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 8, fill: "var(--muted-foreground)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    fontSize: 10,
                  }}
                  formatter={(v) => `${v}%`}
                />
                <Area type="monotone" dataKey="energy" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.15} strokeWidth={1.5} />
                <Area type="monotone" dataKey="fatigue" stroke="var(--chart-3)" fill="var(--chart-3)" fillOpacity={0.15} strokeWidth={1.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Section>
      )}

      {/* ── Gamification ───────────────── */}
      {gamification && (
        <Section title="Your Progress" icon={Trophy} defaultOpen={true}>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-xl bg-gradient-to-br ${
                  LEVEL_COLORS[gamification.level] || LEVEL_COLORS.Student
                } flex items-center justify-center shadow`}
              >
                <Trophy size={18} className="text-primary-foreground" />
              </div>
              <div>
                <p className="text-sm font-bold">{gamification.level}</p>
                <p className="text-[10px] text-muted-foreground">{gamification.xp} XP</p>
              </div>
            </div>
            {gamification.streak > 0 && (
              <p className="flex items-center gap-1 text-xs">
                <Flame size={13} className="text-chart-1" />
                <span className="font-semibold">{gamification.streak}</span> deep streak
              </p>
            )}
            {gamification.badges?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {gamification.badges.map((b) => (
                  <span
                    key={b}
                    className="inline-flex items-center gap-0.5 rounded-full bg-accent px-2 py-0.5
                               text-[10px] font-medium text-accent-foreground"
                  >
                    <Award size={9} /> {b}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {/* ── TLX Feedback ───────────────── */}
      {blocks?.length > 0 && (
        <Section title="How was it? (TLX Feedback)" icon={ClipboardCheck} defaultOpen={false}>
          <TLXFeedback blocks={blocks} />
        </Section>
      )}
    </div>
  );
}
