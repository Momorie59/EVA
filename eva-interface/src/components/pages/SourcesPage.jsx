import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";

export default function SourcesPage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);

  const refresh = useCallback(() => {
    api("/api/docs/status").then((d) => { setStatus(d); setError(""); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, status?.running ? 1500 : 15000);
    return () => clearInterval(id);
  }, [refresh, status?.running]);

  async function reindex() {
    setError("");
    try { await api("/api/docs/reindex", { method: "POST" }); refresh(); } catch (e) { setError(e.message); }
  }
  async function search(e) {
    e.preventDefault();
    setSearching(true); setError("");
    try {
      const d = await api(`/api/docs/search?q=${encodeURIComponent(q)}&k=8`);
      setResults(d.results);
    } catch (err) { setError(err.message); setResults(null); }
    finally { setSearching(false); }
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1>Sources</h1>
        <span className="page__sub">Documents et conversations indexés — la mémoire sémantique d'EVA</span>
        <button className="btn btn--primary page__action" onClick={reindex} disabled={status?.running}>
          {status?.running ? "Indexation…" : "Réindexer"}
        </button>
      </header>
      <div className="page__body">
        {error && <p className="page__warn">{error}</p>}
        {status?.last_error && <p className="page__warn">{status.last_error}</p>}
        {status && (
          <div className="card srcstats">
            <span className="card__label">État</span>
            <div className="srcstats__grid">
              <div><strong>{status.files}</strong><span>fichiers</span></div>
              <div><strong>{status.file_chunks}</strong><span>passages</span></div>
              <div><strong>{status.messages}</strong><span>messages</span></div>
              <div><strong>{status.embed_model}</strong><span>modèle d'embeddings</span></div>
            </div>
            <p className="page__sub">
              Dossiers : {status.roots.map((r) => `${r.name} (${r.path})`).join(", ")}. Mise à jour automatique toutes les 10 min.
            </p>
          </div>
        )}
        <form className="card skillinstall" onSubmit={search}>
          <span className="card__label">Rechercher par le sens</span>
          <div className="schedrow">
            <input className="skillinstall__input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ex : comment installer EVA sur le NAS ?" required />
            <button className="btn btn--primary" type="submit" disabled={searching || !q.trim()}>Chercher</button>
          </div>
        </form>
        {results && results.length === 0 && <p className="dash-empty">Aucun résultat. Lance une indexation ou vérifie le modèle d'embeddings.</p>}
        {(results || []).map((r, i) => (
          <div key={i} className="card acard">
            <div className="acard__head">
              <div className="acard__title"><strong>{r.source}</strong><span className="skilltag">{r.kind === "message" ? "conversation" : "fichier"}</span></div>
              <span className="srcscore">{Math.round(r.score * 100)} %</span>
            </div>
            <pre className="rundetail__output">{r.content}</pre>
          </div>
        ))}
      </div>
    </section>
  );
}
