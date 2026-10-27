import { useEffect, useState } from "react";
import { api } from "../api";

// Agendas iCal de la personne connectée : EVA les lit pour répondre « qu'est-ce que j'ai cette semaine ? » et dans le briefing.
export default function AgendasCard() {
  const [lst, setLst] = useState(null); const [f, setF] = useState({ nom: "", url: "" }); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const load = () => api("/api/agendas").then((d) => setLst(d.agendas)).catch((e) => setError(e.status === 404 ? "Pas encore disponible : eva-core n'a pas été reconstruit." : e.message));
  useEffect(() => { load(); }, []);
  const ajouter = async (e) => {
    e.preventDefault(); setError(""); setBusy(true);
    try { const d = await api("/api/agendas", { method: "POST", body: JSON.stringify(f) }); setLst(d.agendas); setF({ nom: "", url: "" }); } catch (x) { setError(x.message); }
    setBusy(false);
  };
  return (
    <div className="card routercard" data-testid="agendas-card">
      <span className="card__label">📅 Mes agendas (iCal)</span>
      <p className="page__sub">Colle le lien d'abonnement d'un agenda (.ics ou webcal://) : vacances scolaires, agenda Outlook ou iCloud partagé, club, école… EVA le lit (sans rien y changer) pour « qu'est-ce que j'ai cette semaine ? » et ton briefing du matin. Ces agendas ne sont visibles que par toi.</p>
      {lst?.map((a) => (
        <div className="pj-row" key={a.url}><span>📅 <b>{a.nom}</b> <span className="page__sub">{a.url.replace(/^https?:\/\//, "").slice(0, 60)}</span></span>
          <button className="btn btn--ghost" onClick={() => api("/api/agendas/retirer", { method: "POST", body: JSON.stringify({ url: a.url }) }).then((d) => setLst(d.agendas))}>Retirer</button></div>
      ))}
      <form className="routergrid" onSubmit={ajouter}>
        <label className="field"><span>Nom</span><input value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} placeholder="Vacances scolaires" /></label>
        <label className="field"><span>Lien de l'agenda</span><input value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://… .ics" data-testid="agenda-url" /></label>
        <div className="agentform__actions"><button className="btn btn--primary" disabled={!f.url.trim() || busy}>{busy ? "Vérification…" : "Ajouter"}</button></div>
      </form>
      {error && <p className="page__warn">{error}</p>}
    </div>
  );
}
