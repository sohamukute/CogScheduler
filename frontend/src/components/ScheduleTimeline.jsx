import { Coffee, BookOpen, AlertTriangle } from "lucide-react";

function loadColor(load) {
  if (load >= 8) return "text-destructive";
  if (load >= 6) return "text-chart-1";
  if (load >= 4) return "text-chart-5";
  return "text-chart-2";
}

function energyBar(val) {
  const pct = Math.round(val * 100);
  const color =
    pct >= 60 ? "bg-green-500 dark:bg-green-400" :
    pct >= 35 ? "bg-yellow-500 dark:bg-yellow-400" :
               "bg-red-500 dark:bg-red-400";
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-muted-foreground w-8 text-right">{pct}%</span>
    </div>
  );
}

export default function ScheduleTimeline({ blocks, warnings }) {
  if (!blocks?.length) return null;

  return (
    <div className="space-y-3">
      {/* ── Warnings ───────────────────── */}
      {warnings?.length > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {warnings.map((w, i) => (
            <p key={i} className="text-xs text-destructive flex items-start gap-1.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              {w}
            </p>
          ))}
        </div>
      )}

      {/* ── Blocks ─────────────────────── */}
      <div className="relative space-y-1.5">
        {/* vertical timeline line */}
        <div className="absolute left-[54px] top-2 bottom-2 w-px bg-border" />

        {blocks.map((block, i) => (
          <div
            key={i}
            className={`relative flex items-stretch gap-3 rounded-lg p-3 transition
              ${block.is_break
                ? "bg-accent/40 border border-accent/60"
                : "bg-card border border-border hover:shadow-md"
              }`}
          >
            {/* time column */}
            <div className="w-[80px] shrink-0 flex flex-col items-center justify-center text-center">
              <span className="text-xs font-mono font-semibold text-foreground">
                {block.start_time}
              </span>
              <span className="text-[10px] text-muted-foreground">–</span>
              <span className="text-xs font-mono text-muted-foreground">
                {block.end_time}
              </span>
            </div>

            {/* dot on timeline */}
            <div className="absolute left-[52px] top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-primary ring-2 ring-background z-10" />

            {/* content */}
            <div className="flex-1 min-w-0 pl-3">
              <div className="flex items-center gap-2 mb-1">
                {block.is_break ? (
                  <Coffee size={14} className="text-accent-foreground" />
                ) : (
                  <BookOpen size={14} className="text-primary" />
                )}
                <h4 className="text-sm font-semibold truncate">
                  {block.task_title}
                </h4>
              </div>

              {!block.is_break && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span className={`font-medium ${loadColor(block.cognitive_load)}`}>
                    Load {block.cognitive_load.toFixed(1)}
                  </span>
                  <span className="flex items-center gap-1">
                    Energy {energyBar(block.energy_at_start)}
                  </span>
                  <span className="flex items-center gap-1">
                    Fatigue {energyBar(block.fatigue_at_start)}
                  </span>
                </div>
              )}

              {block.explanation && (
                <p className="text-xs text-muted-foreground mt-1 italic">
                  {block.explanation}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
