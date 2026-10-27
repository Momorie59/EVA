import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import ModelSelect from "../ModelSelect";
import { confirmer } from "../../confirmer";

const STATUS = {
  pending: ["En attente", "pending"],
  applied: ["Appliquée", "ok"],
  rejected: ["Refusée", "off"],
  reverted: ["Annulée", "off"],
  failed_checks: ["Contrôles échoués", "error"],
};

function Diff({ text }) {
  return (
    <pre className="evo-diff">
      {text.split("\n").map((l, i) => (
        <span key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "is-add" : l.startsWith("-") && !l.startsWith("---") ? "is-del" : l.startsWith("@@") ? "is-hunk" : ""}>{l + "\n"}</span>
      ))}
    </pre>
  );
}

function Proposal({ p, onChange, busy, setBusy, setError }) {
  const [open, setOpen] = useState(p.status === "pending");
  const [detail, setDetail] = useState(null);
  useEffect(() => {
    if (open && !detail) api(`/api/self/proposals/${p.id}`).then(setDetail).catch((e) => setError(e.message));
  }, [open, detail, p.id, setError]);
  const [label, tone] = STATUS[p.status] || [p.status, "off"];

  async function act(kind, confirmText) {
    if (confirmText && !(await confirmer(confirmText))) return;
    setBusy(true); setError("");
    try {
      const r = await api(`/api/self/proposals/${p.id}/${kind}`, { method: "POST" });
      onChange(r.restarting);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <div className="card acard">
      <div className="acard__head">
        <span className={`acard__status acard__status--${tone}`} title={label} />
        <div className="acard__title"><strong>#{p.id} · {p.title}</strong><span className="skilltag">{label}</span></div>
        <div className="acard__actions">
          {p.status === "pending" && <>
            <button className="btn btn--primary" disabled={busy} onClick={() => act("apply", `Appliquer « ${p.title} » ? EVA redémarrera quelques secondes.`)}>Appliquer</button>
            <button className="btn" disabled={busy} onClick={() => act("reject")}>Refuser</button>
          </>}
          {p.status === "failed_checks" && <button className="btn" disabled={busy} onClick={() => act("reject")}>Écarter</button>}
          {p.status === "applied" && <button className="btn btn--danger" disabled={busy} onClick={() => act("revert", `Annuler « ${p.title} » ? EVA redémarrera quelques secondes.`)}>Annuler</button>}
          <button className="btn" onClick={() => setOpen((v) => !v)}>{open ? "Masquer" : "Détails"}</button>
        </div>
      </div>
      <p className="acard__instruction">{p.rationale || "(aucune justification)"}</p>
      <div className="acard__meta"><span>{p.files.join(", ")}</span>{p.commit_sha && <span>commit {p.commit_sha}</span>}</div>
      {open && (
        <>
          <p className={p.checks.ok ? "page__sub" : "page__warn"}>
            Contrôles automatiques : {p.checks.ok ? "syntaxe et import corrects" : `${p.checks.stage} — ${p.checks.output}`}
          </p>
          {detail ? <Diff text={detail.diff} /> : <p className="dash-loading">Chargement…</p>}
        </>
      )}
    </div>
  );
}

const STATUTS = { a_faire: "à faire", faite: "faite ✓", refusee: "écartée" };

// Ce qu'on a demandé à EVA et qu'elle ne sait pas encore faire : elle le note toute seule (outil evolution_demander).
function Demandes() {
  const [lst, setLst] = useState(null);
  const [err, setErr] = useState("");
  const charger = useCallback(() => api("/api/self/demandes").then((d) => setLst(d.demandes)).catch((e) => setErr(e.message)), []);
  useEffect(() => { charger(); }, [charger]);
  async function statut(id, s) {
    try { setLst((await api(`/api/self/demandes/${id}`, { method: "PATCH", body: JSON.stringify({ statut: s }) })).demandes); } catch (e) { setErr(e.message); }
  }
  if (!lst) return null;
  const aFaire = lst.filter((d) => d.statut === "a_faire").length;
  return (
    <div className="card" data-testid="demandes-evolution">
      <span className="card__label">Demandes d'évolution ({aFaire} à faire)</span>
      <p className="page__sub">Quand tu demandes quelque chose qu'EVA ne sait pas encore faire, elle le note ici au lieu de s'arrêter à « je ne peux pas ». Transmets la liste pour la prochaine mise à jour.</p>
      {lst.length === 0 ? <p className="dash-empty">Rien pour l'instant.</p> : (
        <ul className="pj-trash__list">
          {lst.map((d) => (
            <li key={d.id} className={d.statut !== "a_faire" ? "is-off" : ""}>
              <span><b>{d.texte}</b>{d.fois > 1 && <small> · demandée {d.fois} fois</small>}
                <small className="page__sub" style={{ display: "block" }}>{d.exemple ? `« ${d.exemple} » · ` : ""}{d.qui || "toi"} · {new Date(d.cree * 1000).toLocaleDateString("fr-FR")} · {STATUTS[d.statut]}</small></span>
              <span>
                {d.statut === "a_faire" ? <><button className="btn btn--ghost" onClick={() => statut(d.id, "faite")}>Faite</button> <button className="btn btn--ghost" onClick={() => statut(d.id, "refusee")}>Écarter</button></>
                  : <button className="btn btn--ghost" onClick={() => statut(d.id, "a_faire")}>Rouvrir</button>}
                {" "}<button className="btn btn--ghost" onClick={() => statut(d.id, "supprimer")} aria-label="Supprimer">✕</button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}


const VERDICTS = { ok: ["✅", "bon outil"], mauvais_outil: ["❌", "mauvais outil"], aucun_outil: ["⚪", "n'a utilisé aucun outil"],
  pas_propose: ["🧩", "outil pas proposé par EVA (à corriger côté EVA)"], erreur: ["⚠️", "erreur"] };

// Banc d'essai : des phrases types envoyées au vrai modèle, on regarde l'outil qu'il choisit (rien n'est exécuté).
function BancEssai() {
  const [res, setRes] = useState(null);
  const [modeles, setModeles] = useState([]);
  const [modele, setModele] = useState("");
  const [ouvert, setOuvert] = useState("");
  const [err, setErr] = useState("");
  const charger = useCallback(() => api("/api/self/banc").then(setRes).catch((e) => setErr(e.message)), []);
  useEffect(() => { charger(); api("/api/models").then((d) => setModeles((d.installed || []).filter((m) => !m.embedding))).catch(() => {}); }, [charger]);
  const enCours = res?.etat?.en_cours;
  useEffect(() => { if (!enCours) return undefined; const t = setInterval(charger, 3000); return () => clearInterval(t); }, [enCours, charger]);
  async function lancer() {
    setErr("");
    try { await api("/api/self/banc", { method: "POST", body: JSON.stringify({ modele }) }); charger(); } catch (e) { setErr(e.message); }
  }
  if (!res) return null;
  return (
    <div className="card" data-testid="banc-essai">
      <span className="card__label">Banc d'essai des outils</span>
      <p className="page__sub">{res.cas} phrases types (« allume le salon », « rappelle-moi dans 10 minutes », « remplace les moules »…) sont envoyées au modèle choisi avec les outils qu'EVA lui proposerait. On regarde quel outil il prend — <b>rien n'est exécuté</b>. Compte quelques minutes avec ton serveur IA.</p>
      <div className="pj-row">
        <ModelSelect value={modele} onChange={setModele} modeles={modeles} vide="Modèle du choix automatique" aria-label="Modèle à tester" />
        <button className="btn btn--primary" onClick={lancer} disabled={enCours} data-testid="banc-lancer">{enCours ? `En cours… ${res.etat.fait}/${res.etat.total}` : "Lancer le banc d'essai"}</button>
      </div>
      {res.passages.length > 0 && (
        <ul className="pj-trash__list">
          {res.passages.map((p) => (
            <li key={p.modele} style={{ display: "block" }}>
              <button className="btn btn--ghost" onClick={() => setOuvert(ouvert === p.modele ? "" : p.modele)} aria-expanded={ouvert === p.modele}>
                {ouvert === p.modele ? "▾" : "▸"} <b>{p.modele}</b> : {p.score}/{p.total} ({Math.round((100 * p.score) / Math.max(1, p.total))} %) · {p.duree_moyenne_s} s par phrase
                {p.pas_proposes > 0 && <small> · 🧩 {p.pas_proposes} à corriger côté EVA</small>} · <small>{new Date(p.date * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</small>
              </button>
              {ouvert === p.modele && (
                <table className="banc__table">
                  <thead><tr><th /><th>Phrase</th><th>Attendu</th><th>Choisi</th></tr></thead>
                  <tbody>
                    {p.lignes.map((l) => (
                      <tr key={l.phrase} className={l.verdict === "ok" ? "" : "is-ko"}>
                        <td title={VERDICTS[l.verdict]?.[1]}>{VERDICTS[l.verdict]?.[0]}</td>
                        <td>{l.phrase}</td>
                        <td><code>{l.attendus.join(" / ")}</code></td>
                        <td><code>{l.choisi}</code>{l.erreur && <small> {l.erreur}</small>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="page__sub">✅ bon outil · ❌ mauvais outil · ⚪ aucun outil (le modèle a répondu en texte) · 🧩 EVA ne lui a pas proposé le bon outil</p>
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}

export default function EvolutionPage() {
  const [status, setStatus] = useState(null);
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const refresh = useCallback(() => {
    api("/api/self/status").then(setStatus).catch((e) => setError(e.message));
    api("/api/self/proposals").then((d) => setList(d.proposals)).catch(() => setList([]));
  }, []);
  useEffect(refresh, [refresh]);

  function afterChange(restart) {
    if (!restart) { setBusy(false); refresh(); return; }
    setRestarting(true);
    let tries = 0;
    const poll = setInterval(async () => {
      tries += 1;
      try {
        await api("/api/health");
        if (tries > 2) { clearInterval(poll); setRestarting(false); setBusy(false); refresh(); }
      } catch { /* EVA redémarre : on réessaie */ }
      if (tries > 60) { clearInterval(poll); setRestarting(false); setBusy(false); setError("EVA met longtemps à redémarrer : vérifie les logs du conteneur."); }
    }, 2000);
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1>Évolution</h1>
        <span className="page__sub">EVA peut proposer des modifications de son propre code — rien ne s'applique sans ton accord</span>
      </header>
      <div className="page__body">
        {restarting && <p className="page__warn">EVA redémarre avec le nouveau code… la page se rafraîchit toute seule.</p>}
        <Demandes />
        <BancEssai />
        {error && <p className="page__warn">{error}</p>}
        {status && !status.enabled && (
          <div className="card">
            <span className="card__label">Non activée</span>
            <p className="page__sub">Le volume de code d'EVA n'est pas monté. Il est prévu dans docker-compose.yml (volume « eva-self ») : reconstruis eva-core avec ce fichier à jour. Tant que ce n'est pas fait, EVA ne peut rien proposer.</p>
          </div>
        )}
        {status?.enabled && (
          <div className="card srcstats">
            <span className="card__label">État du code</span>
            <div className="srcstats__grid">
              <div><strong>{status.running_from === "live" ? "copie modifiable" : "code de l'image"}</strong><span>code en cours d'exécution</span></div>
              <div><strong>{status.head || "—"}</strong><span>dernière version</span></div>
            </div>
            {status.boot_error && <p className="page__warn">La copie modifiée ne démarrait plus : EVA a relancé le code d'origine. Erreur : {status.boot_error.error}</p>}
            {status.obsolete && <p className="page__sub">Une mise à jour d'EVA a remplacé le code de base : tes anciennes modifications sont archivées ({status.obsolete.archived}) et à redemander si besoin.</p>}
            <p className="page__sub">Garde-fous : contrôle syntaxe + import avant application, retour automatique au code d'origine si ça ne démarre pas, annulation en un clic, et {status.protected.length} fichiers protégés (permissions, authentification, ce mécanisme). Seule l'interface serveur est concernée ; l'interface web ne se modifie pas ici.</p>
          </div>
        )}
        {list && list.length === 0 && status?.enabled && (
          <p className="dash-empty">Aucune proposition. Demande à EVA par exemple : « lis ton fichier app/skills.py et propose une amélioration ».</p>
        )}
        {(list || []).map((p) => <Proposal key={p.id} p={p} onChange={afterChange} busy={busy} setBusy={setBusy} setError={setError} />)}
      </div>
    </section>
  );
}
