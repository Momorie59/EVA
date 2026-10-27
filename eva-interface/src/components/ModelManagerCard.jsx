import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import HFCatalog from "./HFCatalog";
import { badges, decrire } from "../models/catalogue";
import { confirmer } from "../confirmer";

const SUGGESTED = [
  ["llama3.2:3b", "rapide, voix"],
  ["qwen2.5-coder:7b", "code"],
  ["llava", "vision (photos)"],
  ["nomic-embed-text", "recherche dans les documents"],
];

const pct = (p) => (p.total ? Math.min(100, Math.round((p.completed / p.total) * 100)) : 0);

// Modèles Ollama du serveur IA : voir, télécharger, supprimer — sans ouvrir de terminal.
export default function ModelManagerCard() {
  const [data, setData] = useState(null);
  const [pulls, setPulls] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const timer = useRef(null);

  const load = useCallback(() => api("/api/models").then(setData).catch((e) => setError(e.message)), []);
  const poll = useCallback(async () => {
    try {
      const { pulls: list } = await api("/api/models/pulls");
      setPulls(list);
      if (list.some((p) => !p.done)) timer.current = setTimeout(poll, 1500);
      else load();
    } catch { /* on réessaiera au prochain clic */ }
  }, [load]);
  useEffect(() => { load(); poll(); return () => clearTimeout(timer.current); }, [load, poll]);

  async function pull(n) {
    setError(""); setMsg("");
    try { await api("/api/models/pull", { method: "POST", body: JSON.stringify({ name: n }) }); setName(""); clearTimeout(timer.current); poll(); }
    catch (e) { setError(e.message); }
  }
  async function remove(n) {
    if (!(await confirmer(`Supprimer le modèle ${n} du serveur IA ?`))) return;
    setError(""); setMsg("");
    try { await api(`/api/models/${encodeURIComponent(n).replace(/%2F/g, "/")}`, { method: "DELETE" }); setMsg(`${n} supprimé.`); load(); }
    catch (e) { setError(e.message); }
  }

  const installed = data?.installed || [];
  const has = (n) => installed.some((m) => m.name === n || m.name.startsWith(`${n}:`));
  const hasVision = installed.some((m) => m.vision);
  const active = pulls.filter((p) => !p.done || p.error);

  return (
    <div className="card routercard">
      <span className="card__label">Modèles installés (serveur IA)</span>
      {data && !data.reachable && <p className="page__warn">Serveur IA injoignable.</p>}
      {data?.reachable && !hasVision && <p className="page__warn">Aucun modèle vision : l'envoi de photos ne fonctionnera pas. Télécharge « llava » ci-dessous.</p>}
      <ul className="mm" data-testid="model-list">
        {installed.filter((m) => !m.cloud && !m.slow).map((m) => {
          const d = decrire(m);
          return (
            <li key={m.name} className="mm__ligne">
              <span className="mm__nom"><b>{d.titre}</b>{d.variante && <em> {d.variante}</em>}<small>{m.name}</small></span>
              <span className="mm__taille">{m.size_gb ? `${String(m.size_gb).replace(".", ",")} Go` : ""}</span>
              <span className="mp__badges mm__badges">{m.embedding ? <i className="mp__badge">🔎 recherche dans les documents</i> : badges(d).map((b) => <i key={b.t} className={`mp__badge ${b.k ? `is-${b.k}` : ""}`} title={b.aide}>{b.t}</i>)}</span>
              <button className="btn btn--ghost" onClick={() => remove(m.name)} aria-label={`Supprimer ${m.name}`}>Supprimer</button>
            </li>
          );
        })}
      </ul>
      {active.map((p) => (
        <div key={p.name} className="modelpull" data-testid="model-pull">
          <span>{p.name} — {p.error ? <b className="page__warn">{p.error}</b> : `${p.status} ${pct(p)}%`}</span>
          {!p.error && <progress max="100" value={pct(p)} />}
        </div>
      ))}
      <form className="schedrow" onSubmit={(e) => { e.preventDefault(); if (name.trim()) pull(name.trim()); }}>
        <input className="skillinstall__input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Télécharger un modèle (ex. llama3.2:3b)" />
        <button className="btn btn--primary" type="submit" disabled={!name.trim()}>Télécharger</button>
      </form>
      <div className="agentform__actions">
        {SUGGESTED.filter(([n]) => !has(n)).map(([n, why]) => (
          <button key={n} className="btn" onClick={() => pull(n)} title={why}>+ {n}</button>
        ))}
      </div>
      <HFCatalog onPull={pull} />
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
      <p className="page__sub">Un modèle utilisé dans « Choix automatique » ne peut pas être supprimé. Le téléchargement continue même si tu quittes cette page.</p>
    </div>
  );
}
