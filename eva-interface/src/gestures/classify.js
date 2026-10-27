// Reconnaissance de gestes à partir des 21 points d'une main (MediaPipe Hand Landmarker). Fonctions pures, testables sans caméra.
// Points : 0 poignet ; pouce 1-4 ; index 5-8 ; majeur 9-12 ; annulaire 13-16 ; auriculaire 17-20 (bout = 4, 8, 12, 16, 20).
const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

// Un doigt est « tendu » si son bout est nettement plus loin du poignet que son articulation médiane.
export function extended(lm) {
  const w = lm[0];
  const f = (tip, pip) => d(lm[tip], w) > d(lm[pip], w) * 1.15;
  const thumb = d(lm[4], lm[17]) > d(lm[3], lm[17]) * 1.05 && d(lm[4], lm[5]) > d(lm[2], lm[5]) * 0.9;
  return { thumb, index: f(8, 6), middle: f(12, 10), ring: f(16, 14), pinky: f(20, 18) };
}

// → "open" (paume ouverte), "peace" (V), "fist" (poing), "point" (index), "thumb_up" / "thumb_down" (pouce), ou null
export function pose(lm) {
  if (!lm || lm.length < 21) return null;
  const e = extended(lm);
  const n4 = [e.index, e.middle, e.ring, e.pinky].filter(Boolean).length;
  if (n4 === 4) return "open";
  if (e.index && e.middle && !e.ring && !e.pinky) return "peace";
  if (e.index && !e.middle && !e.ring && !e.pinky) return "point";
  if (n4 === 0 && e.thumb) {
    // Pouce tendu, le reste replié : vers le haut ou vers le bas (y de l'image croît vers le bas), nettement à la verticale.
    const dy = lm[4].y - lm[2].y, dx = Math.abs(lm[4].x - lm[2].x), taille = d(lm[0], lm[9]);
    if (dy < -0.45 * taille && Math.abs(dy) > dx * 1.3 && lm[4].y < Math.min(lm[6].y, lm[10].y)) return "thumb_up";
    if (dy > 0.45 * taille && Math.abs(dy) > dx * 1.3 && lm[4].y > Math.max(lm[6].y, lm[10].y)) return "thumb_down";
  }
  if (n4 === 0) return "fist";
  return null;
}

export const center = (lm) => ({ x: (lm[0].x + lm[9].x) / 2, y: (lm[0].y + lm[9].y) / 2 });

// Machine à états : appelée à chaque image (t en ms, lm = points de la main ou null).
// Retourne un geste ("next" | "prev" | "pin" | "clear") ou null.
//   - balayer la main ouverte vers la GAUCHE de l'utilisateur → diapo suivante, vers la DROITE → précédente
//   - paume ouverte immobile 1,2 s → épingler / désépingler
//   - signe de paix tenu 0,8 s → effacer l'écran
//   - poing fermé tenu 0,9 s → "summarize" (EVA résume ce qui est affiché)
//   - pouce levé / baissé tenu 0,7 s → "yes" / "no" (répond à une demande d'accord)
export function createDetector(opts = {}) {
  const o = { swipe: 0.28, swipeMs: 450, palmMs: 1200, peaceMs: 800, fistMs: 900, thumbMs: 700, cooldown: 1400, still: 0.04, ...opts };
  let trail = [];            // [{t, x}]
  let hold = { pose: null, since: 0, x: 0, y: 0 };
  let lastFire = -1e9;
  const fire = (t, g) => { lastFire = t; trail = []; hold = { pose: null, since: 0, x: 0, y: 0 }; return g; };

  return function step(t, lm) {
    if (!lm) { trail = []; hold = { pose: null, since: 0, x: 0, y: 0 }; return null; }
    if (t - lastFire < o.cooldown) return null;
    const p = pose(lm), c = center(lm);
    if (p === "open") {
      trail.push({ t, x: c.x });
      trail = trail.filter((s) => t - s.t <= o.swipeMs);
      const dx = c.x - trail[0].x;                    // image brute (non miroir) : x augmente quand la main va vers la gauche de l'utilisateur
      if (Math.abs(dx) >= o.swipe && trail.length >= 3) return fire(t, dx > 0 ? "next" : "prev");
    } else trail = [];
    const tenus = { open: [o.palmMs, "pin"], peace: [o.peaceMs, "clear"], fist: [o.fistMs, "summarize"], thumb_up: [o.thumbMs, "yes"], thumb_down: [o.thumbMs, "no"] };
    if (p && tenus[p]) {
      if (hold.pose !== p || Math.hypot(c.x - hold.x, c.y - hold.y) > o.still) hold = { pose: p, since: t, x: c.x, y: c.y };
      if (t - hold.since >= tenus[p][0]) return fire(t, tenus[p][1]);
    } else hold = { pose: null, since: 0, x: 0, y: 0 };
    return null;
  };
}
