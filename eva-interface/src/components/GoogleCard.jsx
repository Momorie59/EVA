import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

export default function GoogleCard() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [cid, setCid] = useState("");
  const [secret, setSecret] = useState("");
  const [link, setLink] = useState("");
  const [pasted, setPasted] = useState("");

  const load = () => api("/api/google/status").then(setSt).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function run(fn, ok) {
    setError(""); setMsg("");
    try { await fn(); if (ok) setMsg(ok); await load(); } catch (e) { setError(e.message); }
  }

  if (!st) return <div className="card"><span className="card__label">Google</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;

  return (
    <div className="card routercard">
      <span className="card__label">Google (Gmail et Agenda)</span>
      {st.connected ? (
        <>
          <p className="page__sub">Connecté en tant que <strong>{st.email || "compte Google"}</strong>. EVA peut lire tes e-mails et ton agenda ; envoyer un e-mail ou créer un événement demande toujours ton accord.</p>
          <div className="agentform__actions">
            <button className="btn btn--danger" onClick={() => confirmer("Déconnecter Google ?").then((ok) => ok && (run(() => api("/api/google", { method: "DELETE" }), "Google déconnecté.")))}>Déconnecter</button>
          </div>
        </>
      ) : (
        <>
          <details className="googlehelp">
            <summary>Comment obtenir les identifiants (une seule fois)</summary>
            <ol>
              <li>Sur <strong>console.cloud.google.com</strong> : crée un projet, puis « API et services » → active les API <em>Gmail</em> et <em>Google Agenda</em>.</li>
              <li>« Écran de consentement OAuth » : type Externe, ajoute ton adresse Gmail comme utilisateur test.</li>
              <li>« Identifiants » → Créer → ID client OAuth → type <strong>Application de bureau</strong>.</li>
              <li>Copie l'identifiant client et le secret ci-dessous.</li>
            </ol>
          </details>
          <div className="routergrid">
            <label className="field"><span>Identifiant client</span><input value={cid} onChange={(e) => setCid(e.target.value)} placeholder={st.client_id_hint || "xxxx.apps.googleusercontent.com"} /></label>
            <label className="field"><span>Secret client</span><input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={st.has_client ? "(déjà enregistré)" : ""} /></label>
          </div>
          <div className="agentform__actions">
            <button className="btn" disabled={!cid || !secret} onClick={() => run(() => api("/api/google/client", { method: "PUT", body: JSON.stringify({ client_id: cid, client_secret: secret }) }).then(() => { setSecret(""); }), "Identifiants enregistrés.")}>Enregistrer</button>
            <button className="btn btn--primary" disabled={!st.has_client} onClick={() => run(async () => { const r = await api("/api/google/auth-url"); setLink(r.url); })}>Générer le lien d'autorisation</button>
          </div>
          {link && (
            <>
              <p className="page__sub">1) Ouvre ce lien sur ton PC et autorise l'accès :</p>
              <a className="googlelink" href={link} target="_blank" rel="noreferrer">Ouvrir la page d'autorisation Google</a>
              <p className="page__sub">2) Google te redirige vers une page qui ne s'affiche pas (<code>{st.redirect_uri}…</code>) : c'est normal. Copie l'adresse complète de la barre d'adresse et colle-la ici :</p>
              <div className="schedrow">
                <input className="skillinstall__input" value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder="http://127.0.0.1:8765/?state=…&code=…" />
                <button className="btn btn--primary" disabled={!pasted.trim()} onClick={() => run(async () => { await api("/api/google/complete", { method: "POST", body: JSON.stringify({ url: pasted }) }); setLink(""); setPasted(""); }, "Google connecté.")}>Terminer</button>
              </div>
            </>
          )}
        </>
      )}
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
