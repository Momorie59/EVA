import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

export default function SpotifyCard() {
  const [st, setSt] = useState(null); const [cid, setCid] = useState(""); const [error, setError] = useState(""); const [msg, setMsg] = useState("");
  const load = () => api("/api/spotify").then((s) => { setSt(s); setCid(s.client_id || ""); })
    .catch((e) => setError(e.status === 404 ? "Pas encore disponible : eva-core n'a pas été reconstruit avec la dernière mise à jour." : e.message));
  useEffect(() => {
    load();
    const retour = (e) => { if (e.data === "eva-spotify") load(); };
    window.addEventListener("message", retour);
    return () => window.removeEventListener("message", retour);
  }, []);
  const run = async (fn, ok) => { setError(""); setMsg(""); try { const r = await fn(); if (ok) setMsg(ok); await load(); return r; } catch (e) { setError(e.message); return null; } };
  const relier = async () => {
    const r = await run(() => api("/api/spotify/connecter", { method: "POST", body: JSON.stringify({ retour: st.retour }) }));
    if (r?.lien) window.open(r.lien, "eva-spotify", "width=520,height=760");
  };
  if (!st) return <div className="card"><span className="card__label">Spotify</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  return (
    <div className="card routercard" data-testid="spotify-card">
      <span className="card__label">🎵 Spotify</span>
      {st.relie
        ? <p className="page__sub">Relié au compte <b>{st.compte}</b>{st.premium === false ? " (gratuit : recherche et playlists, mais pas de pilotage de la lecture)" : ""}. Dis « mets du Daft Punk », « pause », « monte le volume à 40 », « mets la musique sur l'enceinte du salon ».</p>
        : <details className="googlehelp" open>
            <summary>Mise en place (3 minutes)</summary>
            <ol>
              <li>Sur <b>developer.spotify.com</b> › Dashboard › <b>Create app</b> (nom : EVA, « Web API » coché).</li>
              <li>Dans « Redirect URIs », colle exactement : <code className="mcpsrv__pre" style={{ display: "inline-block" }}>{st.retour}</code></li>
              <li>Enregistre, ouvre l'appli, copie le <b>Client ID</b> ci-dessous, puis « Relier » (connexion à ton compte Spotify).</li>
            </ol>
            <p className="page__sub">Piloter la lecture demande Spotify Premium. Aucun mot de passe ni secret n'est gardé par EVA.</p>
          </details>}
      <div className="routergrid"><label className="field"><span>Client ID</span><input value={cid} onChange={(e) => setCid(e.target.value.trim())} placeholder="32 caractères" data-testid="spotify-cid" /></label></div>
      <label className="field"><span><input type="checkbox" checked={st.playlist_auto} onChange={(e) => run(() => api("/api/spotify", { method: "PUT", body: JSON.stringify({ playlist_auto: e.target.checked }) }))} /> Ranger les chansons reconnues (« c'est quoi cette musique ? ») dans la playlist « Reconnu par EVA »</span></label>
      <div className="agentform__actions">
        {cid !== (st.client_id || "") && <button className="btn" disabled={!cid} onClick={() => run(() => api("/api/spotify", { method: "PUT", body: JSON.stringify({ client_id: cid }) }), "Client ID enregistré.")}>Enregistrer</button>}
        {st.client_id && cid === st.client_id && <button className="btn btn--primary" onClick={relier} data-testid="spotify-relier">{st.relie ? "Relier à nouveau" : "Relier"}</button>}
        {st.relie && <button className="btn btn--danger" onClick={() => confirmer("Délier Spotify ?").then((ok) => ok && (run(() => api("/api/spotify", { method: "DELETE" }), "Spotify délié.")))}>Délier</button>}
      </div>
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
