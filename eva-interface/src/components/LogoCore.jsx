import { STATE_COLORS } from "../states";

// Le logo d'EVA, tel quel, en vectoriel :
// anneau central vert, point central, trois points en orbite (bleu, violet,
// jaune) et trait d'orbite pointillé. Seule l'animation exprime l'état d'EVA ;
// les couleurs du logo ne changent jamais, seul le halo autour prend la
// couleur de l'état.
export default function LogoCore({ evaState = "idle" }) {
  return (
    <div className={`logo-core logo-core--${evaState}`} style={{ "--state-color": STATE_COLORS[evaState] }}>
      <span className="logo-core__halo logo-core__halo--a" />
      <span className="logo-core__halo logo-core__halo--b" />
      <svg className="logo-core__svg" viewBox="0 0 200 200" role="img" aria-label="EVA">
        <defs>
          <radialGradient id="eva-bg" cx="50%" cy="50%" r="75%">
            <stop offset="0%" stopColor="#10161F" />
            <stop offset="100%" stopColor="#080C14" />
          </radialGradient>
          <filter id="eva-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <circle cx="100" cy="100" r="98" fill="url(#eva-bg)" stroke="#232B38" strokeWidth="1.5" />

        <g className="logo-core__center">
          <circle cx="100" cy="100" r="34" fill="none" stroke="#00FFB3" strokeWidth="4" filter="url(#eva-glow)" />
          <circle className="logo-core__dot" cx="100" cy="100" r="13" fill="#00FFB3" filter="url(#eva-glow)" />
        </g>

        <circle cx="100" cy="100" r="63" fill="none" stroke="#232B38" strokeWidth="1" strokeDasharray="2 4" />

        <g className="logo-core__orbit">
          <circle cx="100" cy="37" r="9" fill="#4D9FFF" filter="url(#eva-glow)" />
          <circle cx="154" cy="130" r="9" fill="#A855F7" filter="url(#eva-glow)" />
          <circle cx="46" cy="130" r="9" fill="#EAB308" filter="url(#eva-glow)" />
        </g>
      </svg>
    </div>
  );
}
