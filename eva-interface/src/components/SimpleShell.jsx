import { useState } from "react";
import { useAuth } from "./AuthGate";
import HelpLayer from "./HelpLayer";
import SalonDock from "./SalonDock";
import PageGuide from "../PageGuide";

const TABS = [["chat", "Conversation", null], ["images", "Images", "images"], ["lists", "Listes", null], ["recettes", "Recettes", "recettes"], ["inventaire", "Inventaire", "inventaire"], ["wiki", "Wiki", "wiki"], ["papiers", "Papiers", "papiers"], ["salon", "Salon", "salon"], ["carnets", "Carnets", "carnets"], ["maison", "Maison", "home"], ["projects", "Projets", "files"]];

// Interface « standard » des utilisateurs non administrateurs : une conversation, des images, des listes — rien d'autre.
// (L'administrateur garde l'interface complète : réglages, agents, évolution, maison, journal…)
export default function SimpleShell({ pages, sessions, activeId, onOpen, onNew, connected, onMic, recording, speaking, salon }) {
  const auth = useAuth();
  const feats = auth.required ? auth.features : ["voice", "images", "home", "files", "salon", "carnets"];
  const tabs = TABS.filter(([id, , f]) => (!f || feats.includes(f)) && (id === "chat" || pages[id]));
  const [tab, setTab] = useState("chat");
  return (
    <div className="simple" data-testid="simple-shell">
      <header className="simple__bar">
        <img src="/eva-logo.svg" alt="" className="simple__logo" />
        <strong className="simple__name">EVA</strong>
        <span className={`sidebar__dot ${connected ? "is-connected" : ""}`} title={connected ? "Connecté" : "Hors ligne"} />
        <nav className="simple__tabs" aria-label="Navigation">
          {tabs.map(([id, label]) => <button key={id} className={tab === id ? "is-on" : ""} onClick={() => setTab(id)} data-testid={`simple-tab-${id}`}>{label}{id === "salon" && salon && salon.unread + salon.dmTotal > 0 && <span className="dm__badge dm__badge--tab" data-testid="badge-salon">{salon.unread + salon.dmTotal}</span>}</button>)}
        </nav>
        <span className="simple__spacer" />
        {feats.includes("voice") && onMic && (
          <button className={`btn simple__mic ${recording ? "is-rec" : ""}`} onClick={onMic} aria-pressed={!!recording} title="Parler à EVA" data-testid="simple-mic">{recording ? "⏹ J'écoute…" : speaking ? "🔊 EVA parle" : "🎙️ Parler"}</button>
        )}
        {tab === "chat" && (
          <>
            <select className="simple__select" value={activeId} onChange={(e) => onOpen(e.target.value)} aria-label="Mes conversations" data-testid="simple-convs">
              {!sessions.some((s) => s.id === activeId) && <option value={activeId}>Nouvelle conversation</option>}
              {sessions.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select>
            <button className="btn" onClick={onNew} data-testid="simple-new">Nouvelle</button>
          </>
        )}
        {auth.required && <button className="btn btn--ghost" onClick={auth.logout} data-testid="logout">Quitter{auth.user ? ` (${auth.user})` : ""}</button>}
      </header>
      <HelpLayer view={tab} />
      {salon && <SalonDock salon={salon} />}
      <div className="simple__body">{tab !== "chat" && <PageGuide id={tab} />}{pages[tab]}</div>
    </div>
  );
}
