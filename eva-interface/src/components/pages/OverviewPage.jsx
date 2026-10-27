import { useEffect, useState } from "react";
import { api } from "../../api";
import { useWidgetData } from "../../hooks/useWidgetData";
import AiServerPanel, { HealthBanner, Ring } from "../AiServerPanel";

function Gauge({ label, percent, detail }) {
  const p = Math.round(percent ?? 0);
  const level = p >= 90 ? "is-hot" : p >= 70 ? "is-warm" : "";
  return (
    <div className={`card gauge ${level}`}>
      <span className="card__label">{label}</span>
      <span className="gauge__value">{percent == null ? "—" : `${p}%`}</span>
      <div className="gauge__bar"><i style={{ width: `${Math.min(100, p)}%` }} /></div>
      <span className="card__hint">{detail || " "}</span>
    </div>
  );
}

export default function OverviewPage() {
  const sys = useWidgetData("/api/widgets/system", { intervalMs: 5000 });
  const docker = useWidgetData("/api/widgets/docker", { intervalMs: 10000 });
  const [cities, setCities] = useState(null);
  const [city, setCity] = useState(() => { try { return localStorage.getItem("eva.city") || ""; } catch { return ""; } });
  useEffect(() => {
    const load = () => api("/api/cities").then(setCities).catch(() => {});
    load(); window.addEventListener("eva:cities", load); return () => window.removeEventListener("eva:cities", load);
  }, []);
  const shown = cities && cities.list.includes(city) ? city : cities?.default || "";
  const pick = (c) => { setCity(c); try { localStorage.setItem("eva.city", c); } catch { /* ignoré */ } };
  const weather = useWidgetData(`/api/widgets/weather${shown ? `?city=${encodeURIComponent(shown)}` : ""}`, { intervalMs: 600000 });
  const ai = useWidgetData("/api/aiserver/stats", { intervalMs: 5000 });
  const s = sys.data;
  const containers = docker.data?.containers || [];
  const w = weather.data;

  return (
    <section className="page">
      <header className="page__header">
        <h1>Tableau de bord</h1>
        <span className="page__sub">Mis à jour automatiquement</span>
      </header>
      <div className="page__body">
        <HealthBanner nas={s} ai={ai.data} />
        <div className="card aisrv" data-testid="nas-card">
          <span className="card__label">EVA — le NAS</span>
          <div className="aisrv__rings">
            <Ring label="Processeur" pct={s?.cpu_percent} />
            <Ring label="Mémoire" pct={s?.memory?.percent} line1={s ? `${s.memory.used_gb} / ${s.memory.total_gb} Go` : ""} />
            <Ring label="Disque" pct={s?.disk?.percent} line1={s ? `${s.disk.used_gb} / ${s.disk.total_gb} Go` : ""} />
          </div>
        </div>
        {sys.error && <p className="page__warn">Statistiques système indisponibles.</p>}

        <AiServerPanel />

        <div className="grid grid--2">
          <div className="card">
            <span className="card__label">Conteneurs Docker</span>
            <span className="card__big">{docker.data ? `${docker.data.running} / ${docker.data.total}` : "—"}</span>
            <div className="aisrv__chips">
              {containers.map((c) => (
                <span key={c.name} className={`chip ${c.status === "running" ? "chip--up" : "chip--down"}`}><i />{c.name}</span>
              ))}
              {docker.error && <span className="page__warn">Docker indisponible.</span>}
            </div>
          </div>
          <div className="card">
            <span className="card__label">Météo{shown ? ` — ${shown}` : ""}</span>
            {cities && cities.list.length > 1 && (
              <div className="aisrv__chips" data-testid="weather-cities">
                {cities.list.map((c) => <button key={c} className={`chip chip--btn ${c === shown ? "chip--up" : ""}`} onClick={() => pick(c)}>{c}</button>)}
              </div>
            )}
            <span className="card__big">
              {w?.current?.temperature_c != null ? `${Math.round(w.current.temperature_c)}°C` : "—"}
            </span>
            <span className="card__hint">{w?.current?.condition || (weather.error ? "indisponible" : "chargement…")}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
