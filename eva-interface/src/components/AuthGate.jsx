import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { CORE_URL, authHeaders, setSession, markLoggedOut } from "../urls";

const Ctx = createContext({ required: false, user: null, logout: () => {}, refresh: () => {} });
export const useAuth = () => useContext(Ctx);

// Écran de connexion — n'apparaît que si la connexion est activée (Paramètres › Sécurité). Sinon EVA s'ouvre directement.
function LoginScreen({ onLogged }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const res = await fetch(`${CORE_URL}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user, password, code }) });
      const d = await res.json().catch(() => ({}));
      if (res.status === 401 && d.detail === "mfa_required") { setNeedCode(true); setBusy(false); return; }
      if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : `Erreur ${res.status}`);
      setSession(d.token); onLogged();
    } catch (err) { setError(err.message); if (!needCode) setPassword(""); setCode(""); }
    setBusy(false);
  }
  return (
    <main className="login" data-testid="login-screen">
      <form className="card login__card" onSubmit={submit}>
        <h1 className="login__word">EVA</h1>
        <p className="page__sub">Connecte-toi pour accéder à ton assistant.</p>
        <label className="field"><span>Identifiant</span>
          <input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" autoFocus data-testid="login-user" /></label>
        <label className="field"><span>Mot de passe</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" data-testid="login-password" /></label>
        {needCode && (
          <label className="field"><span>Code de l'application d'authentification (6 chiffres)</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={8} autoFocus data-testid="login-code" /></label>
        )}
        {error && <p className="page__warn" role="alert" data-testid="login-error">{error}</p>}
        <button className="btn btn--primary" type="submit" disabled={busy || !user || !password || (needCode && !code)} data-testid="login-submit">{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
      {window.location.protocol === "https:" && (
        <p className="page__sub" style={{ textAlign: "center", marginTop: 12 }}>
          <a href="/api/https/install" data-testid="login-cert-link">Un avertissement de sécurité s'affiche ? Installe le certificat d'EVA (1 minute, une seule fois)</a>
        </p>
      )}
    </main>
  );
}

// EVA protégée par le jeton EVA_AUTH_TOKEN et sans aucun compte : on saisit le jeton une fois, puis on crée un compte (Paramètres › Sécurité).
function TokenScreen({ onLogged, tried }) {
  const [token, setToken] = useState("");
  return (
    <main className="login" data-testid="token-screen">
      <form className="card login__card" onSubmit={(e) => { e.preventDefault(); setSession(token.trim()); onLogged(); }}>
        <h1 className="login__word">EVA</h1>
        <p className="page__sub">Cette EVA est protégée par un jeton d'accès (EVA_AUTH_TOKEN dans le fichier .env du NAS). Saisis-le une fois ; crée ensuite un compte dans Paramètres › Sécurité pour que chaque personne se connecte avec son identifiant.</p>
        <label className="field"><span>Jeton d'accès</span>
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" autoFocus data-testid="token-input" /></label>
        {tried && <p className="page__warn" role="alert" data-testid="token-error">Jeton refusé.</p>}
        <button className="btn btn--primary" type="submit" disabled={!token.trim()} data-testid="token-submit">Entrer</button>
      </form>
    </main>
  );
}

export default function AuthGate({ children }) {
  const [st, setSt] = useState(null);
  const [tried, setTried] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${CORE_URL}/api/auth/status`, { headers: authHeaders() });
      setSt(await res.json());
    } catch {
      setSt((s) => s || { login_required: false, authenticated: true });   // EVA CORE injoignable : l'application affichera « hors ligne »
    }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60000);
    const on = () => refresh();
    window.addEventListener("eva:unauthorized", on); window.addEventListener("focus", on);
    return () => { clearInterval(t); window.removeEventListener("eva:unauthorized", on); window.removeEventListener("focus", on); };
  }, [refresh]);
  const logout = useCallback(async () => {
    try { await fetch(`${CORE_URL}/api/auth/logout`, { method: "POST", headers: authHeaders() }); } catch { /* déjà déconnecté */ }
    setSession(""); markLoggedOut(); refresh();
  }, [refresh]);
  const value = useMemo(() => ({ required: !!st?.login_required, protectedByToken: !!st?.protected, user: st?.user || null, role: st?.role || null, mfa: !!st?.mfa, features: st?.features || [], minPassword: st?.min_password || 12, logout, refresh }), [st, logout, refresh]);
  if (!st) return null;
  if (st.login_required && !st.authenticated) return <LoginScreen onLogged={refresh} />;
  if (!st.login_required && st.protected && !st.authenticated) return <TokenScreen onLogged={() => { setTried(true); refresh(); }} tried={tried} />;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
