import { useEffect, useState } from "react";
import { api } from "../api";

export default function AiServerCard() {
  const [cfg, setCfg] = useState(null);
  const [url, setUrl] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api("/api/aiserver/config").then((c) => { setCfg(c); setUrl(c.url); }).catch((e) => setError(e.message)); }, []);
  async function save(e) {
    e.preventDefault(); setError(""); setMsg("");
    try {
      const c = await api("/api/aiserver/config", { method: "PUT", body: JSON.stringify({ url: url === cfg.default ? "" : url }) });
      setCfg(c); setUrl(c.url);
      const s = await api("/api/aiserver/stats");
      setMsg(s.ok ? `Connecté à ${s.hostname || c.url}.` : s.error);
    } catch (er) { setError(er.message); }
  }
  return (
    <div className="card routercard" data-testid="aisrv-card">
      <span className="card__label">Serveur IA — dashboard web</span>
      <p className="card__hint">Adresse du dashboard installé avec le serveur IA (port 7842 par défaut). EVA y lit les statistiques (processeur, carte graphique, disques, consommation) et les affiche dans le Tableau de bord, avec son thème.</p>
      <form className="schedrow" onSubmit={save}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://192.168.1.20:7842" data-testid="aisrv-url" />
        <button className="btn btn--primary" type="submit" data-testid="aisrv-save">Enregistrer et tester</button>
      </form>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub" data-testid="aisrv-msg">{msg}</p>}
    </div>
  );
}
