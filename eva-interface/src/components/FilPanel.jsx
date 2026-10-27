import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

// En-tête de conversation : projet de rattachement et fil conducteur (résumé des échanges anciens, que l'on peut corriger).
export default function FilPanel({ sessionId }) {
  const [projets, setProjets] = useState([]);
  const [fil, setFil] = useState(null);
  const [ouvert, setOuvert] = useState(false);
  const [brouillon, setBrouillon] = useState(null);
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState("");
  const base = `/api/sessions/${encodeURIComponent(sessionId)}`;
  const charger = useCallback(() => api(`${base}/fil`).then(setFil).catch(() => setFil(null)), [base]);
  useEffect(() => { api("/api/projects").then((d) => setProjets(d.projects || [])).catch(() => setProjets([])); }, []);
  useEffect(() => { setBrouillon(null); setErreur(""); charger(); }, [charger]);

  const agir = async (fn) => { setOccupe(true); setErreur(""); try { await fn(); } catch (e) { setErreur(e.message); } setOccupe(false); };
  const rattacher = (slug) => agir(async () => { await api(base, { method: "PATCH", body: JSON.stringify({ project: slug }) }); await charger(); window.dispatchEvent(new Event("eva:sessions-changed")); });
  const compiler = () => agir(async () => { setFil(await api(`${base}/fil`, { method: "POST" })); setBrouillon(null); });
  const enregistrer = () => agir(async () => { setFil(await api(`${base}/fil`, { method: "PUT", body: JSON.stringify({ resume: brouillon }) })); setBrouillon(null); });

  return (
    <>
      {projets.length > 0 && (
        <select className="page__action modelpick" value={fil?.project || ""} onChange={(e) => rattacher(e.target.value)} disabled={occupe} title="Projet de cette conversation : EVA reçoit le fil du projet" data-testid="conv-projet">
          <option value="">Projet : aucun</option>
          {projets.map((p) => <option key={p.slug} value={p.slug}>📁 {p.name}</option>)}
        </select>
      )}
      <button className={`btn btn--ghost filbtn ${ouvert ? "is-on" : ""}`} onClick={() => setOuvert(!ouvert)} aria-expanded={ouvert} title="Fil conducteur : ce qu'EVA retient de la conversation sans tout relire" data-testid="fil-toggle">
        📌 Fil{fil?.resume ? "" : " (vide)"}
      </button>
      {ouvert && (
        <div className="filpanel" data-testid="fil-panel">
          <p className="card__hint">EVA ne relit pas toute la conversation à chaque message : elle reçoit ce fil conducteur et les derniers échanges. Le fil se met à jour tout seul ; tu peux le corriger ou le compiler maintenant.{fil?.en_attente ? ` ${fil.en_attente} message(s) pas encore dans le fil (envoyés tels quels).` : ""}</p>
          <textarea value={brouillon ?? (fil?.resume || "")} onChange={(e) => setBrouillon(e.target.value)} rows={7} maxLength={2400} placeholder="Le fil apparaît quand la conversation s'allonge, ou avec « Compiler maintenant »." data-testid="fil-texte" />
          <div className="schedrow">
            <button className="btn btn--primary" onClick={compiler} disabled={occupe} data-testid="fil-compiler">{occupe ? "…" : "Compiler maintenant"}</button>
            {brouillon !== null && brouillon !== (fil?.resume || "") && <button className="btn btn--ghost" onClick={enregistrer} disabled={occupe}>Enregistrer ma correction</button>}
            {fil?.maj && <small className="card__hint">Mis à jour le {new Date(fil.maj).toLocaleString("fr-FR")}</small>}
          </div>
          {erreur && <p className="page__warn" role="alert">{erreur}</p>}
        </div>
      )}
    </>
  );
}
