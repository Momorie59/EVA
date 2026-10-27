import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";
import { useAuth } from "./AuthGate";

const ICON = { ok: "✅", warn: "⚠️", fail: "❌" };
const STEP_FIELDS = { early_warning: "early_warning", notification: "notification", final_report: "final_report" };

// Contrôle de sécurité aligné sur les mesures NIS2 (art. 21) + registre d'incidents (art. 23). Aucune valeur juridique : voir NIS2.md.
export default function Nis2Card() {
  const auth = useAuth();
  const [a, setA] = useState(null);
  const [inc, setInc] = useState([]);
  const [sev, setSev] = useState([]);
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState("moyen");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setA(await api("/api/nis2"));
      const d = await api("/api/nis2/incidents"); setInc(d.incidents); setSev(d.severities);
      setError("");
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load, auth.required, auth.mfa, auth.role]);

  const add = async (e) => {
    e.preventDefault();
    try { await api("/api/nis2/incidents", { method: "POST", body: JSON.stringify({ title, severity, description: desc }) }); setTitle(""); setDesc(""); await load(); }
    catch (er) { setError(er.message); }
  };
  const patch = async (id, body) => { try { await api(`/api/nis2/incidents/${id}`, { method: "PATCH", body: JSON.stringify(body) }); await load(); } catch (er) { setError(er.message); } };
  const del = async (id) => { try { await api(`/api/nis2/incidents/${id}`, { method: "DELETE" }); await load(); } catch (er) { setError(er.message); } };
  const report = async () => {
    const r = await fetch(`${CORE_URL}/api/nis2/report`, { headers: authHeaders() });
    const url = URL.createObjectURL(await r.blob());
    const el = document.createElement("a"); el.href = url; el.download = "eva-nis2-rapport.md"; el.click(); URL.revokeObjectURL(url);
  };
  const fmt = (iso) => { try { return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); } catch { return iso; } };

  return (
    <div className="card routercard" data-testid="nis2-card">
      <span className="card__label">Sécurité — contrôle NIS2</span>
      <p className="page__sub">Vérifie automatiquement les mesures de sécurité de la directive européenne NIS2 (art. 21) que l'installation d'EVA permet de contrôler. <b>Ce n'est pas une certification</b> : un outil d'aide, pas un avis juridique.</p>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {a && (
        <>
          <div className="nis2__score" data-testid="nis2-score">
            <b style={{ fontSize: "1.6rem" }}>{a.score} %</b> &nbsp; ✅ {a.counts.ok} &nbsp; ⚠️ {a.counts.warn} &nbsp; ❌ {a.counts.fail}
            <button className="btn btn--ghost" onClick={load} style={{ marginLeft: 12 }}>Relancer</button>
            <button className="btn" onClick={report} data-testid="nis2-report">Télécharger le rapport</button>
          </div>
          <ul className="nis2__list" style={{ listStyle: "none", padding: 0 }}>
            {a.checks.map((c) => (
              <li key={c.id} data-testid={`nis2-${c.id}`} data-status={c.status} style={{ margin: "8px 0" }}>
                {ICON[c.status]} <b>{c.title}</b> <small className="page__sub">({c.measure}) {a.measures[c.measure]}</small>
                <div className="page__sub">{c.detail}</div>
                {c.fix && <div className="page__sub">➜ {c.fix}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
      <b>Registre des incidents</b>
      <p className="page__sub">En cas d'incident important : alerte précoce sous 24 h, notification sous 72 h, rapport final sous 1 mois. Note ici ce qui s'est passé ; EVA suit les échéances.</p>
      <button className="btn btn--ghost" onClick={() => setOpen(!open)} data-testid="nis2-new">{open ? "Fermer" : "Déclarer un incident"}</button>
      {open && (
        <form className="agentform" onSubmit={add}>
          <label className="field"><span>Titre</span><input value={title} onChange={(e) => setTitle(e.target.value)} data-testid="inc-title" /></label>
          <label className="field"><span>Gravité</span><select value={severity} onChange={(e) => setSeverity(e.target.value)}>{sev.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label className="field"><span>Description</span><textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} /></label>
          <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!title} data-testid="inc-add">Enregistrer</button></div>
        </form>
      )}
      {inc.map((i) => (
        <div key={i.id} className="card" data-testid="nis2-incident" style={{ marginTop: 8 }}>
          <b>{i.title}</b> <small>({i.severity} · {i.status} · détecté le {fmt(i.detected)})</small>
          {i.description && <div className="page__sub">{i.description}</div>}
          {i.steps.map((s) => (
            <label key={s.key} className="switch-row" style={{ color: s.late ? "var(--danger, #c0392b)" : undefined }}>
              <input type="checkbox" checked={!!s.done} onChange={(e) => patch(i.id, e.target.checked ? { mark: [s.key] } : { unmark: [s.key] })} />
              {s.label} — {s.done ? `fait le ${fmt(s.done)}` : `avant le ${fmt(s.due)}${s.late ? " (EN RETARD)" : ""}`}
            </label>
          ))}
          <div className="agentform__actions">
            <button className="btn" onClick={() => patch(i.id, { status: i.status === "clos" ? "ouvert" : "clos" })}>{i.status === "clos" ? "Rouvrir" : "Clore"}</button>
            <button className="btn btn--ghost" onClick={() => del(i.id)}>Supprimer</button>
          </div>
        </div>
      ))}
    </div>
  );
}
