import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const PROFILS = { user: "Adulte", teen: "Adolescent", child: "Enfant", guest: "Invité" };

// Quotas de messages : le serveur IA (une seule carte graphique) reste disponible pour toute la maison.
export default function QuotasCard() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const load = useCallback(() => api("/api/access/quotas").then((x) => { setD(x); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  if (!d) return <div className="card"><span className="card__label">Quotas</span>{error ? <p className="page__warn">{error}</p> : <p className="card__hint">Chargement…</p>}</div>;

  const num = (v) => Math.max(0, parseInt(v, 10) || 0);
  const setProfil = (p, k, v) => setD({ ...d, profils: { ...d.profils, [p]: { ...d.profils[p], [k]: num(v) } } });
  const setPersonne = (n, k, v) => {
    const cur = { ...(d.personnes[n] || {}) };
    if (v === "") delete cur[k]; else cur[k] = num(v);
    setD({ ...d, personnes: { ...d.personnes, [n]: cur } });
  };
  const save = async () => {
    setError(""); setMsg("");
    try { await api("/api/access/quotas", { method: "PUT", body: JSON.stringify({ profils: d.profils, personnes: d.personnes }) }); setMsg("Quotas enregistrés."); await load(); }
    catch (e) { setError(e.message); }
  };
  const gens = Object.keys(d.usage || {});

  return (
    <div className="card routercard" data-testid="quotas-card">
      <span className="card__label">Quotas de messages</span>
      <p className="card__hint">Nombre maximal de messages par heure et par jour, pour que le serveur IA reste disponible pour tout le monde. 0 = illimité. L'administrateur n'a jamais de limite.</p>
      <b>Par profil</b>
      {Object.entries(PROFILS).map(([p, lab]) => (
        <div key={p} className="schedrow">
          <span style={{ minWidth: "7rem" }}>{lab}</span>
          <label>par heure <input type="number" min="0" value={d.profils[p]?.heure ?? 0} onChange={(e) => setProfil(p, "heure", e.target.value)} style={{ width: "5rem" }} data-testid={`q-${p}-heure`} /></label>
          <label>par jour <input type="number" min="0" value={d.profils[p]?.jour ?? 0} onChange={(e) => setProfil(p, "jour", e.target.value)} style={{ width: "5rem" }} /></label>
        </div>
      ))}
      <b>Par personne</b> <small className="card__hint">(vide = la valeur de son profil)</small>
      {gens.length === 0 && <p className="card__hint">Aucun compte non administrateur.</p>}
      {gens.map((n) => (
        <div key={n} className="schedrow">
          <span style={{ minWidth: "7rem" }}>{n}</span>
          <label>par heure <input type="number" min="0" value={d.personnes[n]?.heure ?? ""} onChange={(e) => setPersonne(n, "heure", e.target.value)} style={{ width: "5rem" }} /></label>
          <label>par jour <input type="number" min="0" value={d.personnes[n]?.jour ?? ""} onChange={(e) => setPersonne(n, "jour", e.target.value)} style={{ width: "5rem" }} /></label>
          <small className="card__hint">utilisé : {d.usage[n].heure} cette heure, {d.usage[n].jour} aujourd'hui</small>
        </div>
      ))}
      <button className="btn btn--primary" onClick={save} data-testid="quotas-save">Enregistrer</button>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
