import { useEffect, useState } from "react";
import { api } from "../api";

// Mémoire de conversation (num_ctx) et précision (température) envoyées à Ollama.
const CTX = [
  [4096, "4 096 — très léger"],
  [8192, "8 192 — recommandé (GTX 1060 6 Go)"],
  [12288, "12 288 — fichiers moyens"],
  [16384, "16 384 — gros fichiers (modèle ≤ 7B, plus lent)"],
  [32768, "32 768 — très gros (demande beaucoup de mémoire)"],
];

export default function LlmOptionsCard() {
  const [cfg, setCfg] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api("/api/models/options").then(setCfg).catch((e) => setError(e.message)); }, []);
  if (!cfg) return <div className="card routercard"><span className="card__label">Compréhension</span>{error && <p className="page__warn">{error}</p>}</div>;
  async function save(e) {
    e.preventDefault(); setError(""); setMsg("");
    try { setCfg(await api("/api/models/options", { method: "PUT", body: JSON.stringify({ num_ctx: +cfg.num_ctx, temperature: +cfg.temperature }) })); setMsg("Enregistré — actif dès le prochain message."); }
    catch (err) { setError(err.message); }
  }
  const opts = CTX.some(([v]) => v === +cfg.num_ctx) ? CTX : [...CTX, [+cfg.num_ctx, `${cfg.num_ctx} — personnalisé`]];
  return (
    <div className="card routercard" data-testid="llmopts-card">
      <span className="card__label">Compréhension (mémoire &amp; précision)</span>
      <p className="page__sub">Une mémoire trop petite fait oublier à EVA ses consignes et tes fichiers. Plus grande = mieux comprendre, mais plus lent et plus gourmand en mémoire vidéo.</p>
      <form className="agentform" onSubmit={save}>
        <label className="field"><span>Mémoire de conversation</span>
          <select value={cfg.num_ctx} onChange={(e) => setCfg({ ...cfg, num_ctx: e.target.value })} data-testid="opt-ctx">
            {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label className="field"><span>Précision (température : {(+cfg.temperature).toFixed(2)})</span>
          <input type="range" min="0" max="1" step="0.05" value={cfg.temperature} onChange={(e) => setCfg({ ...cfg, temperature: e.target.value })} data-testid="opt-temp" />
          <small>Bas = rigoureux (code, outils). Haut = créatif.</small></label>
        <div className="agentform__actions"><button className="btn btn--primary" type="submit" data-testid="opt-save">Enregistrer</button></div>
      </form>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
