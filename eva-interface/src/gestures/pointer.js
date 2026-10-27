// Main « curseur » : position à l'écran, pincement (attraper), pincement bref (cliquer), zoom à deux mains. Fonctions pures.
import { pose, center } from "./classify.js";

const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export const pinchRatio = (lm) => d(lm[4], lm[8]) / (d(lm[0], lm[9]) || 1e-6);        // écart pouce-index, en tailles de main
export const pinchPoint = (lm) => ({ x: (lm[4].x + lm[8].x) / 2, y: (lm[4].y + lm[8].y) / 2 });

// Retourne step(t, hands) → { hands: [{x, y, pinch}], events: [{type, hand, x, y}], zoom }.
// x, y : 0..1 à l'écran (image miroir : ta main droite est à droite). zoom : facteur ≈ 1 par image quand deux mains pincent.
export function createPointer(opts = {}) {
  const o = { on: 0.3, off: 0.5, tapMs: 380, tapMove: 0.06, ...opts };
  const st = [0, 1].map(() => ({ down: false, since: 0, x0: 0, y0: 0, moved: 0 }));
  let prevSpan = null;
  return function step(t, hands) {
    const out = { hands: [], events: [], zoom: 1 };
    (hands || []).slice(0, 2).forEach((lm, i) => {
      const s = st[i], pt = pinchPoint(lm), x = 1 - pt.x, y = pt.y;
      const r = pinchRatio(lm), isFist = pose(lm) === "fist";
      const was = s.down;
      if (!s.down && r < o.on && !isFist) s.down = true;
      else if (s.down && (r > o.off || isFist)) s.down = false;
      if (s.down && !was) { s.since = t; s.x0 = x; s.y0 = y; s.moved = 0; out.events.push({ type: "pinchstart", hand: i, x, y }); }
      if (s.down) s.moved = Math.max(s.moved, Math.hypot(x - s.x0, y - s.y0));
      if (!s.down && was) {
        out.events.push({ type: "pinchend", hand: i, x, y });
        if (t - s.since <= o.tapMs && s.moved <= o.tapMove) out.events.push({ type: "tap", hand: i, x: s.x0, y: s.y0 });
      }
      out.hands.push({ x, y, pinch: s.down });
    });
    for (let i = (hands || []).length; i < 2; i++) { if (st[i].down) out.events.push({ type: "pinchend", hand: i, x: 0, y: 0 }); st[i].down = false; }
    // Zoom à deux mains : deux mains OUVERTES (ou pincées) qu'on écarte / rapproche.
    const two = (hands || []).length >= 2 && hands.slice(0, 2).every((lm, i) => pose(lm) === "open" || out.hands[i].pinch);
    if (two) {
      const a = center(hands[0]), b = center(hands[1]);
      const span = Math.hypot(a.x - b.x, a.y - b.y);
      if (prevSpan && prevSpan > 0.04) {
        const r = span / prevSpan;
        out.zoom = Math.abs(r - 1) < 0.012 ? 1 : Math.min(1.25, Math.max(0.8, r));
      }
      prevSpan = span;
    } else prevSpan = null;
    return out;
  };
}
