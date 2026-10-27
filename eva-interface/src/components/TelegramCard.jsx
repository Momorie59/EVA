import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

export default function TelegramCard() {
  const [st, setSt] = useState(null);
  const [token, setToken] = useState("");
  const [allowed, setAllowed] = useState("");
  const [alerts, setAlerts] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api("/api/telegram/status").then((s) => { setSt(s); setAllowed((s.allowed || []).join(", ")); setAlerts(s.alerts !== false); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function save() {
    setError(""); setMsg("");
    try { await api("/api/telegram", { method: "PUT", body: JSON.stringify({ token, allowed, alerts }) }); setToken(""); setMsg("Enregistré."); await load(); }
    catch (e) { setError(e.message); }
  }
  async function remove() {
    if (!(await confirmer("Déconnecter Telegram ?"))) return;
    await api("/api/telegram", { method: "DELETE" }).catch((e) => setError(e.message));
    setMsg("Déconnecté."); load();
  }

  if (!st) return <div className="card"><span className="card__label">Telegram</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  return (
    <div className="card routercard">
      <span className="card__label">Telegram</span>
      <details className="googlehelp">
        <summary>Mise en place (2 minutes)</summary>
        <ol>
          <li>Dans Telegram, ouvre <strong>@BotFather</strong> → <code>/newbot</code> → choisis un nom : il te donne un <strong>jeton</strong>.</li>
          <li>Colle le jeton ci-dessous et enregistre (laisse la liste vide).</li>
          <li>Écris n'importe quoi à ton bot : il répond « Accès non autorisé. Ton identifiant : 123456 ».</li>
          <li>Mets cet identifiant dans « Identifiants autorisés », enregistre : c'est prêt.</li>
        </ol>
      </details>
      {st.configured && <p className="page__sub">{st.username ? <>Bot <strong>@{st.username}</strong> · </> : null}{st.running ? "à l'écoute" : "en attente"}{st.allowed.length ? ` · ${st.allowed.length} discussion(s) autorisée(s). Les actions sensibles te demandent « oui » ou « non » par message.` : " · aucun identifiant autorisé pour l'instant."}</p>}
      {st.last_error && <p className="page__warn">Dernière erreur : {st.last_error}</p>}
      <div className="routergrid">
        <label className="field"><span>Jeton du bot{st.configured ? " (laisser vide pour le garder)" : ""}</span><input type="password" value={token} onChange={(e) => setToken(e.target.value)} /></label>
        <label className="field"><span>Identifiants autorisés (séparés par des virgules)</span><input value={allowed} onChange={(e) => setAllowed(e.target.value)} placeholder="123456789" /></label>
      </div>
      <label className="field"><span><input type="checkbox" checked={alerts} onChange={(e) => setAlerts(e.target.checked)} /> Recevoir aussi sur Telegram les alertes proactives (serveur, agents planifiés)</span></label>
      <div className="agentform__actions">
        <button className="btn btn--primary" disabled={!token && !st.configured} onClick={save}>Tester et enregistrer</button>
        {st.configured && <button className="btn btn--danger" onClick={remove}>Déconnecter</button>}
      </div>
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
