import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthGate";

// Discussions privées du Salon, façon Zoom/Messenger : des fenêtres en bas à droite, visibles depuis n'importe quel onglet.
// Une fenêtre repliée montre le nom et une pastille avec le nombre de messages non lus ; un clic la déplie.
const COLORS = ["#7aa2ff", "#ff9f7a", "#7ae0b5", "#e07ad0", "#f0d36b", "#7ad3e0"];
const colorOf = (name) => COLORS[[...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length];
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function Win({ s, w }) {
  const low = w.user.toLowerCase();
  const list = s.dms[low] || [];
  const unread = s.dmUnread[low] || 0;
  const online = s.users.some((u) => u.user.toLowerCase() === low);
  const [text, setText] = useState("");
  const endRef = useRef(null);

  useEffect(() => { if (!w.min) endRef.current?.scrollIntoView({ block: "end" }); }, [list.length, w.min]);
  useEffect(() => { if (!w.min && unread > 0 && document.visibilityState === "visible") s.markRead(w.user); }, [w.min, unread]); // eslint-disable-line

  function submit(e) { e.preventDefault(); if (!text.trim()) return; s.sendDm(w.user, text); setText(""); }

  return (
    <div className={`dm ${w.min ? "is-min" : ""}`} data-testid={`dm-${low}`} role="dialog" aria-label={`Discussion avec ${w.user}`}>
      <header className="dm__head" onClick={() => s.minDm(w.user, !w.min)}>
        <span className="salon__avatar" style={{ background: colorOf(w.user), width: 28, height: 28, fontSize: 12 }} aria-hidden="true">{w.user.slice(0, 1).toUpperCase()}</span>
        <span className="dm__name"><b>{w.user}</b><small>{online ? "en ligne" : "hors ligne"}</small></span>
        {unread > 0 && <span className="dm__badge" data-testid={`dm-badge-${low}`} aria-label={`${unread} message${unread > 1 ? "s" : ""} non lu${unread > 1 ? "s" : ""}`}>{unread}</span>}
        <button type="button" className="dm__btn" aria-label={w.min ? "Déplier" : "Replier"} onClick={(e) => { e.stopPropagation(); s.minDm(w.user, !w.min); }}>{w.min ? "▴" : "–"}</button>
        <button type="button" className="dm__btn" aria-label="Fermer" data-testid={`dm-close-${low}`} onClick={(e) => { e.stopPropagation(); s.closeDm(w.user); }}>✕</button>
      </header>
      {!w.min && (
        <>
          <div className="dm__msgs" aria-live="polite">
            {list.length === 0 && <p className="card__hint">Dis bonjour à {w.user}. Cette discussion reste entre vous deux.</p>}
            {list.map((m) => (
              <div key={m.id} className={`dm__msg ${m.from.toLowerCase() === low ? "" : "is-mine"}`} data-testid="dm-msg">
                <p>{m.text}</p><small>{hhmm(m.ts)}</small>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <div className="salon__typing">{s.dmTyping && s.dmTyping.toLowerCase() === low ? `${w.user} écrit…` : ""}</div>
          <form className="dm__form" onSubmit={submit}>
            <input value={text} onChange={(e) => { setText(e.target.value); s.notifyDmTyping(w.user); }} placeholder={`Message à ${w.user}…`} maxLength={2000} data-testid={`dm-input-${low}`} autoFocus />
            <button className="btn btn--primary" type="submit" disabled={!text.trim() || !s.connected} data-testid={`dm-send-${low}`}>➤</button>
          </form>
        </>
      )}
    </div>
  );
}

export default function SalonDock({ salon }) {
  const auth = useAuth();
  if (!auth.required || !salon.connected || salon.dmOpen.length === 0) return null;
  return <div className="dmdock" data-testid="dm-dock">{salon.dmOpen.map((w) => <Win key={w.user.toLowerCase()} s={salon} w={w} />)}</div>;
}
