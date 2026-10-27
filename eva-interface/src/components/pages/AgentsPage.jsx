import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import TraceSteps, { fmtMs } from "../TraceSteps";
import { confirmer } from "../../confirmer";

function humanSchedule(a) {
  if (a.schedule_type === "manual") return "À la demande";
  if (a.schedule_type === "interval") {
    const s = Number(a.schedule_value);
    if (s % 3600 === 0) return `Toutes les ${s / 3600} h`;
    if (s % 60 === 0) return `Toutes les ${s / 60} min`;
    return `Toutes les ${s} s`;
  }
  const w = /^(\d+) (\d+) \* \* ([0-6])$/.exec(a.schedule_value);
  if (w) return `Chaque ${["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"][Number(w[3])]} à ${w[2].padStart(2, "0")}:${w[1].padStart(2, "0")}`;
  const m = /^(\d+) (\d+) \* \* \*$/.exec(a.schedule_value);
  if (m) return `Chaque jour à ${m[2].padStart(2, "0")}:${m[1].padStart(2, "0")}`;
  return `Cron ${a.schedule_value}`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function RunDetail({ runId }) {
  const [run, setRun] = useState(null);
  useEffect(() => {
    api(`/api/agent-runs/${runId}`).then(setRun).catch(() => setRun({ output: "Impossible de charger cette exécution.", steps: [] }));
  }, [runId]);
  if (!run) return <p className="dash-loading">Chargement…</p>;
  return (
    <div className="rundetail">
      <pre className="rundetail__output">{run.output || "(vide)"}</pre>
      {run.duration_ms != null && (
        <p className="rundetail__meta">
          {fmtMs(run.duration_ms)} · {run.prompt_tokens} → {run.completion_tokens} tokens
        </p>
      )}
      <TraceSteps steps={run.steps} />
    </div>
  );
}

function AgentCard({ agent, onChange }) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [error, setError] = useState("");

  const loadRuns = useCallback(() => {
    api(`/api/agents/${agent.id}/runs`).then((d) => setRuns(d.runs || [])).catch(() => {});
  }, [agent.id]);

  useEffect(() => {
    if (open) loadRuns();
  }, [open, loadRuns, agent.last_run_at, agent.running]);

  async function act(fn) {
    setError("");
    try {
      await fn();
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  const status = agent.running ? "running" : agent.last_status || "none";
  return (
    <div className={`acard ${agent.enabled ? "" : "is-off"}`}>
      <div className="acard__head">
        <span className={`acard__status acard__status--${status}`} title={status} />
        <div className="acard__title">
          <strong>{agent.name}</strong>
          <span>{humanSchedule(agent)}{agent.enabled ? "" : " · désactivé"}</span>
        </div>
        <div className="acard__actions">
          <button className="btn btn--primary" disabled={agent.running} onClick={() => act(() => api(`/api/agents/${agent.id}/run`, { method: "POST" }))}>
            {agent.running ? "En cours…" : "Lancer"}
          </button>
          {agent.schedule_type !== "manual" && (
            <button className="btn" onClick={() => act(() => api(`/api/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !agent.enabled }) }))}>
              {agent.enabled ? "Pause" : "Activer"}
            </button>
          )}
          <button className="btn" onClick={() => setOpen((v) => !v)}>{open ? "Masquer" : "Historique"}</button>
          <button className="btn btn--danger" onClick={() => confirmer(`Supprimer l'agent « ${agent.name} » ?`).then((ok) => ok && (act(() => api(`/api/agents/${agent.id}`, { method: "DELETE" }))))}>×</button>
        </div>
      </div>
      <p className="acard__instruction">{agent.instruction || "Instruction du modèle par défaut."}</p>
      <div className="acard__meta">
        <span>Dernier : {fmtDate(agent.last_run_at)}</span>
        <span>Prochain : {agent.enabled ? fmtDate(agent.next_run_at) : "—"}</span>
      </div>
      {agent.last_output && !open && <p className="acard__last">{agent.last_output}</p>}
      {error && <p className="page__warn">{error}</p>}
      {open && (
        <div className="acard__runs">
          {runs.length === 0 && <p className="dash-empty">Aucune exécution pour l'instant.</p>}
          {runs.map((r) => (
            <div key={r.id}>
              <button className={`arun ${selectedRun === r.id ? "is-open" : ""}`} onClick={() => setSelectedRun(selectedRun === r.id ? null : r.id)}>
                <span className={`acard__status acard__status--${r.status}`} />
                <span>{fmtDate(r.started_at)}</span>
                <span className="arun__preview">{r.preview}</span>
              </button>
              {selectedRun === r.id && <RunDetail runId={r.id} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DesignBox({ onCreated }) {
  const [goal, setGoal] = useState("");
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function design(e) {
    e.preventDefault(); setBusy(true); setError(""); setD(null);
    try { setD(await api("/api/agents/design", { method: "POST", body: JSON.stringify({ goal }) })); } catch (err) { setError(err.message); }
    setBusy(false);
  }
  async function create() {
    setBusy(true); setError("");
    try {
      await api("/api/agents", { method: "POST", body: JSON.stringify({ name: d.name, template: "custom", instruction: d.instruction, schedule_type: d.schedule_type, schedule_value: d.schedule_value }) });
      setD(null); setGoal(""); onCreated();
    } catch (err) { setError(err.message); }
    setBusy(false);
  }
  return (
    <div className="card agentform" data-testid="agent-design">
      <span className="card__label">✨ Décris ce que tu veux, EVA prépare l'agent</span>
      <form onSubmit={design}>
        <textarea rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} data-testid="design-goal"
          placeholder="Ex : chaque matin à 7h, cherche les nouveautés sur les GPU d'occasion et résume-moi les 3 meilleures offres" />
        <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={busy || goal.trim().length < 8} data-testid="design-go">{busy && !d ? "Réflexion…" : "Préparer l'agent"}</button></div>
      </form>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {d && (
        <div data-testid="design-result">
          <label className="field"><span>Nom</span><input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
          <label className="field"><span>Consigne (modifiable)</span><textarea rows={5} value={d.instruction} onChange={(e) => setD({ ...d, instruction: e.target.value })} /></label>
          <p className="page__sub">Quand : <b>{humanSchedule(d)}</b> · outils prévus : {d.tools.slice(0, 12).join(", ")}{d.source === "regles" ? " · (rédigé sans modèle : relis la consigne)" : ""}</p>
          <div className="agentform__actions"><button className="btn btn--primary" onClick={create} disabled={busy || !d.name.trim()} data-testid="design-create">Créer cet agent</button></div>
        </div>
      )}
    </div>
  );
}

function NewAgentForm({ templates, onCreated, onCancel }) {
  const [tpl, setTpl] = useState(templates[0]);
  const [name, setName] = useState(templates[0]?.name || "");
  const [instruction, setInstruction] = useState("");
  const [mode, setMode] = useState("manual");
  const [minutes, setMinutes] = useState(60);
  const [time, setTime] = useState("07:00");
  const [cronExpr, setCronExpr] = useState("0 7 * * *");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function pickTemplate(t) {
    setTpl(t);
    setName(t.name);
    if (t.schedule_type === "interval") {
      setMode("interval");
      setMinutes(Math.round(Number(t.schedule_value) / 60));
    } else if (t.schedule_type === "cron") {
      const m = /^(\d+) (\d+) \* \* \*$/.exec(t.schedule_value);
      if (m) {
        setMode("daily");
        setTime(`${m[2].padStart(2, "0")}:${m[1].padStart(2, "0")}`);
      } else {
        setMode("cron");
        setCronExpr(t.schedule_value);
      }
    } else {
      setMode("manual");
    }
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    let schedule_type = "manual";
    let schedule_value = "";
    if (mode === "interval") {
      schedule_type = "interval";
      schedule_value = String(Math.round(Number(minutes) * 60));
    } else if (mode === "daily") {
      const [h, m] = time.split(":").map(Number);
      schedule_type = "cron";
      schedule_value = `${m} ${h} * * *`;
    } else if (mode === "cron") {
      schedule_type = "cron";
      schedule_value = cronExpr;
    }
    setBusy(true);
    try {
      await api("/api/agents", {
        method: "POST",
        body: JSON.stringify({ name, template: tpl.id, instruction, schedule_type, schedule_value }),
      });
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card agentform" onSubmit={submit}>
      <span className="card__label">Nouvel agent</span>
      <div className="tplgrid">
        {templates.map((t) => (
          <button type="button" key={t.id} className={`tpl ${tpl.id === t.id ? "is-active" : ""}`} onClick={() => pickTemplate(t)}>
            <strong>{t.name}</strong>
            <span>{t.description}</span>
          </button>
        ))}
      </div>
      <label className="field">
        <span>Nom</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label className="field">
        <span>{tpl.needs_instruction ? "Sujet / instruction (obligatoire)" : "Précisions (facultatif)"}</span>
        <textarea rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder={tpl.id === "custom" ? "Ce que l'agent doit faire…" : "Ex : les nouveautés sur les GPU d'occasion"} />
      </label>
      <div className="field">
        <span>Planification</span>
        <div className="schedrow">
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="manual">À la demande</option>
            <option value="interval">Toutes les N minutes</option>
            <option value="daily">Chaque jour à une heure</option>
            <option value="cron">Expression cron</option>
          </select>
          {mode === "interval" && <input type="number" min="1" value={minutes} onChange={(e) => setMinutes(e.target.value)} />}
          {mode === "daily" && <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />}
          {mode === "cron" && <input value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="0 7 * * 1-5" />}
        </div>
      </div>
      {error && <p className="page__warn">{error}</p>}
      <div className="agentform__actions">
        <button type="button" className="btn" onClick={onCancel}>Annuler</button>
        <button type="submit" className="btn btn--primary" disabled={busy}>Créer l'agent</button>
      </div>
    </form>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api("/api/agents").then((d) => { setAgents(d.agents || []); setError(""); }).catch((e) => { setAgents((a) => a || []); setError(e.message); });
  }, []);

  useEffect(() => {
    refresh();
    api("/api/agent-templates").then((d) => setTemplates(d.templates || [])).catch(() => {});
  }, [refresh]);

  // Rafraîchit plus souvent tant qu'un agent tourne
  const anyRunning = agents?.some((a) => a.running);
  useEffect(() => {
    const id = setInterval(refresh, anyRunning ? 2500 : 20000);
    return () => clearInterval(id);
  }, [refresh, anyRunning]);

  return (
    <section className="page">
      <header className="page__header">
        <h1>Agents</h1>
        <span className="page__sub">Tâches autonomes, à la demande ou planifiées — seules les actions sans risque sont autorisées</span>
        <button className="btn btn--primary page__action" onClick={() => setCreating((v) => !v)} disabled={templates.length === 0}>
          {creating ? "Fermer" : "+ Nouvel agent"}
        </button>
      </header>
      <div className="page__body">
        {error && <p className="page__warn">Serveur injoignable ou trop ancien : {error}</p>}
        {creating && templates.length > 0 && (<>
          <DesignBox onCreated={() => { setCreating(false); refresh(); }} />
          <NewAgentForm templates={templates} onCreated={() => { setCreating(false); refresh(); }} onCancel={() => setCreating(false)} />
        </>)}
        {agents && agents.length === 0 && !creating && (
          <p className="dash-empty">Aucun agent pour l'instant. Crée-en un à partir d'un modèle : briefing du matin, recherche approfondie, veille…</p>
        )}
        {(agents || []).map((a) => <AgentCard key={a.id} agent={a} onChange={refresh} />)}
      </div>
    </section>
  );
}
