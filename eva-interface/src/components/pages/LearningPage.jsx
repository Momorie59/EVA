import { useCallback, useEffect, useState } from "react";
import ModelSelect from "../ModelSelect";
import { api } from "../../api";
import { fmtMs } from "../TraceSteps";
import ChangesCard from "../ChangesCard";
import { confirmer } from "../../confirmer";

const pct = (x) => `${Math.round(x * 100)} %`;


const GENRES = { correction: "tu l'as corrigée", incapable: "« je ne peux pas »", erreur_outil: "un outil a échoué", pouce_bas: "👎" };
const STATUTS = { a_voir: "⏳ à étudier", lecon: "✅ leçon apprise", deja_bon: "👌 la réponse était bonne", manque: "🧩 fonction absente (demande d'évolution)",
  non_verifiee: "⚠️ leçon pas encore suivie par le modèle", erreur: "⚠️ non étudié", vu: "vu" };

// Apprentissage par les erreurs : EVA note ses ratés et en tire des leçons vérifiées, la nuit ou sur demande.
function LeconsCard() {
  const [d, setD] = useState(null); const [modeles, setModeles] = useState([]); const [err, setErr] = useState("");
  const charger = useCallback(() => api("/api/self/lecons").then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { charger(); api("/api/models").then((x) => setModeles((x.installed || []).filter((m) => !m.embedding))).catch(() => {}); }, [charger]);
  useEffect(() => { if (!d?.en_cours) return undefined; const t = setInterval(charger, 4000); return () => clearInterval(t); }, [d?.en_cours, charger]);
  const regler = (chg) => api("/api/self/lecons/reglages", { method: "PUT", body: JSON.stringify(chg) }).then(charger).catch((e) => setErr(e.message));
  const changer = (id, chg) => api(`/api/self/lecons/${id}`, { method: "PATCH", body: JSON.stringify(chg) }).then(setD).catch((e) => setErr(e.message));
  const apprendre = () => api("/api/self/lecons/apprendre", { method: "POST" }).then(() => setTimeout(charger, 800)).catch((e) => setErr(e.message));
  if (!d) return err ? <p className="page__warn">{err}</p> : null;
  const r = d.reglages;
  return (
    <div className="card" data-testid="lecons">
      <span className="card__label">Apprendre de ses erreurs</span>
      <p className="page__sub">EVA note ses ratés (tu la corriges, elle répond « je ne peux pas », un outil échoue, ou tu mets 👎). La nuit, elle cherche quel outil aurait dû servir, <b>vérifie</b> la leçon au banc d'essai (rien n'est exécuté) et ne la garde que si elle marche. Les leçons s'appliquent ensuite toutes seules aux demandes qui ressemblent. Une fonction qui manque devient une demande d'évolution.</p>
      <div className="routergrid">
        <label className="field"><span>Apprentissage</span>
          <select value={r.actif ? "1" : "0"} onChange={(e) => regler({ actif: e.target.value === "1" })} data-testid="lecons-actif">
            <option value="1">Activé (chaque nuit)</option><option value="0">Désactivé</option></select></label>
        <label className="field"><span>Heure de la passe</span>
          <select value={r.heure} onChange={(e) => regler({ heure: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{h} h</option>)}</select></label>
        <label className="field"><span>IA qui étudie les ratés</span>
          <ModelSelect value={r.modele} onChange={(v) => regler({ modele: v })} modeles={modeles} vide="Choix automatique (mon serveur IA)" /></label>
        <label className="field"><span>Corrections de son code</span>
          <select value={r.auto ? "auto" : r.code ? "1" : "0"} onChange={(e) => regler({ code: e.target.value !== "0", auto: e.target.value === "auto" })} data-testid="lecons-code">
            <option value="0">Non (seulement des leçons)</option>
            <option value="1">Les proposer dans Évolution (j'accepte ou je refuse)</option>
            <option value="auto">Évoluer toute seule (appliquées la nuit, annulées si ça marche moins bien)</option></select></label>
      </div>
      {r.auto && (
        <p className="page__sub" data-testid="lecons-auto">
          🤖 <b>Évolution automatique</b> : chaque nuit (entre {r.heure} h et {(r.heure + 3) % 24} h), EVA applique au plus une de ses propositions qui a passé les contrôles,
          compare son banc d'essai avant/après et <b>revient en arrière toute seule</b> si elle ne démarre plus ou répond moins bien.
          La sécurité, les permissions et ce mécanisme restent intouchables. Tout est visible et annulable dans <b>Évolution</b>.
          {!d.code_modifiable && <span className="page__warn" style={{ display: "block" }}>La copie modifiable du code n'est pas active sur ce serveur : rien ne peut être appliqué pour l'instant.</span>}
          {d.evolution?.verifier && <span style={{ display: "block" }}>⏳ Vérification en cours de « {d.evolution.titre} ».</span>}
          {d.evolution?.dernier && <span style={{ display: "block" }}>Dernière : « {d.evolution.dernier.titre} » — {{ gardee: "✅ gardée", annulee: "↩️ annulée", refusee: "⛔ refusée aux contrôles", annulation_impossible: "⚠️ annulation impossible" }[d.evolution.dernier.resultat] || d.evolution.dernier.resultat}{d.evolution.dernier.raison ? ` (${d.evolution.dernier.raison})` : ""}, le {new Date(d.evolution.dernier.le * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}.</span>}
        </p>
      )}
      <p className="page__sub">Conseil : une IA plus forte que le serveur local (IA du marché ou IA gratuites) étudie mieux les ratés et écrit de meilleures corrections ; les demandes concernées partent alors en ligne.</p>
      <div className="pj-row">
        <button className="btn btn--primary" onClick={apprendre} disabled={d.en_cours} data-testid="lecons-apprendre">{d.en_cours ? "Étude en cours…" : `Apprendre maintenant (${d.en_attente} raté${d.en_attente > 1 ? "s" : ""} à étudier)`}</button>
        {d.dernier && <span className="page__sub">Dernière passe : {new Date(d.dernier.le * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} — {d.dernier.etudies} étudié(s), {d.dernier.lecons} leçon(s), {d.dernier.manques} fonction(s) manquante(s)</span>}
      </div>
      <span className="card__label" style={{ marginTop: 12 }}>Leçons apprises ({d.lecons.length})</span>
      {d.lecons.length === 0 ? <p className="dash-empty">Aucune pour l'instant.</p> : (
        <ul className="pj-trash__list">{d.lecons.map((l) => (
          <li key={l.id} className={l.actif ? "" : "is-off"}>
            <span>« {l.exemple} » → <code>{l.outil}</code><small className="page__sub" style={{ display: "block" }}>{l.consigne} · appliquée {l.utilisee} fois · {GENRES[l.source] || l.source}</small></span>
            <span><button className="btn btn--ghost" onClick={() => changer(l.id, { actif: !l.actif })}>{l.actif ? "Désactiver" : "Activer"}</button>{" "}
              <button className="btn btn--ghost" onClick={() => confirmer("Oublier cette leçon ?").then((ok) => ok && (changer(l.id, { supprimer: true })))} aria-label="Supprimer">✕</button></span>
          </li>))}</ul>
      )}
      <details><summary className="page__sub">Ratés notés ({d.rates.length} derniers)</summary>
        <ul className="pj-trash__list">{d.rates.map((x) => (
          <li key={x.id}><span>« {x.phrase} » <small className="page__sub">· {GENRES[x.genre] || x.genre} · {STATUTS[x.statut] || x.statut}{x.resultat ? ` · ${x.resultat}` : ""}</small></span></li>))}</ul>
      </details>
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}

export default function LearningPage() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/api/learning?days=${days}`).then((d) => { setData(d); setError(""); }).catch((e) => setError(e.message));
  }, [days]);

  return (
    <section className="page">
      <header className="page__header">
        <h1>Apprentissage</h1>
        <span className="page__sub">Ce que tes avis et l'historique disent d'EVA — elle propose, tu décides</span>
        <select className="page__action" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>7 jours</option><option value={30}>30 jours</option><option value={90}>90 jours</option>
        </select>
      </header>
      <div className="page__body">
        <LeconsCard />
        <ChangesCard />
        {error && <p className="page__warn">Serveur injoignable ou trop ancien : {error}</p>}
        {data && (
          <>
            <div className="card srcstats">
              <span className="card__label">Avis donnés (👍 / 👎 sous les réponses d'EVA)</span>
              <div className="srcstats__grid">
                <div><strong>{data.feedback.up}</strong><span>👍 satisfait</span></div>
                <div><strong>{data.feedback.down}</strong><span>👎 insatisfait</span></div>
              </div>
              {data.feedback.up + data.feedback.down === 0 && (
                <p className="page__sub">Aucun avis pour l'instant. Utilise les pouces sous les réponses : plus tu en donnes, plus les suggestions deviennent utiles.</p>
              )}
            </div>

            <div className="card srcstats">
              <span className="card__label">Suggestions</span>
              {data.suggestions.length === 0
                ? <p className="page__sub">Rien à signaler pour l'instant.</p>
                : <ul className="learn-tips">{data.suggestions.map((t, i) => <li key={i}>{t}</li>)}</ul>}
            </div>

            <div className="card srcstats">
              <span className="card__label">Modèles</span>
              <table className="learn-table">
                <thead><tr><th>Modèle</th><th>Tours</th><th>Réussite</th><th>Durée moy.</th><th>👍</th><th>👎</th></tr></thead>
                <tbody>
                  {data.models.map((m) => (
                    <tr key={m.model}><td>{m.model || "—"}</td><td>{m.traces}</td><td>{pct(m.ok_rate)}</td><td>{fmtMs(m.avg_ms)}</td><td>{m.up}</td><td>{m.down}</td></tr>
                  ))}
                </tbody>
              </table>
              {data.models.length === 0 && <p className="dash-empty">Pas encore de données.</p>}
            </div>

            <div className="card srcstats">
              <span className="card__label">Outils</span>
              <table className="learn-table">
                <thead><tr><th>Outil</th><th>Appels</th><th>Échecs</th></tr></thead>
                <tbody>
                  {data.tools.map((t) => (
                    <tr key={t.tool} className={t.failure_rate >= 0.3 && t.calls >= 5 ? "is-bad" : ""}><td>{t.tool}</td><td>{t.calls}</td><td>{t.failures} ({pct(t.failure_rate)})</td></tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.skills.length > 0 && (
              <div className="card srcstats">
                <span className="card__label">Skills utilisés</span>
                <table className="learn-table">
                  <thead><tr><th>Skill</th><th>Utilisations</th><th>👍</th><th>👎</th></tr></thead>
                  <tbody>{data.skills.map((k) => <tr key={k.skill}><td>{k.skill}</td><td>{k.uses}</td><td>{k.up}</td><td>{k.down}</td></tr>)}</tbody>
                </table>
                <p className="page__sub">Page Skills → « Proposer une amélioration » pour réviser un skill à partir de son historique.</p>
              </div>
            )}

            {data.recent_negative.length > 0 && (
              <div className="card srcstats">
                <span className="card__label">Derniers avis négatifs</span>
                {data.recent_negative.map((n) => (
                  <div key={n.message_id} className="learn-neg">
                    <strong>{n.question || "(question inconnue)"}</strong>
                    <p>{n.reply}</p>
                    {n.comment && <em>« {n.comment} »</em>}
                    <span className="rundetail__meta">{n.model}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
