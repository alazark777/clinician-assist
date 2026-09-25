import { useState } from "react";
import { LoginPanel } from "./components/LoginPanel";
import { ProfileWorkspace } from "./components/ProfileWorkspace";

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);

  return (
    <main className="app-shell">
      {!authenticated ? (
        <LoginPanel onLoggedIn={() => setAuthenticated(true)} />
      ) : (
        <ProfileWorkspace onLoggedOut={() => setAuthenticated(false)} />
      )}
    </main>
  );
}
