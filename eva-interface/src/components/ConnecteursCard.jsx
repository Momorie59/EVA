import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

function useBloc(service, recharger) {
  const [error, setError] = useState(""); const [msg, setMsg] = useState("");
  const run = async (fn, ok) => { setError(""); setMsg(""); try { const r = await fn(); setMsg(typeof ok === "function" ? ok(r) : ok); await recharger(); return r; } catch (e) { setError(e.message); return null; } };
  const enregistrer = (body) => run(() => api(`/api/connecteurs/${service}`, { method: "PUT", body: JSON.stringify(body) }), "Enregistré.");
  const tester = (fmt) => run(() => api(`/api/connecteurs/${service}/tester`, { method: "POST" }), fmt);
  const oublier = () => confirmer("Déconnecter ce service ?").then((ok) => ok && (run(() => api(`/api/connecteurs/${service}`, { method: "DELETE" }), "Déconnecté.")));
  const Notice = () => <>{error && <p className="page__warn" role="alert">{error}</p>}{msg && <p className="page__sub">{msg}</p>}</>;
  return { enregistrer, tester, oublier, Notice };
}

function Obs({ st, load }) {
  const [f, setF] = useState({ hote: st.hote || "", port: st.port || 4455, password: "" });
  const b = useBloc("obs", load);
  return (
    <details className="googlehelp" data-testid="cx-obs">
      <summary>🎥 OBS Studio {st.configure ? "· relié" : ""}</summary>
      <p className="page__sub">Dans OBS : <b>Outils › Paramètres du serveur WebSocket</b> → coche « Activer », note le port (4455) et le mot de passe (« Afficher les infos de connexion »). EVA pourra lancer ou couper le live et l'enregistrement, changer de scène, sauver un replay — toujours après ton accord.</p>
      <div className="routergrid">
        <label className="field"><span>Adresse IP de l'ordinateur OBS</span><input value={f.hote} onChange={(e) => setF({ ...f, hote: e.target.value })} placeholder="192.168.1.30" /></label>
        <label className="field"><span>Port</span><input type="number" value={f.port} onChange={(e) => setF({ ...f, port: e.target.value })} /></label>
        <label className="field"><span>Mot de passe{st.password_enregistre ? " (laisser vide pour le garder)" : ""}</span><input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" /></label>
      </div>
      <div className="agentform__actions">
        <button className="btn btn--primary" disabled={!f.hote} onClick={() => b.enregistrer(f)}>Enregistrer</button>
        {st.configure && <button className="btn" onClick={() => b.tester((r) => `OBS répond : ${r.en_direct ? "🔴 en direct" : "pas de live"}, scène « ${r.scene} » (${r.scenes.length} scènes).`)}>Tester</button>}
        {st.configure && <button className="btn btn--danger" onClick={b.oublier}>Déconnecter</button>}
      </div>
      <b.Notice />
    </details>
  );
}

function Discord({ st, load }) {
  const [nom, setNom] = useState(""); const [url, setUrl] = useState("");
  const b = useBloc("discord", load);
  const salons = st.salons || {};
  return (
    <details className="googlehelp" data-testid="cx-discord">
      <summary>💬 Discord {Object.keys(salons).length ? `· ${Object.keys(salons).length} salon(s)` : ""}</summary>
      <p className="page__sub">Sur ton serveur Discord : <b>Paramètres du salon › Intégrations › Webhooks › Nouveau webhook › Copier l'URL</b>. Donne un nom au salon pour le désigner à EVA (« annonce le live sur Discord »). Les mentions @everyone sont désactivées.</p>
      {Object.entries(salons).map(([n, fin]) => (
        <div className="pj-row" key={n}><span># <b>{n}</b> <span className="page__sub">{fin}</span></span><button className="btn btn--ghost" onClick={() => b.enregistrer({ retirer: [n] })}>Retirer</button></div>
      ))}
      <div className="routergrid">
        <label className="field"><span>Nom du salon</span><input value={nom} onChange={(e) => setNom(e.target.value)} placeholder="annonces" /></label>
        <label className="field"><span>URL du webhook</span><input type="password" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://discord.com/api/webhooks/…" autoComplete="off" /></label>
      </div>
      <div className="agentform__actions"><button className="btn btn--primary" disabled={!nom.trim() || !url.trim()} onClick={async () => { if (await b.enregistrer({ salons: { [nom.trim()]: url.trim() } })) { setNom(""); setUrl(""); } }}>Ajouter le salon</button></div>
      <b.Notice />
    </details>
  );
}

function Instagram({ st, load }) {
  const [f, setF] = useState({ token: "", compte_id: st.compte_id || "" });
  const b = useBloc("instagram", load);
  return (
    <details className="googlehelp" data-testid="cx-instagram">
      <summary>📸 Instagram (statistiques) {st.configure ? "· relié" : ""}</summary>
      <p className="page__sub">Il faut un compte <b>professionnel ou créateur</b>. Sur developers.facebook.com : crée une appli, ajoute « Instagram » (connexion Instagram), génère un <b>jeton d'accès</b> pour ton compte et colle-le ici. Le jeton dure 60 jours. L'identifiant de compte n'est utile que pour un jeton « Facebook » (laisse vide sinon). EVA ne publie rien : elle lit les chiffres.</p>
      <div className="routergrid">
        <label className="field"><span>Jeton d'accès{st.token_enregistre ? " (laisser vide pour le garder)" : ""}</span><input type="password" value={f.token} onChange={(e) => setF({ ...f, token: e.target.value })} autoComplete="off" /></label>
        <label className="field"><span>ID du compte (facultatif)</span><input value={f.compte_id} onChange={(e) => setF({ ...f, compte_id: e.target.value })} /></label>
      </div>
      <div className="agentform__actions">
        <button className="btn btn--primary" disabled={!f.token && !st.token_enregistre} onClick={() => b.enregistrer(f)}>Enregistrer</button>
        {st.configure && <button className="btn" onClick={() => b.tester((r) => `Compte @${r.compte} : ${r.abonnes} abonnés.`)}>Tester</button>}
        {st.configure && <button className="btn btn--danger" onClick={b.oublier}>Déconnecter</button>}
      </div>
      <b.Notice />
    </details>
  );
}

function Twilio({ st, load }) {
  const [f, setF] = useState({ sid: st.sid || "", token: "", de: st.de || "", adresse_publique: st.adresse_publique || "" });
  const [contacts, setContacts] = useState(Object.entries(st.contacts || {}).map(([n, v]) => ({ n, v })));
  const b = useBloc("twilio", load);
  const corps = () => ({ ...f, contacts: Object.fromEntries(contacts.filter((c) => c.n.trim() && c.v.trim()).map((c) => [c.n.trim(), c.v.trim()])) });
  return (
    <details className="googlehelp" data-testid="cx-twilio">
      <summary>📞 Appels et SMS (Twilio) {st.configure ? `· ${Object.keys(st.contacts || {}).length} contact(s)` : ""}</summary>
      <p className="page__sub">Crée un compte sur twilio.com et achète un numéro (≈ 1 €/mois, puis quelques centimes par appel). Recopie l'<b>Account SID</b>, l'<b>Auth Token</b> et le numéro. EVA n'appelle <b>que les contacts de cette liste</b>, après ton accord, et lit le message à voix haute (« appelle Maman pour lui dire que le dîner est prêt »).</p>
      <div className="routergrid">
        <label className="field"><span>Account SID</span><input value={f.sid} onChange={(e) => setF({ ...f, sid: e.target.value })} placeholder="AC…" /></label>
        <label className="field"><span>Auth Token{st.token_enregistre ? " (laisser vide pour le garder)" : ""}</span><input type="password" value={f.token} onChange={(e) => setF({ ...f, token: e.target.value })} autoComplete="off" /></label>
        <label className="field"><span>Numéro Twilio (appelant)</span><input value={f.de} onChange={(e) => setF({ ...f, de: e.target.value })} placeholder="+33…" /></label>
        <label className="field"><span>Adresse publique d'EVA (pour les appels où EVA converse)</span><input value={f.adresse_publique} onChange={(e) => setF({ ...f, adresse_publique: e.target.value })} placeholder="https://eva.mondomaine.fr" /></label>
      </div>
      <p className="page__sub">Avec l'adresse publique (accès à distance, voir ACCES-A-DISTANCE.md), EVA peut aussi <b>converser</b> : « appelle Maman et demande-lui si elle vient dimanche » — elle se présente comme assistante automatique, écoute la réponse et t'en fait le compte rendu ici.</p>
      <span className="card__label">Contacts autorisés</span>
      {contacts.map((c, i) => (
        <div className="pj-row" key={i}>
          <input value={c.n} onChange={(e) => setContacts(contacts.map((x, j) => (j === i ? { ...x, n: e.target.value } : x)))} placeholder="Nom (ex. Maman)" />
          <input value={c.v} onChange={(e) => setContacts(contacts.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))} placeholder="06 12 34 56 78" />
          <button className="btn btn--ghost" onClick={() => setContacts(contacts.filter((_x, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="agentform__actions">
        <button className="btn" onClick={() => setContacts([...contacts, { n: "", v: "" }])}>+ Contact</button>
        <button className="btn btn--primary" disabled={!f.sid || (!f.token && !st.token_enregistre) || !f.de} onClick={() => b.enregistrer(corps())}>Enregistrer</button>
        {st.configure && <button className="btn" onClick={() => b.tester((r) => `Compte Twilio « ${r.compte} » : identifiants valides.`)}>Tester</button>}
        {st.configure && <button className="btn btn--danger" onClick={b.oublier}>Déconnecter</button>}
      </div>
      <b.Notice />
    </details>
  );
}

function AcoustId({ st, load }) {
  const [cle, setCle] = useState("");
  const b = useBloc("acoustid", load);
  return (
    <details className="googlehelp" data-testid="cx-acoustid">
      <summary>🎵 Reconnaissance musicale (AcoustID) {st.configure ? "· prête" : ""}</summary>
      <p className="page__sub">« EVA, c'est quoi cette musique ? » : EVA écoute 12 secondes et retrouve le titre dans la base libre AcoustID / MusicBrainz. Seule une empreinte sonore part sur Internet, jamais l'enregistrement. Crée une clé gratuite sur <b>acoustid.org › Applications › Register</b> (connexion avec un compte MusicBrainz ou Google) et colle l'« API key ».</p>
      <div className="routergrid"><label className="field"><span>Clé d'application{st.cle_enregistre ? " (laisser vide pour la garder)" : ""}</span><input type="password" value={cle} onChange={(e) => setCle(e.target.value)} autoComplete="off" /></label></div>
      <div className="agentform__actions">
        <button className="btn btn--primary" disabled={!cle} onClick={async () => { if (await b.enregistrer({ cle })) setCle(""); }}>Enregistrer</button>
        {st.configure && <button className="btn" onClick={() => b.tester("Clé AcoustID acceptée.")}>Tester</button>}
        {st.configure && <button className="btn btn--danger" onClick={b.oublier}>Retirer</button>}
      </div>
      <b.Notice />
    </details>
  );
}

export default function ConnecteursCard() {
  const [st, setSt] = useState(null); const [error, setError] = useState("");
  const load = () => api("/api/connecteurs").then(setSt).catch((e) => setError(e.status === 404 ? "Pas encore disponible : eva-core n'a pas été reconstruit avec la dernière mise à jour." : e.message));
  useEffect(() => { load(); }, []);
  if (!st) return <div className="card"><span className="card__label">Diffusion et appels</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  return (
    <div className="card routercard" data-testid="connecteurs-card">
      <span className="card__label">Diffusion, appels et musique</span>
      <p className="page__sub">OBS, Discord, Instagram, appels téléphoniques et reconnaissance musicale. Lire un état ou des chiffres est libre ; lancer un live, publier ou appeler demande toujours ton accord.</p>
      <Obs st={st.obs} load={load} />
      <Discord st={st.discord} load={load} />
      <Instagram st={st.instagram} load={load} />
      <Twilio st={st.twilio} load={load} />
      <AcoustId st={st.acoustid} load={load} />
    </div>
  );
}
