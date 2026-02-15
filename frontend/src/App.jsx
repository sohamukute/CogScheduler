import { useState, useEffect } from "react";
import { postConverse, getProfile, putProfile, getHealth, getAuthMe } from "./api/schedule";
import toast, { Toaster } from "react-hot-toast";

import ThemeToggle from "./components/ThemeToggle";
import GoogleLoginButton from "./components/GoogleLoginButton";
import OnboardingWizard from "./components/OnboardingWizard";
import ChatInterface from "./components/ChatInterface";
import ScheduleSidebar from "./components/ScheduleSidebar";

import { Brain, Heart, PanelRightClose, PanelRight, User, LogOut } from "lucide-react";

/* ─── app ───────────────────────────────────────────────── */
export default function App() {
  const [phase, setPhase] = useState("loading"); // loading | onboarding | chat
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [healthy, setHealthy] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [googleUser, setGoogleUser] = useState(null); // {name, email, avatar_url, ...}

  /* ── bootstrap ────────────────────────────────────────── */
  useEffect(() => {
    // Handle OAuth callback params
    const params = new URLSearchParams(window.location.search);
    if (params.get("auth_success") === "true") {
      setGoogleUser({
        name: params.get("name") || "",
        email: params.get("email") || "",
        avatar_url: params.get("avatar") || "",
        session_id: params.get("session_id") || "",
      });
      // Clean URL
      window.history.replaceState({}, "", window.location.pathname);
    }

    Promise.allSettled([
      getHealth().then(() => setHealthy(true)).catch(() => setHealthy(false)),
      getAuthMe().then((auth) => {
        if (auth?.authenticated) {
          setGoogleUser(auth);
        }
      }).catch(() => {}),
      getProfile()
        .then((p) => {
          if (p && p.name) {
            setProfile(p);
            setPhase("chat");
          } else {
            setPhase("onboarding");
          }
        })
        .catch(() => setPhase("onboarding")),
    ]);
  }, []);

  /* ── onboarding complete ──────────────────────────────── */
  async function handleOnboardingDone(prof) {
    try {
      const saved = await putProfile(prof);
      setProfile(saved);
      setPhase("chat");
      toast.success(`Welcome, ${prof.name}! Let's plan your day.`);
    } catch {
      toast.error("Failed to save profile — continuing anyway.");
      setProfile(prof);
      setPhase("chat");
    }
  }

  /* ── send message → converse endpoint ─────────────────── */
  async function handleSend(message) {
    setLoading(true);
    try {
      const data = await postConverse({ message });
      setResult(data);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        "Something went wrong. Try again?";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  /* ── reset to re-onboard ──────────────────────────────── */
  function handleReset() {
    setProfile(null);
    setResult(null);
    setPhase("onboarding");
  }

  /* ── loading state ────────────────────────────────────── */
  if (phase === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Brain size={40} className="text-primary animate-pulse" />
          <p className="text-sm text-muted-foreground">Loading CogScheduler…</p>
        </div>
      </div>
    );
  }

  /* ── onboarding ───────────────────────────────────────── */
  if (phase === "onboarding") {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <header className="border-b border-border bg-background/80 backdrop-blur-md">
          <div className="max-w-3xl mx-auto flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2.5">
              <Brain size={24} className="text-primary" />
              <h1 className="text-base font-bold tracking-wide">CogScheduler</h1>
            </div>
            <div className="flex items-center gap-2">
              <GoogleLoginButton
                user={googleUser}
                onLogin={setGoogleUser}
                onLogout={() => setGoogleUser(null)}
              />
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="flex-1 flex items-center justify-center p-4">
          <OnboardingWizard onComplete={handleOnboardingDone} />
        </main>
      </div>
    );
  }

  /* ── main chat + sidebar layout ───────────────────────── */
  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-background/80 backdrop-blur-md z-30">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-center gap-2.5">
            <Brain size={22} className="text-primary" />
            <h1 className="text-sm font-bold tracking-wide hidden sm:block">CogScheduler</h1>
          </div>

          <div className="flex items-center gap-2">
            {/* Google login */}
            <GoogleLoginButton
              user={googleUser}
              onLogin={setGoogleUser}
              onLogout={() => setGoogleUser(null)}
            />

            {/* Profile chip */}
            {profile?.name && !googleUser && (
              <span className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground
                              bg-muted/50 rounded-full px-2.5 py-1">
                <User size={11} />
                {profile.name}
                {profile.chronotype === "early" && " 🌅"}
                {profile.chronotype === "late" && " 🌙"}
                {profile.chronotype === "normal" && " ☀️"}
              </span>
            )}

            {/* health */}
            {healthy !== null && (
              <span
                className={`flex items-center gap-1 text-[10px] ${
                  healthy ? "text-green-600 dark:text-green-400" : "text-destructive"
                }`}
              >
                <Heart size={10} />
                {healthy ? "Online" : "Offline"}
              </span>
            )}

            {/* sidebar toggle */}
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="p-1.5 rounded-md hover:bg-muted transition cursor-pointer"
              title={sidebarOpen ? "Hide schedule" : "Show schedule"}
            >
              {sidebarOpen ? <PanelRightClose size={16} /> : <PanelRight size={16} />}
            </button>

            {/* reset */}
            <button
              onClick={handleReset}
              className="p-1.5 rounded-md hover:bg-muted transition cursor-pointer"
              title="Reset profile"
            >
              <LogOut size={14} className="text-muted-foreground" />
            </button>

            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Body: chat + sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat panel */}
        <div
          className={`flex flex-col border-r border-border transition-all duration-300
            ${sidebarOpen ? "w-full md:w-[55%] lg:w-[50%]" : "w-full"}`}
        >
          <ChatInterface
            onSendMessage={handleSend}
            loading={loading}
            profile={profile}
            scheduleResult={result}
          />
        </div>

        {/* Schedule sidebar */}
        {sidebarOpen && (
          <div className="hidden md:flex flex-col w-[45%] lg:w-[50%] bg-card overflow-hidden">
            <ScheduleSidebar result={result} profile={profile} isLoggedIn={!!googleUser} />
          </div>
        )}
      </div>
    </div>
  );
}
