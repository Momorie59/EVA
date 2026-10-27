import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

export default function HomeAssistantCard() {
  const [st, setSt] = useState(null);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api("/api/homeassistant/status").then(setSt).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function save() {
    setError(""); setMsg("");
    try { await api("/api/homeassistant", { method: "PUT", body: JSON.stringify({ url, token }) }); setToken(""); setMsg("Home Assistant connecté."); await load(); }
    catch (e) { setError(e.message); }
  }
  async function remove() {
    if (!(await confirmer("Déconnecter Home Assistant ?"))) return;
    await api("/api/homeassistant", { method: "DELETE" }).catch((e) => setError(e.message));
    setMsg("Déconnecté."); load();
  }

  if (!st) return <div className="card"><span className="card__label">Home Assistant</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  return (
    <div className="card routercard">
      <span className="card__label">Home Assistant</span>
      {st.configured ? (
        <>
          <p className="page__sub">Connecté à <strong>{st.url}</strong>. EVA lit l'état de la maison ; toute commande te demande ton accord. Déverrouiller, désarmer l'alarme, ouvrir un garage/portail ou redémarrer Home Assistant sont interdits à EVA. Les personnes et leur position ne lui sont jamais exposées.</p>
          <div className="agentform__actions"><button className="btn btn--danger" onClick={remove}>Déconnecter</button></div>
        </>
      ) : (
        <>
          <details className="googlehelp">
            <summary>Où trouver le jeton</summary>
            <ol><li>Dans Home Assistant : ton profil (en bas à gauche) → onglet « Sécurité ».</li><li>« Jetons d'accès longue durée » → Créer un jeton → nomme-le « EVA » et copie-le.</li></ol>
          </details>
          <div className="routergrid">
            <label className="field"><span>Adresse</span><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://192.168.1.20:8123" /></label>
            <label className="field"><span>Jeton d'accès longue durée</span><input type="password" value={token} onChange={(e) => setToken(e.target.value)} /></label>
          </div>
          <div className="agentform__actions"><button className="btn btn--primary" disabled={!url || !token} onClick={save}>Tester et enregistrer</button></div>
        </>
      )}
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
