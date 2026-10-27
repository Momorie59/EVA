import { STATE_COLORS } from "../states";

const STATE_TEXT = {
  idle: "EN VEILLE",
  listening: "ÉCOUTE",
  thinking: "ANALYSE",
  acting: "EXÉCUTION",
  speaking: "RÉPONSE",
  error: "ANOMALIE",
};
// Vitesse de rotation des anneaux selon l'état (1 = repos)
const STATE_SPIN = { idle: 1, listening: 1.6, thinking: 3, acting: 4.5, speaking: 2, error: 0.6 };

const TICKS = Array.from({ length: 120 }, (_, i) => i);

// Habillage HUD plein écran autour de l'avatar (affiché sur grand écran seulement).
export default function HudRings({ evaState }) {
  return (
    <div
      className="hud-rings"
      aria-hidden="true"
      style={{ "--hud-color": STATE_COLORS[evaState], "--spin": STATE_SPIN[evaState] }}
    >
      <svg className="hud-rings__svg" viewBox="-500 -500 1000 1000">
        <g className="ring ring--slow">
          {TICKS.map((i) => (
            <line
              key={i}
              x1="0"
              y1={i % 10 === 0 ? -472 : -480}
              x2="0"
              y2="-492"
              transform={`rotate(${i * 3})`}
              className={i % 10 === 0 ? "tick tick--major" : "tick"}
            />
          ))}
        </g>
        <g className="ring ring--rev">
          <circle r="440" strokeDasharray="260 40 90 40 20 40" />
        </g>
        <g className="ring ring--mid">
          <circle r="392" strokeDasharray="2 12" />
        </g>
        <g className="ring ring--fast">
          <circle r="344" strokeDasharray="120 60 30 60" />
        </g>
        <circle r="296" className="ring-static" />
        <line x1="-500" y1="0" x2="-310" y2="0" className="cross" />
        <line x1="310" y1="0" x2="500" y2="0" className="cross" />
        <line x1="0" y1="-500" x2="0" y2="-310" className="cross" />
        <line x1="0" y1="310" x2="0" y2="500" className="cross" />
      </svg>
      <span className="hud-rings__tag hud-rings__tag--l">EVA // CORE</span>
      <span className="hud-rings__tag hud-rings__tag--r">{STATE_TEXT[evaState]}</span>
    </div>
  );
}
