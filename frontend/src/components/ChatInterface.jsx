import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Bot, User, Sparkles, Sun, Moon, CloudSun, Coffee } from "lucide-react";

function getTimeGreeting() {
  const h = new Date().getHours();
  if (h < 5) return { text: "Late night?", icon: Moon, emoji: "🌙" };
  if (h < 12) return { text: "Good morning", icon: Sun, emoji: "☀️" };
  if (h < 17) return { text: "Good afternoon", icon: CloudSun, emoji: "🌤️" };
  if (h < 21) return { text: "Good evening", icon: Coffee, emoji: "🌆" };
  return { text: "Evening", icon: Moon, emoji: "🌙" };
}

export default function ChatInterface({ onSendMessage, loading, profile, scheduleResult }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Auto greet on mount — friendly, warm, simple
  useEffect(() => {
    const g = getTimeGreeting();
    const name = profile?.name ? `, ${profile.name}` : "";
    const role = profile?.role || "student";

    let greeting = `${g.emoji} ${g.text}${name}! Ready to plan your day?\n\n`;
    greeting += `Just tell me what you need to do — keep it simple:\n`;
    greeting += `• "Study calculus for 2 hours"\n`;
    greeting += `• "Work on my essay and read chapter 5"\n`;
    if (role === "student" && profile?.daily_commitments?.length > 0) {
      greeting += `\n📅 I already know your class schedule — I'll plan around your lectures automatically.`;
    }
    setMessages([{ role: "assistant", content: greeting, ts: Date.now() }]);
  }, [profile?.name]);

  // When schedule result comes in — keep it SHORT and positive
  useEffect(() => {
    if (!scheduleResult) return;
    const taskCount = scheduleResult.parsed_tasks?.length ?? 0;
    const blocks = scheduleResult.schedule ?? [];
    const taskBlocks = blocks.filter(b => !b.is_break);
    const breakBlocks = blocks.filter(b => b.is_break);
    const gam = scheduleResult.gamification ?? {};

    if (taskCount === 0) {
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: "I didn't catch any specific tasks. Could you tell me exactly what you need to do?\n\nFor example: \"Study physics for 1.5 hours and finish my lab report\"",
        ts: Date.now(),
      }]);
      return;
    }

    // Build a clean, friendly summary
    let reply = `✅ Your schedule is ready!\n\n`;

    // Show the timeline inline — compact and scannable
    taskBlocks.forEach((b) => {
      reply += `⏰ **${b.start_time} – ${b.end_time}** · ${b.task_title}\n`;
    });
    if (breakBlocks.length > 0) {
      reply += `\n☕ ${breakBlocks.length} break${breakBlocks.length > 1 ? "s" : ""} included to keep you fresh.\n`;
    }

    // Gamification — keep it light
    if (gam.xp) reply += `\n⭐ +${gam.xp} XP`;
    if (gam.streak > 0) reply += ` · 🔥 Streak: ${gam.streak}`;
    if (gam.badges?.length) reply += ` · 🏅 ${gam.badges.join(", ")}`;
    if (gam.xp) reply += `\n`;

    reply += `\nWant to adjust anything? Just ask!`;

    setMessages((prev) => [...prev, { role: "assistant", content: reply, ts: Date.now() }]);
  }, [scheduleResult]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: Date.now() }]);
    setInput("");
    onSendMessage(text);
    inputRef.current?.focus();
  }

  // Quick suggestions — context-aware
  const suggestions = messages.length <= 1 ? [
    "Study calculus for 2 hours",
    "Read chapter 5 and write lab report",
    "Plan a productive study session",
  ] : [];

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                <Bot size={16} className="text-primary" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap
                ${msg.role === "user"
                  ? "bg-primary text-primary-foreground rounded-br-md"
                  : "bg-muted/60 text-foreground rounded-bl-md"
                }`}
            >
              {msg.content}
            </div>
            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0 mt-0.5">
                <User size={16} className="text-secondary-foreground" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Bot size={16} className="text-primary" />
            </div>
            <div className="bg-muted/60 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">
                Analyzing tasks & building your optimal schedule…
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick suggestions */}
      {suggestions.length > 0 && (
        <div className="px-4 pb-2 flex flex-wrap gap-2">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => {
                setInput(s);
                inputRef.current?.focus();
              }}
              className="rounded-full border border-border bg-card px-3 py-1.5 text-xs
                         text-muted-foreground hover:text-foreground hover:border-primary/40
                         transition cursor-pointer"
            >
              <Sparkles size={10} className="inline mr-1" />
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-border p-4">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            placeholder="Tell me what you need to do today…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            className="flex-1 rounded-xl border border-input bg-background px-4 py-2.5 text-sm
                       placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring
                       disabled:opacity-50 transition"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-xl bg-primary px-4 py-2.5 text-primary-foreground
                       hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                       transition cursor-pointer"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </form>
    </div>
  );
}
