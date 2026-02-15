import { useState } from "react";
import { getGoogleAuthUrl, postAuthLogout } from "../api/schedule";
import { LogOut } from "lucide-react";

/* Google "G" logo as inline SVG */
function GoogleLogo({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className="shrink-0">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
  );
}

export default function GoogleLoginButton({ user, onLogin, onLogout }) {
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setLoading(true);
    try {
      const { auth_url } = await getGoogleAuthUrl();
      // Redirect to Google consent screen
      window.location.href = auth_url;
    } catch (err) {
      // If OAuth not configured, show a friendly message
      const msg = err?.response?.data?.detail || "Google login not available";
      alert(msg);
      setLoading(false);
    }
  }

  async function handleLogout() {
    try {
      await postAuthLogout();
      onLogout?.();
    } catch {
      onLogout?.();
    }
  }

  // Logged in state
  if (user) {
    return (
      <div className="flex items-center gap-2">
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.name}
            className="w-7 h-7 rounded-full border border-border"
          />
        ) : (
          <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
            {user.name?.charAt(0)?.toUpperCase() || "?"}
          </div>
        )}
        <span className="text-xs text-muted-foreground hidden sm:block max-w-[100px] truncate">
          {user.name}
        </span>
        <button
          onClick={handleLogout}
          className="p-1.5 rounded-md hover:bg-muted transition cursor-pointer"
          title="Logout"
        >
          <LogOut size={13} className="text-muted-foreground" />
        </button>
      </div>
    );
  }

  // Login button
  return (
    <button
      onClick={handleLogin}
      disabled={loading}
      className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5
                 text-xs font-medium hover:bg-muted/50 transition cursor-pointer
                 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
    >
      <GoogleLogo size={16} />
      <span>{loading ? "Connecting…" : "Sign in with Google"}</span>
    </button>
  );
}
