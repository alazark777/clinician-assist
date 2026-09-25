import { FormEvent, useState } from "react";
import { createDemoSession } from "../api/client";
import { AgentApiError } from "../utils/errors";

interface LoginPanelProps {
  onLoggedIn: () => void;
}

export function LoginPanel({ onLoggedIn }: LoginPanelProps) {
  const [username, setUsername] = useState("reviewer");
  const [passphrase, setPassphrase] = useState("local-demo");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createDemoSession({ username, passphrase });
      onLoggedIn();
    } catch (err) {
      if (err instanceof AgentApiError) {
        if (err.body?.code === "invalid_origin") {
          setError(
            "Origin not allowed. Open the app at http://127.0.0.1:5173 (not localhost) while the agent runs on port 8000.",
          );
        } else if (err.body?.code === "invalid_credentials") {
          setError("Invalid username or passphrase. Use reviewer / local-demo with the real agent.");
        } else if (err.status === 0 || err.message === "Failed to fetch") {
          setError(
            "Cannot reach the agent API. Start agent-service on http://127.0.0.1:8000 and check web/.env VITE_AGENT_API_BASE_URL.",
          );
        } else {
          setError(err.body?.message ?? "Demo login failed. Check credentials and API availability.");
        }
      } else if (err instanceof Error && err.message.includes("VITE_AGENT_API_BASE_URL")) {
        setError("Missing VITE_AGENT_API_BASE_URL. Copy web/.env.example to web/.env.");
      } else {
        setError("Demo login failed. Check credentials and API availability.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="login-heading">
      <h2 id="login-heading">Demo session</h2>
      <p className="form-hint">
        Real stack: sign in with <strong>reviewer</strong> / <strong>local-demo</strong> (see{" "}
        <code>agent-service/secrets/demo-sessions.json</code>).
      </p>
      <form onSubmit={handleSubmit} data-testid="login-form">
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Passphrase
          <input
            type="password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" disabled={busy} data-testid="login-submit">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </section>
  );
}
