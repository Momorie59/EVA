import { useState } from "react";
import HudClock from "./HudClock";
import { WHO_ICON, WHO_TITLE } from "../hooks/useIdentity";

function MiniLogo() {
  return (
    <svg className="top-bar__logo" viewBox="0 0 200 200" role="img" aria-label="EVA">
      <circle cx="100" cy="100" r="98" fill="#0b1018" stroke="#232B38" strokeWidth="3" />
      <circle cx="100" cy="100" r="34" fill="none" stroke="#00FFB3" strokeWidth="8" />
      <circle cx="100" cy="100" r="13" fill="#00FFB3" />
      <circle cx="100" cy="37" r="12" fill="#4D9FFF" />
      <circle cx="154" cy="130" r="12" fill="#A855F7" />
      <circle cx="46" cy="130" r="12" fill="#EAB308" />
    </svg>
  );
}

export default function TopBar({ connected, offlineReason, who, onMenu, onSettings, canVerify, onVerify, onCommand, onTheme, extra, speaking, speakOn, onStopSpeaking, onToggleSpeak }) {
  const [cmd, setCmd] = useState("");
  function submit(e) {
    e.preventDefault();
    const t = cmd.trim();
    if (!t) return;
    onCommand?.(t);
    setCmd("");
  }
  return (
    <header className="top-bar">
      <button className="menu-btn top-bar__menu" onClick={onMenu} aria-label="Menu">☰</button>
      <span className="top-bar__brand">
        <span className="top-bar__mark">EVA</span>
        <span
          className={`top-bar__status ${connected ? "is-connected" : ""}`}
          title={connected ? "EVA CORE connecté" : `EVA CORE déconnecté — ${offlineReason || ""}`}
        />
      </span>
      <span className="top-bar__id"><MiniLogo /><b className="top-bar__word">EVA</b></span>
      <form className="top-bar__cmd" onSubmit={submit} role="search">
        <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder="Demande n'importe quoi à EVA…" aria-label="Donner un ordre à EVA" data-testid="top-cmd" />
      </form>
      <div className="top-bar__center">
        <span className="top-bar__title">EVA</span>
        <span className="top-bar__tagline">ASSISTANT PERSONNEL · LOCAL</span>
        <HudClock />
        {who && <span className="top-bar__who" data-testid="who" title={WHO_TITLE[who.source]}>{WHO_ICON[who.source]} {who.name}</span>}
        {canVerify && (!who || who.source !== "face-live") && <button className="top-bar__verify" data-testid="verify-btn" onClick={onVerify}>🔒 Me présenter</button>}
      </div>
      <div className="top-bar__actions">
        {extra}
        <button type="button" className={`top-bar__icon ${speaking ? "is-hot" : ""}`} data-testid="mute-btn"
          onClick={speaking ? onStopSpeaking : onToggleSpeak}
          aria-label={speaking ? "Couper le son" : speakOn ? "Désactiver la voix d'EVA" : "Activer la voix d'EVA"}
          title={speaking ? "Couper le son (arrêter la lecture)" : speakOn ? "Voix d'EVA activée : cliquer pour couper" : "Voix d'EVA coupée : cliquer pour activer"}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 10v4h4l5 4V6L8 10H4Z" />
            {speakOn || speaking ? <path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11" /> : <path d="M17 9l4 6M21 9l-4 6" />}
          </svg>
        </button>
        <button type="button" className="top-bar__icon" onClick={onTheme} aria-label="Personnaliser l'interface" title="Personnaliser l'interface" data-testid="theme-open">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><circle cx="8.5" cy="10" r="1.2" fill="currentColor" /><circle cx="12" cy="7.5" r="1.2" fill="currentColor" /><circle cx="15.5" cy="10" r="1.2" fill="currentColor" /><path d="M12 21c-1.5 0-2-1-1.6-2 .5-1.2 1.6-1.6 1.6-3a2 2 0 0 0-2-2" /></svg>
        </button>
      </div>
      <span className={`top-bar__pill ${connected ? "is-ok" : "is-down"}`} data-testid="conn-pill">{connected ? "● Tout fonctionne" : "● Hors ligne"}</span>
      <button className="top-bar__settings" aria-label="Paramètres" onClick={onSettings}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path
            d="M19.4 13.5a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V19.5a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H4.5a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1.08 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H10a1.65 1.65 0 0 0 1-1.51V4.5a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V10a1.65 1.65 0 0 0 1.51 1h.09a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"
            stroke="currentColor"
            strokeWidth="1.3"
          />
        </svg>
      </button>
    </header>
  );
}
