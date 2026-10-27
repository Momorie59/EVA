import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

const pct = (p) => (p && p.total ? Math.min(100, Math.round((p.completed / p.total) * 100)) : 0);
const COLORS = { ok: "#3ecf8e", slow: "#e8a93c", no: "#e5645a" };

// Modèles d'images du serveur IA : conseillés selon la carte graphique, téléchargés / supprimés depuis EVA, sans terminal.
export default function ImageModelsCard() {
  const [d, setD] = useState(null); const [error, setError] = useState(""); const [msg, setMsg] = useState(""); const [custom, setCustom] = useState("");
  const timer = useRef(null);
  const load = useCallback(() => api("/api/images/models").then((r) => { setD(r); setError(""); return r; }).catch((e) => { setError(e.message); return null; }), []);
  const poll = useCallback(async () => {
    const r = await load();
    clearTimeout(timer.current);
    if (r?.items?.some((i) => i.pull && !i.pull.done)) timer.current = setTimeout(poll, 2000);
  }, [load]);
  useEffect(() => {
    poll();
    window.addEventListener("eva:imagecfg", poll);
    return () => { clearTimeout(timer.current); window.removeEventListener("eva:imagecfg", poll); };
  }, [poll]);

  async function act(path, id, ok) {
    setError(""); setMsg("");
    try { await api(`/api/images/models/${path}`, { method: "POST", body: JSON.stringify({ id }) }); if (ok) setMsg(ok); poll(); } catch (e) { setError(e.message); }
  }
  async function updateServer() {
    setError(""); setMsg("Mise à jour du serveur d'images… il redémarre (environ 30 secondes).");
    try {
      const r = await api("/api/images/server/update", { method: "POST" });
      setMsg(`Serveur d'images mis à jour (version ${r.expected ?? r.version}). Redémarrage en cours…`);
      // Le serveur redémarre : on attend qu'il réponde de nouveau avec la bonne version, puis on rafraîchit tout (cette carte et les réglages d'images).
      for (let i = 0; i < 45; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const st = await load();
        const want = r.expected ?? r.version;
        if (st?.server?.up && !st.server.needs_update && (want == null || st.server.version === want)) {
          setMsg(`Serveur d'images à jour (version ${st.server.version ?? want}) et de nouveau disponible.`);
          window.dispatchEvent(new Event("eva:imagecfg"));
          return;
        }
      }
      setMsg("Mise à jour envoyée, mais le serveur met du temps à redémarrer : recharge la page dans une minute.");
    } catch (e) { setError(e.message); setMsg(""); }
  }
  if (!d) return <div className="card routercard"><span className="card__label">Modèles d'images</span>{error && <p className="page__warn">{error}</p>}</div>;
  const s = d.server;
  return (
    <div className="card routercard" data-testid="imagemodels-card">
      <span className="card__label">Modèles d'images</span>
      <p className="page__sub">Choisis le modèle qui dessine. Les conseils tiennent compte de ta carte graphique ({d.hardware.vram_gb} Go). Le téléchargement se fait sur le serveur IA, depuis Hugging Face.</p>
      {!s.up && <p className="page__warn" data-testid="imagemodels-down">{s.error || "Serveur d'images injoignable."}</p>}
      {s.needs_update && s.token_ok !== false && <p className="page__sub">Ton serveur d'images est ancien : mets-le à jour pour gérer les modèles d'ici.</p>}
      <div className="agentform__actions">
        <button className="btn" type="button" onClick={updateServer} data-testid="imagemodels-update">Mettre à jour le serveur d'images{s.version ? ` (version ${s.version})` : ""}</button>
      </div>
      <ul className="pj-trash__list" data-testid="imagemodels-list">
        {d.items.map((m) => (
          <li key={m.id} data-testid={`imagemodel-${m.id}`} style={{ display: "block" }}>
            <strong>{m.title}</strong>{m.id === d.recommended ? " ⭐ conseillé" : ""}{d.active === m.id ? " · utilisé" : ""}
            <div className="page__sub">{m.about}</div>
            <div className="page__sub">{m.size_gb ? `${m.size_gb} Go` : ""}{m.speed ? ` · ${m.speed}` : ""}{m.quality ? ` · qualité ${m.quality}` : ""} · <span style={{ color: COLORS[m.verdict.level] }}>{m.verdict.label}</span></div>
            {m.pull && !m.pull.done && <div className="page__sub" data-testid={`imagemodel-pull-${m.id}`}>Téléchargement {pct(m.pull)} %…</div>}
            {m.pull?.error && <div className="page__warn">{m.pull.error}</div>}
            <div className="agentform__actions">
              {!m.installed && !(m.pull && !m.pull.done) && <button className="btn btn--primary" onClick={() => act("pull", m.id, "Téléchargement lancé.")} disabled={!s.up} data-testid={`imagemodel-get-${m.id}`}>Télécharger</button>}
              {m.installed && d.active !== m.id && <button className="btn" onClick={() => act("use", m.id, "Modèle changé.")} data-testid={`imagemodel-use-${m.id}`}>Utiliser</button>}
              {m.installed && <button className="btn btn--ghost" onClick={() => confirmer(`Supprimer ${m.title} du serveur d'images ?`).then((ok) => ok && (act("delete", m.id, "Modèle supprimé.")))} data-testid={`imagemodel-del-${m.id}`}>Supprimer</button>}
            </div>
          </li>
        ))}
      </ul>
      <form className="agentform" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) { act("pull", custom.trim(), "Téléchargement lancé."); setCustom(""); } }}>
        <label className="field"><span>Autre modèle du hub Hugging Face (format « auteur/modèle », version diffusers)</span>
          <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="ex. SG161222/Realistic_Vision_V6.0_B1_noVAE" data-testid="imagemodels-custom" /></label>
        <div className="agentform__actions"><button className="btn" type="submit" disabled={!custom.trim() || !s.up}>Télécharger</button></div>
      </form>
      {error && <p className="page__warn" role="alert" data-testid="imagemodels-error">{error}</p>}
      {msg && <p className="page__sub" data-testid="imagemodels-msg">{msg}</p>}
    </div>
  );
}
