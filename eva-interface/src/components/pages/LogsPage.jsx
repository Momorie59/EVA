import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";

const GENRES = [
  ["", "Tout"], ["outil", "🔧 Outils"], ["erreur", "⚠️ Erreurs"], ["apprentissage", "🎓 Apprentissage"], ["evolution", "🧬 Évolution"],
  ["tache", "⏳ Tâches en fond"], ["routine", "🔁 Routines"], ["satellite", "🎙 Satellites"], ["systeme", "⚙️ Système"],
];
const ICONE = Object.fromEntries(GENRES.filter(([k]) => k).map(([k, l]) => [k, l.split(" ")[0]]));

// Journal d'activité : tout ce qu'EVA a fait (outils pendant les conversations, et ce qu'elle fait seule).
export default function LogsPage({ messages = [] }) {
  const [lignes, setLignes] = useState(null); const [genre, setGenre] = useState(""); const [err, setErr] = useState("");
  const charger = useCallback(() => api(`/api/journal?limite=300&genre=${genre}`).then((d) => { setLignes(d.lignes); setErr(""); })
    .catch((e) => setErr(e.status === 404 ? "Le journal arrive avec la prochaine reconstruction d'eva-core." : e.message)), [genre]);
  useEffect(() => { charger(); const t = setInterval(charger, 15000); return () => clearInterval(t); }, [charger]);
  const confirmations = messages.filter((m) => m.from === "confirm");
  const quand = (ts) => new Date(ts).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
  return (
    <section className="page" data-testid="logs-page">
      <header className="page__header">
        <h1>Journal</h1>
        <span className="page__sub">Tout ce qu'EVA a fait : outils utilisés dans les conversations, et ce qu'elle fait seule (apprentissage, évolution, tâches, routines, satellites).</span>
      </header>
      <div className="page__body">
        <div className="pj-sbx__tabs" data-testid="logs-filtres">
          {GENRES.map(([k, l]) => <button key={k} className={genre === k ? "is-on" : ""} onClick={() => setGenre(k)}>{l}</button>)}
          <button className="btn btn--ghost" onClick={charger}>↻</button>
        </div>
        {err && <p className="page__warn">{err}</p>}
        {confirmations.length > 0 && (
          <ul className="loglist">
            {confirmations.map((m) => (
              <li key={m.id} className="is-confirm">
                <span className="loglist__kind">CONFIRMATION</span><span className="loglist__text">{m.text}</span>
                {m.resolved && <em>{m.approved ? (m.always ? "autorisé en permanence" : "autorisé") : "refusé"}</em>}
              </li>
            ))}
          </ul>
        )}
        {lignes === null ? <p className="page__sub">Chargement…</p> : lignes.length === 0 ? (
          <p className="dash-empty">Rien pour l'instant. Demande quelque chose à EVA : chaque outil qu'elle utilise apparaîtra ici.</p>
        ) : (
          <ul className="loglist" data-testid="logs-lignes">
            {lignes.map((l, i) => (
              <li key={i} className={l.genre === "erreur" ? "is-confirm" : ""}>
                <span className="loglist__kind">{ICONE[l.genre] || "•"} {quand(l.ts)}</span>
                <span className="loglist__text">{l.texte}{l.qui && !["chat", "agent"].includes(l.qui) ? ` · ${l.qui}` : l.qui === "agent" ? " · agent" : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
