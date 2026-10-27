export default function ControlDock({
  micOn, cameraOn, onToggleMic, onToggleCamera, onOpenDashboard,
  speakOn, onToggleSpeak, wakeOn, wakePhase, wakeWord = "eva", wakeError, onToggleWake, speaking, onStopSpeaking, wakeLevel = 0, wakeHeard = "", wakeBusy = false, thinking = false, onMusique, musiqueOn = false,
}) {
  const hint = wakeError
    ? wakeError
    : wakeOn
      ? wakePhase === "awake" ? "Je t'écoute…" : wakePhase === "sleep" ? `Dis « ${wakeWord} » pour me réveiller` : "Activation du micro…"
      : "";
  return (
    <div className="control-dock">
      {hint && <div className={`control-dock__hint ${wakeError ? "is-error" : ""} ${wakePhase === "awake" ? "is-awake" : ""}`} role="status">
        {hint}
        {wakeOn && !wakeError && wakePhase !== "off" && (
          <>
            <span className="meter" title="Niveau du micro"><i style={{ width: `${Math.min(100, Math.sqrt(wakeLevel) * 260)}%` }} /></span>
            {(wakeBusy || thinking || wakeHeard) && <div className="control-dock__heard">{wakeBusy ? "Analyse…" : thinking ? "Je réfléchis…" : `J'ai entendu : « ${wakeHeard} »`}</div>}
          </>
        )}
      </div>}
      <button
        className={`control-dock__btn ${cameraOn ? "is-active" : ""}`}
        onClick={onToggleCamera}
        aria-pressed={cameraOn}
        aria-label="Activer la caméra"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="6" width="13" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
          <path d="M16 10.5 21 7v10l-5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
      </button>

      <button
        className={`control-dock__btn ${wakeOn ? "is-active" : ""} ${wakePhase === "awake" ? "is-awake" : ""}`}
        onClick={onToggleWake}
        aria-pressed={!!wakeOn}
        aria-label="Écoute mains libres (mot d'éveil)"
        title="Écoute mains libres : dis le mot d'éveil"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M4 12h2M8 8v8M12 4v16M16 8v8M20 12h-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>

      <button
        className={`control-dock__btn control-dock__btn--primary ${micOn ? "is-active" : ""}`}
        onClick={onToggleMic}
        aria-pressed={micOn}
        aria-label="Parler à EVA"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="1.6" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </button>

      <button
        className={`control-dock__btn ${speaking ? "is-active" : speakOn ? "is-on" : ""}`}
        onClick={speaking ? onStopSpeaking : onToggleSpeak}
        aria-pressed={!!speakOn}
        aria-label={speaking ? "Arrêter la lecture" : "Lire les réponses à voix haute"}
        title={speaking ? "Arrêter la lecture" : speakOn ? "Lecture à voix haute activée" : "Lire les réponses à voix haute"}
      >
        {speaking ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" /></svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M4 10v4h4l5 4V6L8 10H4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            {speakOn ? <path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /> : <path d="M17 9l4 6M21 9l-4 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />}
          </svg>
        )}
      </button>

      {onMusique && (
        <button className={`control-dock__btn ${musiqueOn ? "is-active" : ""}`} onClick={onMusique} disabled={musiqueOn}
          aria-label="Quelle est cette musique ?" title="Quelle est cette musique ? (12 secondes d'écoute)" data-testid="musique-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M9 18V6l10-2v12" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            <circle cx="6.5" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.5" /><circle cx="16.5" cy="16" r="2.5" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>
      )}
      <button className="control-dock__btn" aria-label="Projets" onClick={onOpenDashboard}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path
            d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
      </button>
    </div>
  );
}
