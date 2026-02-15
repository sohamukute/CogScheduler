import { useState } from "react";
import { postTLXFeedback } from "../api/schedule";
import { Send, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

export default function TLXFeedback({ blocks }) {
  const taskBlocks = blocks?.filter((b) => !b.is_break) ?? [];
  const [blockIndex, setBlockIndex] = useState(0);
  const [mentalDemand, setMentalDemand] = useState(4);
  const [effort, setEffort] = useState(4);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  if (!taskBlocks.length) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setSending(true);
    try {
      const res = await postTLXFeedback({
        block_index: blockIndex,
        mental_demand: mentalDemand,
        effort,
      });
      setResult(res);
      toast.success("TLX feedback recorded");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to submit TLX feedback");
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Block selector */}
      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1 block">
          Task block
        </label>
        <select
          value={blockIndex}
          onChange={(e) => setBlockIndex(parseInt(e.target.value))}
          className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm
                     focus:outline-none focus:ring-2 focus:ring-ring transition"
        >
          {taskBlocks.map((b, i) => (
            <option key={i} value={i}>
              {b.start_time}–{b.end_time}: {b.task_title}
            </option>
          ))}
        </select>
      </div>

      {/* Sliders */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">
            Mental Demand (1-7)
          </label>
          <input
            type="range"
            min={1}
            max={7}
            value={mentalDemand}
            onChange={(e) => setMentalDemand(parseInt(e.target.value))}
            className="w-full accent-primary"
          />
          <div className="text-center text-xs font-mono text-muted-foreground">
            {mentalDemand}
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">
            Effort (1-7)
          </label>
          <input
            type="range"
            min={1}
            max={7}
            value={effort}
            onChange={(e) => setEffort(parseInt(e.target.value))}
            className="w-full accent-primary"
          />
          <div className="text-center text-xs font-mono text-muted-foreground">
            {effort}
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={sending}
        className="w-full flex items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-2
                   text-secondary-foreground font-medium text-sm
                   hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                   transition cursor-pointer"
      >
        {sending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Send size={14} />
        )}
        Submit Feedback
      </button>

      {result && (
        <div className="rounded-lg bg-muted/50 p-3 text-xs space-y-1 text-muted-foreground">
          <p>TLX entries: {result.tlx_entries}</p>
          <p>
            Updated weights — consec: {result.updated_weights.fatigue_consec_weight.toFixed(3)},
            total: {result.updated_weights.fatigue_total_weight.toFixed(3)},
            force-break: {result.updated_weights.fatigue_force_break.toFixed(3)}
          </p>
        </div>
      )}
    </form>
  );
}
