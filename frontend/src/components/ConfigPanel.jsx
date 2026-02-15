import { useState, useEffect } from "react";
import { getConfig, putConfig } from "../api/schedule";
import { Settings, Save, RefreshCw, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

const FIELD_META = {
  sleep_baseline:           { label: "Sleep baseline (hrs)",     type: "number", step: 0.5, min: 0, max: 24 },
  fatigue_consec_weight:    { label: "Fatigue consec weight",    type: "number", step: 0.05, min: 0, max: 1 },
  fatigue_total_weight:     { label: "Fatigue total weight",     type: "number", step: 0.025, min: 0, max: 1 },
  consec_threshold_min:     { label: "Consec threshold (min)",   type: "number", step: 5, min: 15 },
  total_deep_threshold_min: { label: "Total deep threshold",     type: "number", step: 15, min: 30 },
  short_break_trigger_min:  { label: "Short break trigger (min)",type: "number", step: 5, min: 15 },
  short_break_duration:     { label: "Short break (min)",        type: "number", step: 5, min: 5 },
  long_break_duration:      { label: "Long break (min)",         type: "number", step: 5, min: 5 },
  fatigue_force_break:      { label: "Force break fatigue",      type: "number", step: 0.05, min: 0.3, max: 1 },
  stress_cap_threshold:     { label: "Stress cap threshold",     type: "number", step: 1, min: 1, max: 5 },
  max_load_under_stress:    { label: "Max load under stress",    type: "number", step: 0.5, min: 1, max: 10 },
  lecture_penalty_per:      { label: "Lecture penalty",           type: "number", step: 0.01, min: 0 },
  break_recovery_factor:    { label: "Break recovery factor",    type: "number", step: 0.05, min: 0, max: 1 },
  quantum_min:              { label: "Quantum (min)",            type: "number", step: 5, min: 5 },
  deep_work_load_threshold: { label: "Deep work threshold",      type: "number", step: 0.5, min: 1, max: 10 },
};

export default function ConfigPanel() {
  const [config, setConfig] = useState(null);
  const [dirty, setDirty] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await getConfig();
      setConfig(data);
      setDirty({});
    } catch {
      toast.error("Failed to load config");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function handleChange(key, value) {
    setDirty((d) => ({ ...d, [key]: value }));
  }

  async function handleSave() {
    if (!Object.keys(dirty).length) return;
    setSaving(true);
    try {
      const updated = await putConfig(dirty);
      setConfig(updated);
      setDirty({});
      toast.success("Config updated");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update config");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  if (!config) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Settings size={16} /> Configuration
        </h3>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="p-1.5 rounded-md hover:bg-muted transition cursor-pointer"
            title="Reload"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !Object.keys(dirty).length}
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-1
                       text-primary-foreground text-xs font-medium
                       hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                       transition cursor-pointer"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {Object.entries(FIELD_META).map(([key, meta]) => {
          const val = key in dirty ? dirty[key] : config[key];
          if (val === undefined) return null;
          return (
            <div key={key}>
              <label className="text-xs text-muted-foreground mb-1 block">
                {meta.label}
              </label>
              <input
                type="number"
                step={meta.step}
                min={meta.min}
                max={meta.max}
                value={val}
                onChange={(e) => handleChange(key, parseFloat(e.target.value))}
                className={`w-full rounded-md border px-3 py-1.5 text-sm
                  focus:outline-none focus:ring-2 focus:ring-ring transition
                  ${key in dirty ? "border-primary bg-primary/5" : "border-input bg-background"}`}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
