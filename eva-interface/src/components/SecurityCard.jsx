import { useState } from "react";
import { api } from "../api";
import { setSession } from "../urls";
import { useAuth } from "./AuthGate";

// Connexion par identifiant + mot de passe : désactivée par défaut, à activer ici. Les autres appareils devront se connecter.
export default function SecurityCard() {
  const auth = useAuth();
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [cur, setCur] = useState("");
  const [off, setOff] = useState(false);
  const [offPw, setOffPw] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mfa, setMfa] = useState(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaPw, setMfaPw] = useState("");

  async function run(fn, done) {
    setBusy(true); setError(""); setMsg("");
    try { await fn(); if (done) setMsg(done); } catch (e) { setError(e.message); }
    setBusy(false);
  }
  const enable = (e) => { e.preventDefault(); if (pw !== pw2) return setError("Les deux mots de passe sont différents."); run(async () => {
    const r = await api("/api/auth/setup", { method: "POST", body: JSON.stringify({ user, password: pw }) });
    setSession(r.token); setPw(""); setPw2(""); await auth.refresh();
  }, "Connexion activée : cet appareil est connecté ; les autres devront se connecter."); };
  const change = (e) => { e.preventDefault(); if (pw !== pw2) return setError("Les deux mots de passe sont différents."); run(async () => {
    const r = await api("/api/auth/password", { method: "POST", body: JSON.stringify({ current: cur, new: pw }) });
    setCur(""); setPw(""); setPw2(""); setMsg(`Mot de passe changé${r.revoked ? ` (${r.revoked} autre(s) appareil(s) déconnecté(s))` : ""}.`);
  }); };
  const logoutAll = () => run(async () => { const r = await api("/api/auth/logout-all", { method: "POST" }); setMsg(`${r.revoked} autre(s) appareil(s) déconnecté(s).`); });
  const disable = (e) => { e.preventDefault(); run(async () => {
    await api("/api/auth/disable", { method: "POST", body: JSON.stringify({ password: offPw }) });
    setSession(""); setOff(false); setOffPw(""); await auth.refresh();
  }, "Connexion par mot de passe désactivée. (Si EVA_AUTH_TOKEN est défini dans .env, ce jeton protège toujours l'accès.)"); };

  const mfaBegin = () => run(async () => { setMfa(await api("/api/auth/mfa/begin", { method: "POST" })); });
  const mfaEnable = (e) => { e.preventDefault(); run(async () => {
    await api("/api/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code: mfaCode }) });
    setMfa(null); setMfaCode(""); await auth.refresh();
  }, "Double authentification activée : le code sera demandé à chaque connexion."); };
  const mfaOff = (e) => { e.preventDefault(); run(async () => {
    await api("/api/auth/mfa/disable", { method: "POST", body: JSON.stringify({ password: mfaPw }) });
    setMfaPw(""); await auth.refresh();
  }, "Double authentification désactivée."); };

  return (
    <div className="card routercard" data-testid="security-card">
      <span className="card__label">Sécurité — connexion par mot de passe</span>
      {!auth.required ? (
        <>
          <p className="page__sub">Aujourd'hui, toute personne connectée à ton réseau peut ouvrir EVA, modifier tes projets et lancer du code dans le bac à sable. Active la connexion pour que seules les personnes autorisées y accèdent (le premier compte est administrateur et pourra en ajouter d’autres) (interface, voix, partage des projets non concerné : il a son propre mot de passe).</p>
          <form className="agentform" onSubmit={enable}>
            <label className="field"><span>Identifiant</span><input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" placeholder="ex. alice" data-testid="sec-user" /></label>
            <label className="field"><span>Mot de passe ({auth.minPassword} caractères minimum)</span><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" data-testid="sec-pw" /></label>
            <label className="field"><span>Confirmer le mot de passe</span><input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" data-testid="sec-pw2" /></label>
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={busy || !user || !pw} data-testid="sec-enable">Activer la connexion</button></div>
          </form>
        </>
      ) : (
        <>
          <p className="page__sub" data-testid="sec-state">Connexion activée — compte <b>{auth.user}</b> ({auth.role === "admin" ? "administrateur" : "utilisateur"}). Les sessions durent 30 jours.</p>
          <form className="agentform" onSubmit={change}>
            <label className="field"><span>Mot de passe actuel</span><input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" data-testid="sec-cur" /></label>
            <label className="field"><span>Nouveau mot de passe</span><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" data-testid="sec-pw" /></label>
            <label className="field"><span>Confirmer</span><input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" data-testid="sec-pw2" /></label>
            <div className="agentform__actions">
              <button className="btn btn--primary" type="submit" disabled={busy || !cur || !pw} data-testid="sec-change">Changer le mot de passe</button>
              <button className="btn" type="button" onClick={logoutAll} disabled={busy} data-testid="sec-logout-all">Déconnecter les autres appareils</button>
              <button className="btn btn--ghost" type="button" onClick={auth.logout} data-testid="sec-logout">Se déconnecter</button>
            </div>
          </form>
          <div className="mfa" data-testid="mfa-box">
            <b>Double authentification (TOTP)</b>
            {auth.mfa ? (
              <form className="pj-row" onSubmit={mfaOff}>
                <span className="page__sub">Activée sur ton compte.</span>
                <input type="password" value={mfaPw} onChange={(e) => setMfaPw(e.target.value)} placeholder="Mot de passe pour désactiver" autoComplete="current-password" data-testid="mfa-off-pw" />
                <button className="btn btn--danger" type="submit" disabled={busy || !mfaPw} data-testid="mfa-off">Désactiver</button>
              </form>
            ) : !mfa ? (
              <>
                <p className="page__sub">Ajoute un code à usage unique (Google Authenticator, Aegis, 2FAS, FreeOTP…) en plus du mot de passe. Recommandé pour les administrateurs (NIS2).</p>
                <button className="btn" onClick={mfaBegin} disabled={busy} data-testid="mfa-begin">Activer la double authentification</button>
              </>
            ) : (
              <form className="agentform" onSubmit={mfaEnable}>
                <p className="page__sub">Dans ton application, ajoute un compte « saisie manuelle » avec cette clé (type : basé sur l'heure) :</p>
                <code data-testid="mfa-secret" style={{ userSelect: "all", wordBreak: "break-all" }}>{mfa.secret}</code>
                <p className="page__sub">Ou ouvre ce lien depuis ton téléphone : <a href={mfa.uri}>ajouter à l'application</a>. Puis saisis le code affiché pour confirmer.</p>
                <label className="field"><span>Code à 6 chiffres</span><input value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" data-testid="mfa-code" /></label>
                <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={busy || !mfaCode} data-testid="mfa-enable">Confirmer</button>
                  <button className="btn" type="button" onClick={() => setMfa(null)}>Annuler</button></div>
              </form>
            )}
          </div>
          {auth.role === "admin" && (!off
            ? <button className="btn btn--ghost" onClick={() => setOff(true)} data-testid="sec-off">Désactiver la connexion pour tous…</button>
            : <form className="pj-row" onSubmit={disable}>
                <input type="password" value={offPw} onChange={(e) => setOffPw(e.target.value)} placeholder="Mot de passe pour confirmer" autoComplete="current-password" data-testid="sec-off-pw" />
                <button className="btn btn--danger" type="submit" disabled={busy || !offPw} data-testid="sec-off-ok">Désactiver</button>
                <button className="btn" type="button" onClick={() => { setOff(false); setOffPw(""); }}>Annuler</button>
              </form>)}
        </>
      )}
      {error && <p className="page__warn" role="alert" data-testid="sec-error">{error}</p>}
      {msg && <p className="page__sub" data-testid="sec-msg">{msg}</p>}
    </div>
  );
}
