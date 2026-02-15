import { useState, useRef } from "react";
import {
  User,
  Sun,
  Moon,
  Sunrise,
  Clock,
  BookOpen,
  Coffee,
  ArrowRight,
  Sparkles,
  Upload,
  FileText,
  Briefcase,
  Loader2,
  CheckCircle2,
  AlertCircle,
  X,
} from "lucide-react";
import { uploadTimetable, personalizeTimetable } from "../api/schedule";
import toast from "react-hot-toast";

/* ─── Dynamic steps based on role ───────────────────────────── */
function getSteps(role) {
  if (role === "student") {
    return [
      { key: "welcome", title: "Welcome" },
      { key: "role", title: "About you" },
      { key: "timetable", title: "Timetable" },
      { key: "rhythm", title: "Your rhythm" },
      { key: "commitments", title: "Commitments" },
    ];
  }
  if (role === "professional") {
    return [
      { key: "welcome", title: "Welcome" },
      { key: "role", title: "About you" },
      { key: "occupation", title: "Your work" },
      { key: "rhythm", title: "Your rhythm" },
    ];
  }
  // researcher
  return [
    { key: "welcome", title: "Welcome" },
    { key: "role", title: "About you" },
    { key: "rhythm", title: "Your rhythm" },
    { key: "commitments", title: "Commitments" },
  ];
}

export default function OnboardingWizard({ onComplete }) {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState({
    name: "",
    role: "student",
    chronotype: "normal",
    wake_time: "07:00",
    sleep_time: "23:00",
    sleep_hours: 7,
    stress_level: 2,
    daily_commitments: [],
    break_preferences: ["13:00-14:00"],
    lectures_today: 0,
    occupation: "",
    work_hours: "",
    meetings_today: 0,
    occupation_busy_slots: [],
    has_timetable: false,
    timetable_answers: {},
  });
  const [commitmentInput, setCommitmentInput] = useState("");
  const [busySlotInput, setBusySlotInput] = useState("");
  const [collegeHours, setCollegeHours] = useState(""); // e.g. "09:00-15:00"

  // Timetable state
  const [ttUploading, setTtUploading] = useState(false);
  const [ttData, setTtData] = useState(null);
  const [ttQuestions, setTtQuestions] = useState([]);
  const [ttAnswers, setTtAnswers] = useState({});
  const [ttPersonalized, setTtPersonalized] = useState(null);
  const [ttError, setTtError] = useState(null);
  const fileInputRef = useRef(null);

  const STEPS = getSteps(profile.role);

  function update(key, val) {
    setProfile((p) => ({ ...p, [key]: val }));
  }

  function addCommitment() {
    const val = commitmentInput.trim();
    if (!val) return;
    update("daily_commitments", [...profile.daily_commitments, val]);
    setCommitmentInput("");
  }
  function removeCommitment(i) {
    update("daily_commitments", profile.daily_commitments.filter((_, idx) => idx !== i));
  }
  function addBusySlot() {
    const val = busySlotInput.trim();
    if (!val) return;
    update("occupation_busy_slots", [...profile.occupation_busy_slots, val]);
    setBusySlotInput("");
  }
  function removeBusySlot(i) {
    update("occupation_busy_slots", profile.occupation_busy_slots.filter((_, idx) => idx !== i));
  }

  /* ── Timetable upload ──────────────────────── */
  async function handleTimetableUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setTtUploading(true);
    setTtError(null);
    setTtData(null);
    setTtQuestions([]);
    setTtAnswers({});
    setTtPersonalized(null);

    try {
      const result = await uploadTimetable(file);
      setTtData(result);
      setTtQuestions(result.questions_for_user || []);
      const defaults = {};
      (result.questions_for_user || []).forEach((q) => {
        if (q.options?.length) defaults[q.id] = q.options[0];
      });
      setTtAnswers(defaults);
      update("has_timetable", true);
      toast.success("Timetable extracted!");

      if (!result.questions_for_user?.length) {
        const personalized = await personalizeTimetable({});
        setTtPersonalized(personalized);
        if (personalized.todays_commitments?.length) {
          update("daily_commitments", personalized.todays_commitments);
          update("lectures_today", personalized.todays_commitments.length);
        }
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || "Failed to extract timetable";
      setTtError(msg);
      toast.error(msg);
    } finally {
      setTtUploading(false);
    }
  }

  async function handlePersonalize() {
    setTtUploading(true);
    try {
      const personalized = await personalizeTimetable(ttAnswers);
      setTtPersonalized(personalized);
      update("timetable_answers", ttAnswers);
      if (personalized.todays_commitments?.length) {
        update("daily_commitments", personalized.todays_commitments);
        update("lectures_today", personalized.todays_commitments.length);
      }
      toast.success("Timetable personalized!");
    } catch {
      toast.error("Failed to personalize");
    } finally {
      setTtUploading(false);
    }
  }

  /* ── Navigation ────────────────────────────── */
  function next() {
    if (step < STEPS.length - 1) {
      // Before leaving commitments step for students, add college hours as a blocked commitment
      if (currentStepKey === "commitments" && profile.role === "student") {
        let resolvedHours = collegeHours;
        if (collegeHours === "custom") {
          const fromEl = document.getElementById("college-from");
          const toEl = document.getElementById("college-to");
          resolvedHours = `${fromEl?.value || "09:00"}-${toEl?.value || "15:00"}`;
        }
        if (resolvedHours && resolvedHours !== "") {
          // Remove old college block and add new one
          const filtered = profile.daily_commitments.filter(c => !c.endsWith(" College"));
          update("daily_commitments", [...filtered, `${resolvedHours} College`]);
        }
      }
      setStep((s) => s + 1);
    } else {
      const final = { ...profile };
      // For students: ensure college hours are in commitments
      if (final.role === "student") {
        let resolvedHours = collegeHours;
        if (collegeHours === "custom") {
          const fromEl = document.getElementById("college-from");
          const toEl = document.getElementById("college-to");
          resolvedHours = `${fromEl?.value || "09:00"}-${toEl?.value || "15:00"}`;
        }
        if (resolvedHours && resolvedHours !== "") {
          const filtered = final.daily_commitments.filter(c => !c.endsWith(" College"));
          final.daily_commitments = [...filtered, `${resolvedHours} College`];
        }
        // Auto-derive lectures_today from commitment count
        final.lectures_today = final.daily_commitments.length;
      }
      if (final.role === "professional") {
        if (final.occupation_busy_slots.length > 0) {
          final.daily_commitments = [...final.occupation_busy_slots];
        }
        if (final.work_hours && final.work_hours !== "flexible") {
          final.daily_commitments = [
            `${final.work_hours} Work`,
            ...final.daily_commitments.filter((s) => !s.includes("Work")),
          ];
        }
        // Auto-derive lectures_today from commitment count
        final.lectures_today = final.daily_commitments.length;
      }
      if (final.role === "researcher") {
        // Researchers: lectures_today from any added blocks
        final.lectures_today = final.daily_commitments.length;
      }
      onComplete(final);
    }
  }
  function back() {
    if (step > 0) setStep((s) => s - 1);
  }

  const currentStepKey = STEPS[step]?.key;
  const canProceed =
    currentStepKey === "welcome" ? profile.name.trim().length > 0
    : currentStepKey === "role" ? !!profile.role
    : currentStepKey === "occupation" ? profile.occupation.trim().length > 0
    : true;

  return (
    <div className="w-full max-w-lg">
      {/* Progress bar */}
      <div className="flex items-center gap-1 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex-1 flex flex-col items-center gap-1">
            <div className={`h-1.5 w-full rounded-full transition-all duration-300 ${i <= step ? "bg-primary" : "bg-muted"}`} />
            <span className={`text-[10px] font-medium transition ${i <= step ? "text-primary" : "text-muted-foreground"}`}>
              {s.title}
            </span>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-border bg-card shadow-lg p-6 sm:p-8 space-y-6">

        {/* ── Welcome ─────────────────── */}
        {currentStepKey === "welcome" && (
          <div className="space-y-5">
            <div className="text-center space-y-2">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
                <Sparkles size={28} className="text-primary" />
              </div>
              <h1 className="text-xl font-bold">Hey there! I'm CogScheduler</h1>
              <p className="text-sm text-muted-foreground leading-relaxed">
                I'll help you plan your day based on your cognitive energy —
                no burnout, just smart scheduling.
              </p>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">What should I call you?</label>
              <input
                type="text" placeholder="Your name" value={profile.name}
                onChange={(e) => update("name", e.target.value)} autoFocus
                className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-sm
                           placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition"
              />
            </div>
          </div>
        )}

        {/* ── Role ────────────────────── */}
        {currentStepKey === "role" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">What describes you best?</h2>
              <p className="text-xs text-muted-foreground">This helps me calibrate difficulty and energy models.</p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[
                { val: "student", icon: BookOpen, label: "Student" },
                { val: "professional", icon: Briefcase, label: "Professional" },
                { val: "researcher", icon: Sparkles, label: "Researcher" },
              ].map(({ val, icon: Ic, label }) => (
                <button
                  key={val} onClick={() => update("role", val)}
                  className={`flex flex-col items-center gap-2 rounded-xl border p-4 transition cursor-pointer
                    ${profile.role === val ? "border-primary bg-primary/5 ring-2 ring-primary/30" : "border-border hover:border-primary/40 hover:bg-muted/30"}`}
                >
                  <Ic size={24} className={profile.role === val ? "text-primary" : "text-muted-foreground"} />
                  <span className="text-xs font-medium">{label}</span>
                </button>
              ))}
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">How stressed are you today? (1-5)</label>
              <input type="range" min={1} max={5} value={profile.stress_level}
                onChange={(e) => update("stress_level", parseInt(e.target.value))} className="w-full accent-primary" />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>Relaxed</span>
                <span className="font-mono font-semibold text-foreground">{profile.stress_level}</span>
                <span>Very stressed</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Timetable (Student) ─────── */}
        {currentStepKey === "timetable" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">Your College Timetable</h2>
              <p className="text-xs text-muted-foreground">
                Upload your timetable (PDF or photo) and I'll extract your schedule automatically.
              </p>
            </div>

            {/* Upload */}
            {!ttData && !ttUploading && !ttError && (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-border rounded-xl p-8 text-center
                           hover:border-primary/50 hover:bg-muted/20 transition cursor-pointer"
              >
                <Upload size={32} className="mx-auto text-muted-foreground mb-3" />
                <p className="text-sm font-medium mb-1">Drop your timetable here or click to upload</p>
                <p className="text-xs text-muted-foreground">PDF, PNG, JPG — max 10MB</p>
                <input ref={fileInputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp"
                  onChange={handleTimetableUpload} className="hidden" />
              </div>
            )}

            {/* Loading */}
            {ttUploading && (
              <div className="text-center py-8">
                <Loader2 size={32} className="mx-auto animate-spin text-primary mb-3" />
                <p className="text-sm font-medium">Analyzing your timetable with AI…</p>
                <p className="text-xs text-muted-foreground mt-1">This may take 15-30 seconds</p>
              </div>
            )}

            {/* Error */}
            {ttError && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/30 p-4 text-center">
                <AlertCircle size={20} className="mx-auto text-destructive mb-2" />
                <p className="text-sm text-destructive">{ttError}</p>
                <button onClick={() => { setTtError(null); fileInputRef.current?.click(); }}
                  className="mt-2 text-xs text-primary hover:underline cursor-pointer">Try again</button>
              </div>
            )}

            {/* Extracted */}
            {ttData && !ttUploading && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 size={16} /> Timetable extracted!
                  {ttData.institution_name && ttData.institution_name !== "Unknown" && (
                    <span className="text-muted-foreground">— {ttData.institution_name}</span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="font-bold text-foreground">{ttData.subjects?.length || 0}</p>
                    <p className="text-muted-foreground">Subjects</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="font-bold text-foreground">{ttData.days?.length || 0}</p>
                    <p className="text-muted-foreground">Days</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="font-bold text-foreground">{ttData.detected_groups?.length || 0}</p>
                    <p className="text-muted-foreground">Groups</p>
                  </div>
                </div>

                {/* Questions */}
                {ttQuestions.length > 0 && !ttPersonalized && (
                  <div className="space-y-3">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Quick questions to personalize
                    </p>
                    {ttQuestions.map((q) => (
                      <div key={q.id}>
                        <label className="text-sm font-medium mb-1 block">{q.question}</label>
                        <div className="flex flex-wrap gap-2">
                          {q.options.map((opt) => (
                            <button key={opt}
                              onClick={() => setTtAnswers((a) => ({ ...a, [q.id]: opt }))}
                              className={`rounded-lg border px-3 py-1.5 text-xs transition cursor-pointer
                                ${ttAnswers[q.id] === opt
                                  ? "border-primary bg-primary/10 text-primary font-semibold"
                                  : "border-border hover:border-primary/40"}`}
                            >{opt}</button>
                          ))}
                        </div>
                      </div>
                    ))}
                    <button onClick={handlePersonalize}
                      className="w-full rounded-lg bg-primary/10 text-primary py-2 text-sm font-medium
                                 hover:bg-primary/20 transition cursor-pointer">
                      Apply selections
                    </button>
                  </div>
                )}

                {/* Personalized */}
                {ttPersonalized && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-green-600 dark:text-green-400 flex items-center gap-1">
                      <CheckCircle2 size={12} /> Personalized!
                      {ttPersonalized.todays_commitments?.length > 0 && (
                        <span className="text-muted-foreground font-normal">
                          — {ttPersonalized.todays_commitments.length} classes today
                        </span>
                      )}
                    </p>
                    {ttPersonalized.todays_commitments?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {ttPersonalized.todays_commitments.map((c, i) => (
                          <span key={i} className="text-[10px] rounded-full bg-muted px-2.5 py-1 font-medium">{c}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <button onClick={() => { setTtData(null); setTtPersonalized(null); setTtQuestions([]); setTtAnswers({}); setTtError(null); }}
                  className="text-xs text-muted-foreground hover:text-foreground transition cursor-pointer">
                  Upload different timetable
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Occupation (Professional) ── */}
        {currentStepKey === "occupation" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">Tell me about your work</h2>
              <p className="text-xs text-muted-foreground">I'll schedule around your work hours and meetings.</p>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">What do you do?</label>
              <input type="text" placeholder="e.g. Software Engineer, Doctor, Designer…"
                value={profile.occupation} onChange={(e) => update("occupation", e.target.value)} autoFocus
                className="w-full rounded-lg border border-input bg-background px-4 py-2.5 text-sm
                           placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition" />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Typical work hours</label>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { val: "09:00-17:00", label: "9 to 5" },
                  { val: "10:00-18:00", label: "10 to 6" },
                  { val: "10:00-19:00", label: "10 to 7" },
                  { val: "flexible", label: "Flexible" },
                ].map(({ val, label }) => (
                  <button key={val} onClick={() => update("work_hours", val)}
                    className={`rounded-lg border px-3 py-2 text-sm transition cursor-pointer
                      ${profile.work_hours === val
                        ? "border-primary bg-primary/5 ring-2 ring-primary/30 font-semibold"
                        : "border-border hover:border-primary/40"}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Any fixed blocks today? (e.g. "14:00-15:00 Client call")
              </label>
              <div className="flex gap-2">
                <input type="text" placeholder="14:00-15:00 Client call"
                  value={busySlotInput} onChange={(e) => setBusySlotInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addBusySlot()}
                  className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-ring transition" />
                <button type="button" onClick={addBusySlot}
                  className="px-3 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm
                             hover:opacity-90 transition cursor-pointer">Add</button>
              </div>
              {profile.occupation_busy_slots.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {profile.occupation_busy_slots.map((s, i) => (
                    <span key={i} onClick={() => removeBusySlot(i)} title="Click to remove"
                      className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1
                                 text-xs font-medium cursor-pointer hover:bg-destructive/10 hover:text-destructive transition">
                      <Briefcase size={10} />{s}<X size={10} className="text-muted-foreground ml-1" />
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Rhythm ──────────────────── */}
        {currentStepKey === "rhythm" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">Your daily rhythm</h2>
              <p className="text-xs text-muted-foreground">Are you a morning person or a night owl?</p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[
                { val: "early", icon: Sunrise, label: "Early Bird", desc: "Peak before noon" },
                { val: "normal", icon: Sun, label: "Normal", desc: "Peak mid-morning" },
                { val: "late", icon: Moon, label: "Night Owl", desc: "Peak in afternoon" },
              ].map(({ val, icon: Ic, label, desc }) => (
                <button key={val} onClick={() => update("chronotype", val)}
                  className={`flex flex-col items-center gap-1.5 rounded-xl border p-3 transition cursor-pointer
                    ${profile.chronotype === val
                      ? "border-primary bg-primary/5 ring-2 ring-primary/30"
                      : "border-border hover:border-primary/40 hover:bg-muted/30"}`}>
                  <Ic size={22} className={profile.chronotype === val ? "text-primary" : "text-muted-foreground"} />
                  <span className="text-xs font-semibold">{label}</span>
                  <span className="text-[10px] text-muted-foreground">{desc}</span>
                </button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                  <Sunrise size={12} /> Wake up
                </label>
                <input type="time" value={profile.wake_time}
                  onChange={(e) => update("wake_time", e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-ring transition" />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                  <Moon size={12} /> Bedtime
                </label>
                <input type="time" value={profile.sleep_time}
                  onChange={(e) => update("sleep_time", e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-ring transition" />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                  <Clock size={12} /> Slept (hrs)
                </label>
                <input type="number" min={0} max={24} step={0.5}
                  value={profile.sleep_hours} onChange={(e) => update("sleep_hours", parseFloat(e.target.value))}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-ring transition" />
              </div>
            </div>
          </div>
        )}

        {/* ── Commitments ─────────────── */}
        {currentStepKey === "commitments" && profile.role === "student" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">Your college timing today</h2>
              <p className="text-xs text-muted-foreground">
                When are you at college? I'll schedule study tasks around these hours.
              </p>
            </div>

            {/* College hours quick pick */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block">
                College hours today
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { val: "", label: "No college today", desc: "Free all day" },
                  { val: "08:00-13:00", label: "8 AM – 1 PM", desc: "Morning batch" },
                  { val: "09:00-15:00", label: "9 AM – 3 PM", desc: "Regular day" },
                  { val: "09:00-17:00", label: "9 AM – 5 PM", desc: "Full day" },
                  { val: "13:00-17:00", label: "1 PM – 5 PM", desc: "Afternoon batch" },
                  { val: "custom", label: "Custom timing", desc: "Set your own" },
                ].map(({ val, label, desc }) => (
                  <button key={val} onClick={() => setCollegeHours(val)}
                    className={`rounded-lg border px-3 py-2.5 text-left transition cursor-pointer
                      ${collegeHours === val
                        ? "border-primary bg-primary/5 ring-2 ring-primary/30"
                        : "border-border hover:border-primary/40 hover:bg-muted/30"}`}>
                    <span className="text-sm font-medium block">{label}</span>
                    <span className="text-[10px] text-muted-foreground">{desc}</span>
                  </button>
                ))}
              </div>
              {collegeHours === "custom" && (
                <div className="flex gap-2 mt-3 items-center">
                  <input type="time" defaultValue="09:00" id="college-from"
                    className="rounded-lg border border-input bg-background px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-ring transition" />
                  <span className="text-sm text-muted-foreground">to</span>
                  <input type="time" defaultValue="15:00" id="college-to"
                    className="rounded-lg border border-input bg-background px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-ring transition" />
                </div>
              )}
            </div>

            {/* Additional specific slots */}
            {profile.daily_commitments.filter(c => !c.endsWith(" College")).length > 0 || true ? (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  Any extra fixed slots? (optional, e.g. "16:00-17:00 Gym")
                </label>
                <div className="flex gap-2">
                  <input type="text" placeholder="16:00-17:00 Gym"
                    value={commitmentInput} onChange={(e) => setCommitmentInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addCommitment()}
                    className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm
                               focus:outline-none focus:ring-2 focus:ring-ring transition" />
                  <button type="button" onClick={addCommitment}
                    className="px-3 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm
                               hover:opacity-90 transition cursor-pointer">Add</button>
                </div>
                {profile.daily_commitments.filter(c => !c.endsWith(" College")).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {profile.daily_commitments.filter(c => !c.endsWith(" College")).map((c, i) => (
                      <span key={i} onClick={() => removeCommitment(profile.daily_commitments.indexOf(c))} title="Click to remove"
                        className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1
                                   text-xs font-medium cursor-pointer hover:bg-destructive/10 hover:text-destructive transition">
                        <Coffee size={10} />{c}<X size={10} className="text-muted-foreground ml-1" />
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}

        {/* ── Commitments (Researcher) ── */}
        {currentStepKey === "commitments" && profile.role === "researcher" && (
          <div className="space-y-5">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold">Any fixed blocks today?</h2>
              <p className="text-xs text-muted-foreground">
                Meetings, seminars, office hours — add them here. Otherwise you're free all day! 🎉
              </p>
            </div>
            <div>
              <div className="flex gap-2">
                <input type="text" placeholder="14:00-15:30 Lab meeting"
                  value={commitmentInput} onChange={(e) => setCommitmentInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addCommitment()}
                  className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-ring transition" />
                <button type="button" onClick={addCommitment}
                  className="px-3 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm
                             hover:opacity-90 transition cursor-pointer">Add</button>
              </div>
              {profile.daily_commitments.length > 0 ? (
                <div className="flex flex-wrap gap-2 mt-3">
                  {profile.daily_commitments.map((c, i) => (
                    <span key={i} onClick={() => removeCommitment(i)} title="Click to remove"
                      className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1
                                 text-xs font-medium cursor-pointer hover:bg-destructive/10 hover:text-destructive transition">
                      <Coffee size={10} />{c}<X size={10} className="text-muted-foreground ml-1" />
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  No blocks added — your entire day is open for deep work ✨
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── Nav buttons ─────────────── */}
        <div className="flex items-center justify-between pt-2">
          {step > 0 ? (
            <button onClick={back}
              className="text-sm text-muted-foreground hover:text-foreground transition cursor-pointer">← Back</button>
          ) : <div />}
          <div className="flex items-center gap-2">
            {currentStepKey === "timetable" && !ttData && !ttUploading && (
              <button onClick={next}
                className="text-sm text-muted-foreground hover:text-foreground transition cursor-pointer">Skip →</button>
            )}
            <button onClick={next} disabled={!canProceed}
              className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5
                         text-primary-foreground text-sm font-medium shadow-sm
                         hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer">
              {step === STEPS.length - 1 ? (<><Sparkles size={16} /> Let's go!</>) : (<>Continue <ArrowRight size={16} /></>)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
