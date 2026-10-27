import { useEffect, useState } from "react";
import { api } from "../api";

// Villes d'EVA : la ville par défaut sert à la météo, au briefing du matin et aux questions sans lieu précis.
export default function CitiesCard() {
  const [d, setD] = useState(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const load = () => api("/api/cities").then(setD).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  async function save(def, list, done) {
    setError(""); setMsg("");
    try { setD(await api("/api/cities", { method: "PUT", body: JSON.stringify({ default: def, cities: list }) })); window.dispatchEvent(new Event("eva:cities")); if (done) setMsg(done); }
    catch (e) { setError(e.message); }
  }
  if (!d) return <div className="card"><span className="card__label">Villes</span>{error ? <p className="page__warn">{error}</p> : <p className="card__hint">Chargement…</p>}</div>;
  return (
    <div className="card routercard" data-testid="cities-card">
      <span className="card__label">Villes — météo et briefing</span>
      <p className="card__hint">Choisis la ville par défaut (⭐) et ajoute celles que tu veux suivre : elles apparaissent en choix rapide dans le Tableau de bord. Tu peux toujours demander « la météo à Palerme » dans la conversation.</p>
      <div className="aisrv__chips">
        {d.list.map((c) => (
          <span key={c} className={`chip ${c === d.default ? "chip--up" : ""}`} data-testid="city-chip">
            <button className="chip__btn" title="Définir par défaut" onClick={() => save(c, d.list, `${c} est maintenant la ville par défaut.`)}>{c === d.default ? "⭐" : "☆"}</button>
            {c}
            {c !== d.default && <button className="chip__btn" title="Retirer" aria-label={`Retirer ${c}`} onClick={() => save(d.default, d.list.filter((x) => x !== c))}>×</button>}
          </span>
        ))}
      </div>
      <form className="schedrow" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { save(d.default, [...d.list, name.trim()], `${name.trim()} ajoutée.`); setName(""); } }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ajouter une ville (ex. Palerme)" data-testid="city-input" />
        <button className="btn btn--primary" type="submit" disabled={!name.trim()} data-testid="city-add">Ajouter</button>
      </form>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
