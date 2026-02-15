import { Trophy, Flame, Star, Award } from "lucide-react";

const LEVEL_COLORS = {
  Student: "from-secondary to-muted",
  Scholar: "from-chart-5 to-secondary",
  Genius: "from-chart-1 to-chart-5",
  Mastermind: "from-primary to-chart-1",
};

export default function GamificationCard({ gamification }) {
  if (!gamification) return null;
  const { xp, level, streak, badges } = gamification;

  return (
    <div className="space-y-4">
      {/* ── Level + XP ─────────────────── */}
      <div className="flex items-center gap-4">
        <div
          className={`w-14 h-14 rounded-xl bg-gradient-to-br ${
            LEVEL_COLORS[level] || LEVEL_COLORS.Student
          } flex items-center justify-center shadow-md`}
        >
          <Trophy size={24} className="text-primary-foreground" />
        </div>
        <div>
          <p className="text-lg font-bold">{level}</p>
          <p className="text-sm text-muted-foreground">{xp} XP earned</p>
        </div>
      </div>

      {/* ── XP bar to next level ───────── */}
      {(() => {
        const thresholds = [0, 200, 600, 1200];
        const levels = ["Student", "Scholar", "Genius", "Mastermind"];
        const idx = levels.indexOf(level);
        const next = thresholds[idx + 1] ?? thresholds[thresholds.length - 1];
        const prev = thresholds[idx] ?? 0;
        const pct = idx >= levels.length - 1 ? 100 : Math.min(100, Math.round(((xp - prev) / (next - prev)) * 100));
        return (
          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>{pct}%</span>
              <span>
                {idx < levels.length - 1 ? `${next - xp} XP to ${levels[idx + 1]}` : "Max level"}
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })()}

      {/* ── Streak ─────────────────────── */}
      {streak > 0 && (
        <div className="flex items-center gap-2 text-sm">
          <Flame size={18} className="text-chart-1" />
          <span className="font-semibold">{streak}</span>
          <span className="text-muted-foreground">deep-work streak</span>
        </div>
      )}

      {/* ── Badges ─────────────────────── */}
      {badges?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {badges.map((badge) => (
            <span
              key={badge}
              className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1
                         text-xs font-medium text-accent-foreground"
            >
              <Award size={12} />
              {badge}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
