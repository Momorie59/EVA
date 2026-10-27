import { STATE_COLORS } from "../states";

const STATE_LABELS = {
  idle: "Je suis là.",
  listening: "Je t'écoute…",
  thinking: "Je réfléchis…",
  acting: "J'utilise un outil…",
  speaking: "…",
  error: "Une erreur est survenue.",
};

const STATES = ["idle", "listening", "thinking", "acting", "speaking", "error"];

export default function StatusLine({ evaState, onStateChange }) {
  return (
    <div className="status-line">
      <p className="status-line__text">
        <span
          className="status-line__dot"
          style={{ background: STATE_COLORS[evaState] }}
        />
        {STATE_LABELS[evaState]}
      </p>

      {/* Simulateur d'état — à retirer une fois le harness connecté en WebSocket */}
      <div className="state-sim" role="group" aria-label="Simuler un état d'EVA">
        {STATES.map((s) => (
          <button
            key={s}
            className={`state-sim__dot ${s === evaState ? "is-active" : ""}`}
            style={{ "--dot-color": STATE_COLORS[s] }}
            onClick={() => onStateChange(s)}
            aria-label={s}
            title={s}
          />
        ))}
      </div>
    </div>
  );
}
