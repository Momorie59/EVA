import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

const when = (t) => new Date(t * 1000).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });

// Mémoire d'EVA : ce qu'elle a retenu sur toi, les règles qu'elle propose, les sujets qu'elle a appris du net. Tout est visible, modifiable, effaçable.
export default function MindCard() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [topic, setTopic] = useState("");
  const [open, setOpen] = useState("");
  const timer = useRef(null);

  const load = useCallback(() => api("/api/mind").then((r) => { setD(r); setError(""); return r; }).catch((e) => { setError(e.message); return null; }), []);
  const poll = useCallback(async () => {
    const r = await load();
    clearTimeout(timer.current);
    if (r?.lessons?.some((l) => l.status === "running")) timer.current = setTimeout(poll, 4000);
  }, [load]);
  useEffect(() => { poll(); return () => clearTimeout(timer.current); }, [poll]);

  async function act(fn, ok) {
    setError(""); setMsg("");
    try { const r = await fn(); if (ok) setMsg(typeof ok === "function" ? ok(r) : ok); await poll(); return r; } catch (e) { setError(e.message); return null; }
  }
  const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
  const put = (path, body) => api(path, { method: "PUT", body: JSON.stringify(body) });
  const del = (path) => api(path, { method: "DELETE" });

  if (!d) return <div className="card routercard"><span className="card__label">Mémoire d'EVA</span>{error && <p className="page__warn">{error}</p>}</div>;
  const pending = d.rules.filter((r) => r.status === "pending");
  const active = d.rules.filter((r) => r.status === "active");
  return (
    <div className="card routercard" data-testid="mind-card">
      <span className="card__label">Apprentissage d'EVA — règles et sujets du net</span>
      <p className="page__sub">Tout reste sur ton NAS. Ce qu'EVA retient de toi (« retiens que… ») est dans la page Mémoire. Ici : les règles qu'elle te propose d'après tes 👍/👎, et les sujets qu'elle étudie sur le net (« apprends-moi comment… »).</p>
      {error && <p className="page__warn" role="alert" data-testid="mind-error">{error}</p>}
      {msg && <p className="page__sub" data-testid="mind-msg">{msg}</p>}
      <label className="field" style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={d.enabled} onChange={(e) => { const on = e.target.checked; setD((x) => ({ ...x, enabled: on })); act(() => put("/api/mind/enabled", { enabled: on }), on ? "Apprentissage activé." : "Apprentissage coupé : EVA n'utilise ni ne retient rien."); }} data-testid="mind-enabled" />
        <span>Laisser EVA apprendre (règles, sujets)</span>
      </label>

      <h4 style={{ margin: "18px 0 6px" }}>Règles pour mieux te répondre</h4>
      <p className="page__sub">EVA relit tes 👍 / 👎 sous les réponses et propose des règles. Rien ne s'applique sans ton accord.</p>
      {pending.map((r) => (
        <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", margin: "4px 0" }} data-testid="mind-rule-pending">
          <span style={{ flex: 1 }}>💡 {r.text}</span>
          <button className="btn btn--primary" onClick={() => act(() => put(`/api/mind/rules/${r.id}`, { status: "active" }), "Règle appliquée.")} data-testid="mind-rule-accept">Appliquer</button>
          <button className="btn btn--ghost" onClick={() => act(() => del(`/api/mind/rules/${r.id}`), "Proposition refusée.")}>Refuser</button>
        </div>
      ))}
      {active.map((r) => (
        <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", margin: "4px 0" }} data-testid="mind-rule-active">
          <span style={{ flex: 1 }}>✅ {r.text}</span>
          <button className="btn btn--ghost" onClick={() => act(() => put(`/api/mind/rules/${r.id}`, { status: "pending" }), "Règle retirée (remise en attente).")}>Retirer</button>
        </div>
      ))}
      <div className="agentform__actions">
        <button className="btn" onClick={() => act(() => post("/api/mind/review"), (r) => (r.added.length ? `${r.added.length} règle(s) proposée(s).` : "Aucune tendance claire dans tes avis pour l'instant."))} data-testid="mind-review">Analyser mes avis</button>
      </div>

      <h4 style={{ margin: "18px 0 6px" }}>Sujets appris du net ({d.lessons.length}/{d.limits.lessons})</h4>
      <form className="agentform" onSubmit={(e) => { e.preventDefault(); if (topic.trim()) act(() => post("/api/mind/learn", { topic: topic.trim() }), "EVA étudie le sujet en tâche de fond (quelques minutes).").then((r) => r && setTopic("")); }}>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={160} placeholder="Ex. le fonctionnement d'un moteur Stirling" data-testid="mind-topic" />
        <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!topic.trim()} data-testid="mind-learn">Apprendre ce sujet</button></div>
      </form>
      <ul className="pj-trash__list" data-testid="mind-lessons">
        {[...d.lessons].reverse().map((l) => (
          <li key={l.id} style={{ display: "block" }} data-testid="mind-lesson">
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <strong style={{ flex: 1 }}>{l.topic}</strong>
              <small className="page__sub">{l.status === "running" ? "⏳ étude en cours…" : l.status === "done" ? `appris le ${when(l.created)}` : "échec"}</small>
              {l.status === "done" && <button className="btn btn--ghost" onClick={() => setOpen(open === l.id ? "" : l.id)} aria-expanded={open === l.id}>{open === l.id ? "Masquer" : "Lire"}</button>}
              <button className="btn btn--ghost" onClick={() => act(() => del(`/api/mind/lessons/${l.id}`), "Supprimé.")} aria-label="Supprimer ce sujet" data-testid="mind-lesson-del">×</button>
            </div>
            {l.status === "error" && <p className="page__warn">{l.error || "Échec."}</p>}
            {open === l.id && (
              <div className="page__sub" style={{ whiteSpace: "pre-wrap", margin: "6px 0" }}>
                {l.summary}
                <div style={{ marginTop: 6 }}>Sources : {l.sources.map((s, i) => <span key={s.url}>{i ? " · " : ""}<a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></span>)}</div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
