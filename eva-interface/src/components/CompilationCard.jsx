import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

// Compilation automatique des conversations : chaque nuit, fils conducteurs à jour et faits durables retenus en mémoire.
export default function CompilationCard() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api("/api/compilation").then((x) => { setD(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!d?.en_cours?.actif) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [d?.en_cours?.actif, load]);
  const regler = (body) => api("/api/compilation", { method: "PUT", body: JSON.stringify(body) }).then(setD).catch((e) => setErr(e.message));
  const lancer = () => api("/api/compilation/lancer", { method: "POST" }).then(() => setTimeout(load, 500)).catch((e) => setErr(e.message));
  const b = d?.dernier;
  return (
    <div className="card" data-testid="compilation-card">
      <span className="card__label">Compilation des conversations</span>
      <p className="card__hint">Chaque nuit, quand personne ne parle à EVA, elle résume toutes les conversations (même courtes) dans leur fil conducteur et retient ce que chacun a dit de lui (page Mémoire). Au début d'une nouvelle conversation, elle reçoit le résumé de tes dernières conversations : elle sait où on en est sans tout relire.</p>
      {err && <p className="page__warn">{err}</p>}
      {d && (
        <>
          <div className="schedrow">
            <label className="access__f"><input type="checkbox" checked={d.actif} onChange={() => regler({ actif: !d.actif })} data-testid="compil-actif" />Chaque nuit à</label>
            <select value={d.heure} onChange={(e) => regler({ heure: Number(e.target.value) })} disabled={!d.actif} aria-label="Heure de la compilation">
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{h} h</option>)}
            </select>
            <button className="btn btn--primary" onClick={lancer} disabled={d.en_cours?.actif} data-testid="compil-lancer">{d.en_cours?.actif ? "Compilation en cours…" : "Compiler maintenant"}</button>
          </div>
          {d.en_cours?.actif && <p className="card__hint">Étape : {d.en_cours.etape} — {d.en_cours.faites}{d.en_cours.total ? ` / ${d.en_cours.total}` : ""}</p>}
          <ul className="access__legend">
            <li>{d.en_attente} conversation(s) avec des échanges pas encore résumés</li>
            {b && <li>Dernière compilation : {new Date(b.le).toLocaleString("fr-FR")} — {b.conversations} conversation(s), {b.souvenirs} souvenir(s) retenu(s){b.erreurs ? `, ${b.erreurs} erreur(s)` : ""} ({b.duree_s} s)</li>}
          </ul>
        </>
      )}
    </div>
  );
}
