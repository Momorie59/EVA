import { useEffect, useState } from "react";
import { api } from "../../api";
import TraceSteps, { fmtMs } from "../TraceSteps";

function fmtDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function TraceDetail({ id }) {
  const [t, setT] = useState(null);
  useEffect(() => { api(`/api/traces/${id}`).then(setT).catch(() => setT({ steps: [], error: "Trace illisible" })); }, [id]);
  if (!t) return <p className="dash-loading">Chargement…</p>;
  return (
    <div className="rundetail">
      <p className="rundetail__meta">{t.model} · {fmtMs(t.duration_ms)} · {t.prompt_tokens} → {t.completion_tokens} tokens · ≈ {(t.energy_kwh * 1000).toFixed(3)} Wh</p>
      {t.error && <p className="page__warn">{t.error}</p>}
      <TraceSteps steps={t.steps} />
    </div>
  );
}

export default function TracesPage() {
  const [sum, setSum] = useState(null);
  const [days, setDays] = useState(7);
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/api/traces/summary?days=${days}`).then(setSum).catch((e) => setError(e.message));
    api("/api/traces?limit=50").then((d) => setList(d.traces)).catch((e) => setError(e.message));
  }, [days]);

  const maxTok = Math.max(1, ...(sum?.per_day || []).map((d) => d.tokens));

  return (
    <section className="page">
      <header className="page__header">
        <h1>Traces</h1>
        <span className="page__sub">Ce qu'EVA a fait, étape par étape — avec coût et énergie estimés</span>
        <select className="page__action" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={1}>24 h</option><option value={7}>7 jours</option><option value={30}>30 jours</option>
        </select>
      </header>
      <div className="page__body">
        {error && <p className="page__warn">Serveur injoignable ou trop ancien : {error}</p>}
        {sum && (
          <div className="card srcstats">
            <span className="card__label">Bilan sur {sum.days === 1 ? "24 h" : `${sum.days} jours`}</span>
            <div className="srcstats__grid">
              <div><strong>{sum.traces}</strong><span>tours / exécutions</span></div>
              <div><strong>{sum.prompt_tokens + sum.completion_tokens}</strong><span>tokens</span></div>
              <div><strong>{(sum.energy_kwh * 1000).toFixed(2)} Wh</strong><span>énergie estimée</span></div>
              <div><strong>{sum.local_cost_eur.toFixed(4)} €</strong><span>coût électrique</span></div>
            </div>
            <p className="page__sub">
              Équivalent cloud pour les mêmes tokens :{" "}
              {sum.cloud_equivalents.map((c) => `${c.name} ≈ ${c.usd.toFixed(3)} $`).join(" · ")}.
            </p>
            <p className="page__sub">{sum.assumptions.note} Hypothèses : {sum.assumptions.gpu_watts} W, {sum.assumptions.kwh_price_eur} €/kWh (réglables via EVA_GPU_WATTS, EVA_KWH_PRICE).</p>
            {sum.per_day.length > 0 && (
              <div className="tbars">
                {sum.per_day.map((d) => (
                  <div key={d.day} className="tbars__col" title={`${d.day} : ${d.tokens} tokens`}>
                    <span style={{ height: `${Math.max(4, (d.tokens / maxTok) * 60)}px` }} />
                    <em>{d.day.slice(8)}</em>
                  </div>
                ))}
              </div>
            )}
            {sum.tools.length > 0 && <p className="page__sub">Outils les plus utilisés : {sum.tools.slice(0, 6).map((t) => `${t.name} ×${t.count}`).join(", ")}</p>}
          </div>
        )}
        {list && list.length === 0 && <p className="dash-empty">Aucune trace pour l'instant. Parle à EVA ou lance un agent.</p>}
        {(list || []).map((t) => (
          <div key={t.id}>
            <button className={`arun ${open === t.id ? "is-open" : ""}`} onClick={() => setOpen(open === t.id ? null : t.id)}>
              <span className={`acard__status acard__status--${t.ok ? "ok" : "error"}`} />
              <span className="skilltag">{t.kind === "agent" ? "agent" : "chat"}</span>
              <span className="arun__preview">{t.label || "(sans libellé)"}</span>
              <span className="rundetail__meta">{fmtMs(t.duration_ms)} · {t.n_steps} étapes · {fmtDate(t.started_at)}</span>
            </button>
            {open === t.id && <TraceDetail id={t.id} />}
          </div>
        ))}
      </div>
    </section>
  );
}
