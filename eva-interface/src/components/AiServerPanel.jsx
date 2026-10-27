import { useEffect, useState } from "react";
import { api } from "../api";
import { useWidgetData } from "../hooks/useWidgetData";

// Statistiques du dashboard web du serveur IA, dessinées avec le thème d'EVA (variables CSS) — rien n'est incrusté depuis l'autre site.
export function Ring({ label, pct, line1, line2 }) {
  const p = Math.max(0, Math.min(100, Math.round(pct ?? 0)));
  const level = p >= 90 ? "hot" : p >= 70 ? "warm" : "ok";
  const R = 34, C = 2 * Math.PI * R;
  return (
    <div className={`ring ring--${level}`}>
      <svg viewBox="0 0 84 84" aria-hidden="true">
        <circle cx="42" cy="42" r={R} className="ring__bg" />
        <circle cx="42" cy="42" r={R} className="ring__fg" strokeDasharray={`${(C * p) / 100} ${C}`} transform="rotate(-90 42 42)" />
        <text x="42" y="47" textAnchor="middle" className="ring__val">{pct == null ? "—" : `${p}%`}</text>
      </svg>
      <div className="ring__txt"><b>{label}</b>{line1 && <span>{line1}</span>}{line2 && <span>{line2}</span>}</div>
    </div>
  );
}

function Spark({ points }) {
  if (!points || points.length < 2) return <p className="card__hint">Pas encore d'historique de consommation.</p>;
  const v = points.map((p) => p.total_w ?? p.w ?? 0);
  const max = Math.max(...v, 1), min = Math.min(...v);
  const W = 300, H = 64;
  const xy = v.map((y, i) => [(i / (v.length - 1)) * W, H - 6 - ((y - min) / (max - min || 1)) * (H - 14)]);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="aisrv__spark" role="img" aria-label="Consommation électrique">
      <path d={`${d} L${W},${H} L0,${H} Z`} className="aisrv__fill" />
      <path d={d} fill="none" stroke="var(--accent, currentColor)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Bar({ label, pct, detail }) {
  const p = Math.max(0, Math.min(100, Math.round(pct ?? 0)));
  return (
    <div className={`disk ${p >= 90 ? "is-hot" : p >= 75 ? "is-warm" : ""}`}>
      <span>{label}</span><div className="disk__bar"><i style={{ width: `${p}%` }} /></div><em>{pct == null ? "—" : `${p} %`}{detail ? ` · ${detail}` : ""}</em>
    </div>
  );
}

const gb = (mb) => (mb == null ? "" : `${(mb / 1024).toFixed(1)} Go`);

export default function AiServerPanel() {
  const st = useWidgetData("/api/aiserver/stats", { intervalMs: 5000 });
  const [period, setPeriod] = useState("24h");
  const [pw, setPw] = useState(null);
  useEffect(() => { api(`/api/aiserver/power?period=${period}`).then(setPw).catch(() => setPw(null)); }, [period]);
  const s = st.data;

  if (!s) return <div className="card" data-testid="aisrv"><span className="card__label">Serveur IA</span><p className="card__hint">Chargement…</p></div>;
  if (!s.ok) {
    return (
      <div className="card" data-testid="aisrv">
        <span className="card__label">Serveur IA</span>
        <p className="page__warn" data-testid="aisrv-error">{s.error}</p>
        <p className="card__hint">Adresse essayée : {s.url}. Vérifie qu'il est allumé, ou règle l'adresse dans Paramètres › Services › Serveur IA.</p>
      </div>
    );
  }
  const g = s.gpu || {}, c = s.cpu || {}, m = s.memory || {};
  const sv = s.services || {};
  const chip = (ok, label, extra) => <span className={`chip ${ok ? "chip--up" : "chip--down"}`}><i />{label}{ok && extra ? ` · ${extra}` : !ok ? " · arrêté" : ""}</span>;
  return (
    <div className="card aisrv" data-testid="aisrv">
      <div className="aisrv__head">
        <div>
          <span className="card__label">Serveur IA</span>
          <div className="aisrv__title">{s.hostname}{typeof s.uptime === "string" && s.uptime ? <small> · allumé depuis {s.uptime}</small> : null}</div>
        </div>
        <a className="btn btn--ghost" href={s.url} target="_blank" rel="noreferrer" data-testid="aisrv-open">Dashboard complet ↗</a>
      </div>
      <div className="aisrv__rings">
        <Ring label="Processeur" pct={c.pct} line1={c.temp_c != null ? `${c.temp_c} °C` : ""} line2={c.freq_mhz ? `${c.freq_mhz} MHz` : ""} />
        <Ring label="Mémoire" pct={m.ram_pct} line1={`${gb(m.ram_used_mb)} / ${gb(m.ram_total_mb)}`} />
        {g.available && <Ring label={g.name || "Carte graphique"} pct={g.util_pct} line1={g.temp_c != null ? `${g.temp_c} °C` : ""} line2={g.power_w ? `${Math.round(g.power_w)} W` : ""} />}
        {g.available && <Ring label="Mémoire vidéo" pct={g.mem_pct} line1={`${gb(g.mem_used_mb)} / ${gb(g.mem_total_mb)}`} />}
      </div>
      {(s.disks || []).length > 0 && (
        <div className="aisrv__disks">
          {s.disks.slice(0, 4).map((d) => (
            <div key={d.mount} className={`disk ${d.pct >= 90 ? "is-hot" : d.pct >= 75 ? "is-warm" : ""}`}>
              <span>{d.mount}</span><div className="disk__bar"><i style={{ width: `${Math.min(100, d.pct)}%` }} /></div><em>{gb(d.used_mb)} / {gb(d.size_mb)}</em>
            </div>
          ))}
        </div>
      )}
      <div className="aisrv__chips">
        {chip(sv.ollama?.active, "Ollama", `${sv.ollama?.model_count ?? 0} modèle(s)`)}
        {chip(sv.webui?.active, "Open WebUI", "actif")}
        {chip(sv.docker?.active, "Docker", `${sv.docker?.containers ?? 0} conteneur(s)`)}
      </div>
      <div className="aisrv__row">
        <span className="card__label">Consommation{s.power?.total_w != null ? ` · ${Math.round(s.power.total_w)} W` : ""}</span>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Période">
          <option value="24h">24 h</option><option value="7d">7 jours</option><option value="30d">30 jours</option>
        </select>
      </div>
      <Spark points={pw?.points} />
      {pw?.ok && pw.points.length > 0 && <small className="card__hint">Moyenne {pw.avg_w} W · {pw.kwh_period} kWh sur la période</small>}
    </div>
  );
}

// Carte « statistiques » dans la conversation : le NAS (EVA) + le serveur IA, sans fenêtre flottante.
export function StatsCard() {
  const sys = useWidgetData("/api/widgets/system", { intervalMs: 5000 });
  const s = sys.data;
  return (
    <div className="statscard" data-testid="stats-card">
      {s && (
        <div className="card aisrv">
          <span className="card__label">EVA — le NAS</span>
          <div className="aisrv__grid">
            <Bar label="Processeur" pct={s.cpu_percent} />
            <Bar label="Mémoire" pct={s.memory?.percent} detail={`${s.memory?.used_gb} / ${s.memory?.total_gb} Go`} />
            <Bar label="Disque" pct={s.disk?.percent} detail={`${s.disk?.used_gb} / ${s.disk?.total_gb} Go`} />
          </div>
        </div>
      )}
      <AiServerPanel />
    </div>
  );
}

// Bandeau « tout va bien / à surveiller » : résume le NAS et le serveur IA en une phrase.
export function HealthBanner({ nas, ai }) {
  const issues = [];
  if (nas) {
    if (nas.cpu_percent >= 90) issues.push(`NAS : processeur à ${Math.round(nas.cpu_percent)} %`);
    if (nas.memory?.percent >= 90) issues.push(`NAS : mémoire à ${Math.round(nas.memory.percent)} %`);
    if (nas.disk?.percent >= 90) issues.push(`NAS : disque rempli à ${Math.round(nas.disk.percent)} %`);
  }
  if (ai?.ok) {
    if (ai.gpu?.available && ai.gpu.temp_c >= 80) issues.push(`carte graphique à ${ai.gpu.temp_c} °C`);
    if (ai.cpu?.temp_c >= 85) issues.push(`processeur IA à ${ai.cpu.temp_c} °C`);
    if (ai.memory?.ram_pct >= 90) issues.push(`mémoire du serveur IA à ${Math.round(ai.memory.ram_pct)} %`);
    (ai.disks || []).forEach((d) => { if (d.pct >= 90) issues.push(`disque ${d.mount} du serveur IA à ${d.pct} %`); });
    if (ai.services?.ollama && !ai.services.ollama.active) issues.push("Ollama est arrêté");
  } else if (ai && ai.ok === false) issues.push("serveur IA injoignable");
  const ok = issues.length === 0 && (nas || ai);
  if (!nas && !ai) return null;
  return (
    <div className={`health ${ok ? "health--ok" : "health--warn"}`} data-testid="health-banner">
      <span className="health__dot" />
      <b>{ok ? "Tout va bien" : "À surveiller"}</b>
      <span>{ok ? "Le NAS et le serveur IA fonctionnent normalement." : issues.join(" · ")}</span>
    </div>
  );
}
