// Déroulé d'une trace : appels au modèle (tokens, durée) et appels d'outils.
export function fmtMs(ms) {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

export default function TraceSteps({ steps }) {
  if (!steps || steps.length === 0) {
    return <p className="dash-empty">Aucune étape enregistrée.</p>;
  }
  return (
    <ol className="tsteps">
      {steps.map((s, i) => (
        <li key={i} className={`tsteps__item tsteps__item--${s.type} ${s.ok === false ? "is-fail" : ""}`}>
          <span className="tsteps__dot" />
          <div className="tsteps__main">
            {s.type === "llm" ? (
              <>
                <strong>Modèle</strong>
                <span className="tsteps__meta">
                  {fmtMs(s.duration_ms)} · {s.prompt_tokens} → {s.completion_tokens} tokens
                </span>
              </>
            ) : (
              <>
                <strong>{s.name}</strong>
                <span className="tsteps__meta">
                  {fmtMs(s.duration_ms)} · {s.ok ? "ok" : "échec"}
                </span>
                {s.args && Object.keys(typeof s.args === "object" ? s.args : { x: 1 }).length > 0 && (
                  <code className="tsteps__code">{typeof s.args === "string" ? s.args : JSON.stringify(s.args)}</code>
                )}
                <code className="tsteps__code tsteps__code--result">{s.result}</code>
              </>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
