import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import PlanCard from "./PlanCard";
import MessageText from "./MessageText";

const ETATS = { en_attente: "⏳ en attente", en_cours: "⚙️ en cours", fini: "✅ terminée", erreur: "❌ échec", annule: "⛔ annulée" };
const heure = (s) => (s ? new Date(s * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "");

// Tâches confiées à EVA « en fond » : pastille dans l'en-tête de la conversation, liste détaillée au clic.
export default function TachesFond() {
  const [taches, setTaches] = useState([]);
  const [ouvert, setOuvert] = useState(false);
  const [detail, setDetail] = useState(null);
  const charger = useCallback(() => api("/api/taches-fond").then((d) => setTaches(d.taches || [])).catch(() => {}), []);
  const actives = taches.filter((t) => t.etat === "en_cours" || t.etat === "en_attente");
  useEffect(() => {
    charger();
    const i = setInterval(charger, actives.length || ouvert ? 5000 : 30000);
    window.addEventListener("eva-taches-fond", charger);
    return () => { clearInterval(i); window.removeEventListener("eva-taches-fond", charger); };
  }, [charger, actives.length, ouvert]);
  if (!taches.length) return null;
  return (
    <>
      <button type="button" className={`page__action fond-pastille ${actives.length ? "is-actif" : ""}`} onClick={() => setOuvert(!ouvert)} data-testid="fond-pastille">
        {actives.length ? `⚙️ ${actives.length} tâche${actives.length > 1 ? "s" : ""} en fond` : "Tâches en fond"}
      </button>
      {ouvert && (
        <div className="dash-overlay" role="dialog" aria-label="Tâches en fond" onClick={() => setOuvert(false)}>
          <div className="dash-panel fond-panneau" onClick={(e) => e.stopPropagation()}>
            <div className="dash-header"><b>Tâches en fond</b><button className="dash-close" onClick={() => setOuvert(false)} aria-label="Fermer">✕</button></div>
            <ul className="fond-liste">
              {taches.map((t) => (
                <li key={t.id}>
                  <div className="fond-ligne">
                    <button type="button" className="fond-titre" onClick={() => setDetail(detail === t.id ? null : t.id)}><b>{t.titre}</b></button>
                    <span>{ETATS[t.etat] || t.etat}</span>
                    <span className="page__sub">{heure(t.debut)}</span>
                    {(t.etat === "en_cours" || t.etat === "en_attente") && (
                      <button className="btn btn--ghost" onClick={() => api(`/api/taches-fond/${t.id}`, { method: "DELETE" }).then(charger)}>Annuler</button>
                    )}
                  </div>
                  {(detail === t.id || t.etat === "en_cours") && t.plan && <PlanCard plan={t.plan} />}
                  {detail === t.id && t.resultat && <div className="fond-resultat"><MessageText text={t.resultat} /></div>}
                </li>
              ))}
            </ul>
            <p className="page__sub">Demande à EVA « fais ça en fond » : elle travaille seule, sans poser de question, et le résultat arrive dans la conversation (et en notification). Ce qui demande ton accord n'est pas fait : elle te le signale.</p>
          </div>
        </div>
      )}
    </>
  );
}
