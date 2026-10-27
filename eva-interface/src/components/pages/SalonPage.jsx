import { useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthGate";
import { api } from "../../api";
import { confirmer } from "../../confirmer";

const COLORS = ["#7aa2ff", "#ff9f7a", "#7ae0b5", "#e07ad0", "#f0d36b", "#7ad3e0"];
const colorOf = (name) => COLORS[[...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length];
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function Avatar({ name, size = 36 }) {
  return <span className="salon__avatar" style={{ background: colorOf(name), width: size, height: size, fontSize: size * 0.42 }} aria-hidden="true">{(name || "?").slice(0, 1).toUpperCase()}</span>;
}

function Tile({ stream, name, self, video, muted }) {
  const ref = useRef(null);
  const [live, setLive] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return undefined;
    el.srcObject = stream || null;
    const upd = () => setLive(!!stream && stream.getVideoTracks().some((t) => t.enabled && t.readyState === "live" && !t.muted));
    upd();
    const id = setInterval(upd, 800);
    return () => clearInterval(id);
  }, [stream]);
  return (
    <div className={`salon__tile ${live ? "has-video" : ""}`} data-testid={self ? "tile-self" : "tile-remote"}>
      <video ref={ref} autoPlay playsInline muted={self || muted} className={self ? "is-self" : ""} />
      {!live && <div className="salon__tilebg"><Avatar name={name} size={72} /></div>}
      <span className="salon__tilename">{self ? "Toi" : name}{video === false ? " · voix" : ""}</span>
    </div>
  );
}

function RemoteBox() {
  const [servers, setServers] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/room/ice").then((d) => setServers(d.servers)).catch(() => setServers([])); }, []);
  if (!servers) return null;
  const upd = (i, k, v) => setServers(servers.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  async function save() {
    setErr(""); setMsg("");
    try { const d = await api("/api/room/ice", { method: "PUT", body: JSON.stringify({ servers: servers.filter((s) => s.urls?.trim()) }) }); setServers(d.servers); setMsg("Enregistré."); }
    catch (e) { setErr(e.message); }
  }
  return (
    <details className="pageguide" data-testid="salon-remote">
      <summary>🌍 Appels avec des amis hors de ton réseau</summary>
      <p className="card__hint">Sur ton réseau, les appels marchent sans rien régler. Pour des amis chez eux, il faut en plus un serveur de mise en relation. Le plus sûr : un VPN privé comme Tailscale (rien n'est ouvert sur Internet, et les appels passent directement). Sinon, ajoute ici un serveur STUN (cas simple) ou TURN (réseaux stricts). Le guide complet est dans ACCES-A-DISTANCE.md.</p>
      {servers.map((s, i) => (
        <div key={i} className="schedrow">
          <input value={s.urls || ""} onChange={(e) => upd(i, "urls", e.target.value)} placeholder="stun:hote:3478 ou turn:hote:3478" data-testid={`ice-url-${i}`} />
          <input value={s.username || ""} onChange={(e) => upd(i, "username", e.target.value)} placeholder="utilisateur (TURN)" />
          <input type="password" value={s.credential || ""} onChange={(e) => upd(i, "credential", e.target.value)} placeholder="mot de passe (TURN)" autoComplete="new-password" />
          <button className="btn btn--ghost" onClick={() => setServers(servers.filter((_, j) => j !== i))}>Retirer</button>
        </div>
      ))}
      <div className="agentform__actions">
        <button className="btn" onClick={() => setServers([...servers, { urls: "" }])} data-testid="ice-add">Ajouter un serveur</button>
        <button className="btn btn--primary" onClick={save} data-testid="ice-save">Enregistrer</button>
      </div>
      {err && <p className="page__warn">{err}</p>}{msg && <p className="page__sub">{msg}</p>}
    </details>
  );
}

export default function SalonPage({ salon }) {
  const auth = useAuth();
  const s = salon;
  const [text, setText] = useState("");
  const endRef = useRef(null);
  const admin = auth.required && auth.role === "admin";

  useEffect(() => { s.setVisible(true); return () => s.setVisible(false); }, []); // eslint-disable-line
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [s.messages.length]);

  if (!auth.required) {
    return (
      <section className="page salon" data-testid="salon-page">
        <header className="page__header"><h1>Salon</h1><span className="page__sub">discuter entre vous</span></header>
        <div className="page__body"><div className="card"><p className="card__hint">Pour voir qui est connecté et discuter, EVA doit savoir qui est qui : active la connexion et crée un compte par personne dans Paramètres › Sécurité & données.</p></div></div>
      </section>
    );
  }

  const peers = Object.entries(s.remotes);
  const nameOf = (cid) => s.participants.find((p) => p.cid === cid)?.user || "?";
  const videoOf = (cid) => s.participants.find((p) => p.cid === cid)?.video;
  const callCount = s.participants.length;

  function submit(e) { e.preventDefault(); if (!text.trim()) return; s.sendChat(text); setText(""); }
  async function clearHistory() { if ((await confirmer("Effacer toute la discussion du Salon pour tout le monde ?"))) await api("/api/room/messages", { method: "DELETE" }).catch(() => {}); s.messages.length = 0; }

  return (
    <section className="page salon" data-testid="salon-page">
      <header className="page__header"><h1>Salon</h1><span className="page__sub">{s.connected ? `${s.users.length} connecté${s.users.length > 1 ? "s" : ""} · discussion, appels voix et vidéo` : "connexion…"}</span></header>
      <div className="page__body">
      {admin && <RemoteBox />}
      {s.notice && <div className="salon__notice" role="alert" data-testid="salon-notice">{s.notice} <button className="btn btn--ghost" onClick={s.clearNotice}>OK</button></div>}
      <div className="salon__layout">
        <aside className="card salon__people" data-testid="salon-people">
          <span className="card__label">Connectés <small>· clique pour écrire en privé</small></span>
          <ul>
            {s.users.map((u) => (
              <li key={u.user} data-testid={`person-${u.user}`} className={u.user === s.me ? "" : "is-clickable"}
                onClick={u.user === s.me ? undefined : () => s.openDm(u.user)} title={u.user === s.me ? "" : `Écrire en privé à ${u.user}`}
                role={u.user === s.me ? undefined : "button"} tabIndex={u.user === s.me ? undefined : 0}
                onKeyDown={u.user === s.me ? undefined : (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); s.openDm(u.user); } }}>
                <Avatar name={u.user} />
                <span className="salon__who"><b>{u.user}{u.user === s.me ? " (toi)" : ""}</b><small>{u.label}{u.devices > 1 ? ` · ${u.devices} appareils` : ""}</small></span>
                {s.dmUnread[u.user.toLowerCase()] > 0 && <span className="dm__badge" data-testid={`person-badge-${u.user}`}>{s.dmUnread[u.user.toLowerCase()]}</span>}
                {u.user !== s.me && <span className="salon__dmhint" aria-hidden="true">💬</span>}
                {u.in_call && <span className="chip chip--up" title="En appel"><i />{u.video ? "📹" : "🎙️"}</span>}
              </li>
            ))}
            {s.users.length === 0 && <li className="card__hint">Personne pour l'instant.</li>}
          </ul>
          <div className="salon__callbtns">
            {!s.inCall ? (
              <>
                <button className="btn btn--primary" onClick={() => s.joinCall(false)} disabled={!s.connected} data-testid="call-voice">🎙️ {callCount ? "Rejoindre en vocal" : "Appel vocal"}</button>
                <button className="btn btn--primary" onClick={() => s.joinCall(true)} disabled={!s.connected} data-testid="call-video">📹 {callCount ? "Rejoindre en vidéo" : "Appel vidéo"}</button>
              </>
            ) : <button className="btn salon__hang" onClick={s.leaveCall} data-testid="call-hang">⏹ Raccrocher</button>}
          </div>
          {callCount > 0 && !s.inCall && <p className="card__hint">Un appel est en cours ({callCount}). Les appels se font entre {s.participants.length ? "jusqu'à 6 personnes" : "personnes"} sur ton réseau, sans passer par Internet.</p>}
        </aside>

        <div className="salon__main">
          {s.inCall && (
            <div className="card salon__stage" data-testid="salon-stage">
              <div className={`salon__grid n${Math.min(6, 1 + peers.length)}`}>
                <Tile stream={s.local} name={s.me} self video={s.camOn} />
                {peers.map(([cid, stream]) => <Tile key={cid} stream={stream} name={nameOf(cid)} video={videoOf(cid)} />)}
                {s.participants.filter((p) => p.cid !== s.myCid.current && !s.remotes[p.cid]).map((p) => (
                  <div key={p.cid} className="salon__tile"><div className="salon__tilebg"><Avatar name={p.user} size={72} /></div><span className="salon__tilename">{p.user} · connexion…</span></div>
                ))}
              </div>
              <div className="salon__controls">
                <button className={`btn ${s.micOn ? "" : "is-off"}`} onClick={s.toggleMic} data-testid="toggle-mic" aria-pressed={!s.micOn}>{s.micOn ? "🎙️ Micro" : "🔇 Micro coupé"}</button>
                <button className={`btn ${s.camOn ? "" : "is-off"}`} onClick={s.toggleCam} disabled={!s.local?.getVideoTracks().length} data-testid="toggle-cam">{s.camOn ? "📹 Caméra" : "🚫 Caméra coupée"}</button>
                <button className="btn salon__hang" onClick={s.leaveCall}>⏹ Raccrocher</button>
              </div>
            </div>
          )}
          <div className="card salon__chat" data-testid="salon-chat">
            <span className="card__label">Discussion</span>
            <div className="salon__msgs" aria-live="polite">
              {s.messages.length === 0 && <p className="card__hint">Écris le premier message.</p>}
              {s.messages.map((m) => (
                <div key={m.id} className={`salon__msg ${m.user === s.me ? "is-mine" : ""}`} data-testid="salon-msg">
                  <Avatar name={m.user} size={28} />
                  <div><small><b>{m.user}</b> · {hhmm(m.ts)}</small><p>{m.text}</p></div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
            <div className="salon__typing">{s.typing ? `${s.typing} écrit…` : ""}</div>
            <form className="schedrow" onSubmit={submit}>
              <input value={text} onChange={(e) => { setText(e.target.value); s.notifyTyping(); }} placeholder="Écrire un message…" maxLength={2000} data-testid="salon-input" disabled={!s.connected} />
              <button className="btn btn--primary" type="submit" disabled={!text.trim() || !s.connected} data-testid="salon-send">Envoyer</button>
            </form>
            {admin && s.messages.length > 0 && <button className="btn btn--ghost salon__clear" onClick={clearHistory}>Effacer la discussion</button>}
          </div>
        </div>
      </div>
      </div>
    </section>
  );
}
