import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

// Connexion à GitHub : jeton, mes dépôts, copies de travail (état, historique, commit, récupérer, envoyer).
export default function GitHubCard() {
  const [st, setSt] = useState(null);
  const [jeton, setJeton] = useState("");
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [depots, setDepots] = useState([]);
  const [vue, setVue] = useState(null);                 // {nom, titre, texte}
  const [message, setMessage] = useState({});
  const [pushNom, setPushNom] = useState("");           // dépôt en attente de confirmation d'envoi
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const s = await api("/api/github"); setSt(s); setError("");
      if (s.connecte) setDepots((await api("/api/github/depots")).depots);
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function act(cle, fn, ok) {
    setBusy(cle); setError(""); setInfo("");
    try { const r = await fn(); if (ok) setInfo(typeof ok === "function" ? ok(r) : ok); await load(); return r; } catch (e) { setError(e.message); return null; } finally { setBusy(""); }
  }
  const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b || {}) });

  const connecter = (e) => { e.preventDefault(); act("jeton", () => api("/api/github/token", { method: "PUT", body: JSON.stringify({ token: jeton.trim() }) }), (r) => `Connecté en tant que ${r.login}.`).then((r) => r && setJeton("")); };
  const listerRepos = () => act("repos", async () => { const r = await api("/api/github/repos"); setRepos(r.repos); if (r.repos[0]) setRepo(r.repos[0].nom); });
  const voir = (nom, chemin, titre, fmt) => act(`${chemin}${nom}`, async () => { const r = await api(`/api/github/depots/${encodeURIComponent(nom)}/${chemin}`); setVue({ nom, titre, texte: fmt(r) }); });
  const envoyer = (nom, toujours) => { setPushNom(""); act(`push${nom}`, () => post(`/api/github/depots/${encodeURIComponent(nom)}/envoyer`, { confirme: true, toujours }), "Envoyé vers GitHub."); };

  if (!st) return <div className="card routercard"><span className="card__label">GitHub</span>{error && <p className="page__warn">{error}</p>}</div>;
  return (
    <div className="card routercard" data-testid="github-card">
      <span className="card__label">GitHub</span>
      {error && <p className="page__warn" role="alert" data-testid="github-error">{error}</p>}
      {info && <p className="page__sub" data-testid="github-info">{info}</p>}
      {!st.connecte ? (
        <form className="agentform" onSubmit={connecter}>
          <p className="page__sub">Colle un jeton d'accès personnel : sur github.com › Settings › Developer settings › Personal access tokens › « Fine-grained tokens », limite-le aux dépôts voulus avec « Contents : lecture et écriture ». Le jeton reste sur ton NAS et n'est jamais réaffiché.</p>
          <input type="password" value={jeton} onChange={(e) => setJeton(e.target.value)} placeholder="github_pat_… ou ghp_…" autoComplete="off" data-testid="github-token" />
          <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!jeton.trim() || busy === "jeton"} data-testid="github-connect">Connecter</button></div>
        </form>
      ) : (
        <>
          <div className="schedrow">
            <span style={{ flex: 1 }}>✅ Connecté en tant que <strong>{st.login}</strong></span>
            {st.push_auto && <small className="card__hint">envoi automatique autorisé</small>}
            <button className="btn btn--ghost" onClick={() => act("deco", () => api("/api/github/token", { method: "DELETE" }), "Déconnecté.")}>Déconnecter</button>
          </div>
          <div className="schedrow">
            <button className="btn" onClick={listerRepos} disabled={busy === "repos"}>Mes dépôts</button>
            {repos.length > 0 && (
              <>
                <select value={repo} onChange={(e) => setRepo(e.target.value)} style={{ flex: 1 }} data-testid="github-repos">
                  {repos.map((r) => <option key={r.nom} value={r.nom}>{r.nom}{r.prive ? " 🔒" : ""}</option>)}
                </select>
                <button className="btn btn--primary" onClick={() => act("clone", () => post("/api/github/depots", { repo }), (r) => `« ${r.nom} » cloné dans le dossier depots.`)} disabled={!repo || busy === "clone"}>Cloner</button>
              </>
            )}
          </div>
          {depots.length === 0 && <p className="card__hint">Aucun dépôt cloné. EVA peut aussi les lire et les modifier : dossier « depots ».</p>}
          {depots.map((d) => (
            <div key={d.nom} className="card" data-testid="github-depot">
              <div className="schedrow">
                <strong style={{ flex: 1 }}>{d.nom} <small className="card__hint">({d.branche}{d.modifies ? `, ${d.modifies} modifié(s)` : ", à jour"})</small></strong>
                <button className="btn btn--ghost" aria-label="Retirer la copie" title="Retirer la copie locale (GitHub n'est pas touché)" onClick={() => confirmer(`Retirer la copie locale de « ${d.nom} » ? (GitHub n'est pas touché)`).then((ok) => ok && (act("rm", () => api(`/api/github/depots/${encodeURIComponent(d.nom)}`, { method: "DELETE" }))))}>×</button>
              </div>
              <p className="card__hint">Dernier : {d.dernier || "—"}</p>
              <div className="schedrow">
                <button className="btn" onClick={() => voir(d.nom, "etat", "État", (r) => r.texte)}>État</button>
                <button className="btn" onClick={() => voir(d.nom, "historique", "Historique", (r) => r.commits.map((c) => `${c.id}  ${c.date}  ${c.auteur}  ${c.message}`).join("\n"))}>Historique</button>
                <button className="btn" onClick={() => voir(d.nom, "differences", "Différences", (r) => r.texte || "Aucune différence.")}>Différences</button>
                <button className="btn" onClick={() => act(`pull${d.nom}`, () => post(`/api/github/depots/${encodeURIComponent(d.nom)}/recuperer`), "Récupéré depuis GitHub.")} disabled={busy === `pull${d.nom}`}>Récupérer</button>
              </div>
              <form className="schedrow" onSubmit={(e) => { e.preventDefault(); act(`c${d.nom}`, () => post(`/api/github/depots/${encodeURIComponent(d.nom)}/commit`, { message: message[d.nom] || "" }), "Enregistré (commit).").then((r) => r && setMessage({ ...message, [d.nom]: "" })); }}>
                <input value={message[d.nom] || ""} onChange={(e) => setMessage({ ...message, [d.nom]: e.target.value })} placeholder="Message du commit" style={{ flex: 1 }} data-testid="github-message" />
                <button className="btn" type="submit" disabled={(message[d.nom] || "").trim().length < 3}>Enregistrer</button>
                {pushNom === d.nom ? (
                  <>
                    <button className="btn btn--primary" type="button" onClick={() => envoyer(d.nom, false)}>Envoyer cette fois</button>
                    <button className="btn btn--primary" type="button" onClick={() => envoyer(d.nom, true)} data-testid="github-push-always">Toujours envoyer</button>
                    <button className="btn btn--ghost" type="button" onClick={() => setPushNom("")}>Annuler</button>
                  </>
                ) : (
                  <button className="btn" type="button" data-testid="github-push" onClick={() => (st.push_auto ? envoyer(d.nom, false) : setPushNom(d.nom))}>Envoyer vers GitHub</button>
                )}
              </form>
              {vue?.nom === d.nom && (
                <div>
                  <strong>{vue.titre}</strong> <button className="btn btn--ghost" onClick={() => setVue(null)}>fermer</button>
                  <pre style={{ maxHeight: 240, overflow: "auto", whiteSpace: "pre-wrap" }} data-testid="github-vue">{vue.texte}</pre>
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
