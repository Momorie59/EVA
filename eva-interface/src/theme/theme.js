// Thème d'EVA : couleurs, transparence et disposition personnalisables.
// Tout est ramené à des variables CSS posées sur <html> ; les attributs data-* pilotent la disposition.

export const PRESETS = {
  crepuscule: {
    label: "Crépuscule",
    colors: { bgA: "#5a45b0", bgB: "#2f6bb8", bgC: "#e08a52", glow: "#ffcd82", accent: "#ffc15e", accent2: "#00ffb3", ink: "#fff4e0" },
    glass: 0.16, blur: 14,
  },
  aube: {
    label: "Aube (clair)",
    colors: { bgA: "#ffd9e8", bgB: "#cfe3ff", bgC: "#e0d4ff", glow: "#ffffff", accent: "#6a55f0", accent2: "#12a37a", ink: "#1d2540" },
    glass: 0.62, blur: 18,
  },
  glace: {
    label: "Glace (clair)",
    colors: { bgA: "#ffffff", bgB: "#e3f3fb", bgC: "#bfe0f2", glow: "#ffffff", accent: "#1b9ccf", accent2: "#ff8a1f", ink: "#16384f" },
    glass: 0.78, blur: 12,
  },
  ocean: {
    label: "Océan",
    colors: { bgA: "#1fa6e0", bgB: "#2a6fe0", bgC: "#6a4be0", glow: "#9fe8ff", accent: "#ffffff", accent2: "#00ffb3", ink: "#ffffff" },
    glass: 0.18, blur: 16,
  },
  hologramme: {
    label: "Hologramme",
    colors: { bgA: "#4aa0d4", bgB: "#2a6a9c", bgC: "#1a4268", glow: "#9fe8ff", accent: "#00ffb3", accent2: "#ffd36b", ink: "#eaf8ff" },
    glass: 0.14, blur: 14,
  },
  nuit: {
    label: "Nuit (sombre)",
    colors: { bgA: "#06070a", bgB: "#0a0c10", bgC: "#12161f", glow: "#1d4d52", accent: "#6ee7d8", accent2: "#a78bfa", ink: "#e8eaed" },
    glass: 0.07, blur: 14,
  },
};

export const DEFAULT_LAYOUT = {
  nav: "left",        // left | rail | top | hidden
  chat: "right",      // right | left | hidden
  widgets: "bottom",  // left | right | bottom | hidden
  logo: 100,          // taille du logo, en %
  rings: true,
  grid: true,
  density: "normal",  // compact | normal | large
  radius: 18,
  notes: true,        // afficher les post-it
};

export const DEFAULT_THEME = { preset: "crepuscule", ...PRESETS.crepuscule, label: undefined, layout: { ...DEFAULT_LAYOUT } };
delete DEFAULT_THEME.label;

const HEX = /^#[0-9a-f]{6}$/i;
const clamp = (v, lo, hi, d) => (Number.isFinite(+v) ? Math.min(hi, Math.max(lo, +v)) : d);
const pick = (v, allowed, d) => (allowed.includes(v) ? v : d);

// Accepte n'importe quel objet (stockage ancien, import) et renvoie un thème complet et sûr.
export function normalizeTheme(raw) {
  const base = PRESETS[raw?.preset] || PRESETS.crepuscule;
  const t = raw && typeof raw === "object" ? raw : {};
  const colors = {};
  for (const k of Object.keys(PRESETS.crepuscule.colors)) {
    const v = t.colors?.[k];
    colors[k] = typeof v === "string" && HEX.test(v) ? v.toLowerCase() : base.colors[k];
  }
  const L = t.layout || {};
  return {
    preset: PRESETS[t.preset] ? t.preset : "custom",
    updatedAt: Number(t.updatedAt) || 0,
    colors,
    glass: clamp(t.glass, 0, 0.9, base.glass),
    blur: clamp(t.blur, 0, 40, base.blur),
    textStrength: clamp(t.textStrength, 0.6, 1, 0.85),  // intensité du texte secondaire (lisibilité)
    layout: {
      nav: pick(L.nav, ["left", "rail", "top", "hidden"], DEFAULT_LAYOUT.nav),
      chat: pick(L.chat, ["right", "left", "hidden"], DEFAULT_LAYOUT.chat),
      widgets: pick(L.widgets, ["left", "right", "bottom", "hidden"], DEFAULT_LAYOUT.widgets),
      logo: clamp(L.logo, 60, 140, 100),
      rings: L.rings !== false,
      grid: L.grid !== false,
      density: pick(L.density, ["compact", "normal", "large"], "normal"),
      radius: clamp(L.radius, 0, 32, DEFAULT_LAYOUT.radius),
      notes: L.notes !== false,
    },
  };
}

export function presetTheme(id) {
  const p = PRESETS[id] || PRESETS.crepuscule;
  return normalizeTheme({ preset: id, colors: p.colors, glass: p.glass, blur: p.blur, textStrength: 0.85, layout: DEFAULT_LAYOUT });
}

export function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const rgbStr = (hex) => hexToRgb(hex).join(", ");
function luminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
// Texte lisible sur une couleur d'accent donnée.
// On prend, entre sombre et blanc, celui qui offre le meilleur contraste (le seuil fixe donnait des textes illisibles sur les accents moyens).
export const onColor = (hex) => {
  const l = luminance(hex);
  const dark = (l + 0.05) / (luminance("#10161f") + 0.05);
  const white = 1.05 / (l + 0.05);
  return dark >= white ? "#10161f" : "#ffffff";
};

const contrast = (l1, l2) => (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
const mixHex = (hex, white) => hexToRgb(hex).map((v) => v * (1 - white) + 255 * white);
const lumRgb = ([r, g, b]) => { const f = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
// Fond des panneaux de verre : s'il ne laisse pas le texte lisible (ratio < 4,5 sur le pire des 3 fonds), on le teinte automatiquement.
function glassFill(theme) {
  const { colors: c, glass } = theme;
  const inkL = luminance(c.ink);
  const worst = Math.min(...[c.bgA, c.bgB, c.bgC].map((b) => contrast(inkL, lumRgb(mixHex(b, glass)))));
  if (worst >= 4.5) return `rgba(255, 255, 255, ${glass})`;
  return inkL > 0.5 ? `rgba(6, 12, 32, ${Math.min(0.6, 0.3 + glass * 0.5).toFixed(2)})` : `rgba(255, 255, 255, ${Math.max(glass, 0.72)})`;
}

const DENSITY = { compact: 0.9, normal: 1, large: 1.12 };
// Variables CSS d'un thème (les largeurs de colonnes se calculent en CSS selon data-chat / data-widgets).
export function themeVars(theme) {
  const { colors: c, layout: L } = theme;
  const ink = c.ink;
  const lightInk = luminance(ink) > 0.5;      // encre claire ⇒ fond sombre/coloré
  return {
    "--bg-a": c.bgA, "--bg-b": c.bgB, "--bg-c": c.bgC, "--glow": c.glow, "--glow-rgb": rgbStr(c.glow),
    "--accent": c.accent, "--accent-rgb": rgbStr(c.accent), "--accent2": c.accent2, "--accent2-rgb": rgbStr(c.accent2),
    "--ink": ink, "--ink-rgb": rgbStr(ink),
    "--ink-muted": `rgba(${rgbStr(ink)}, ${theme.textStrength})`, "--ink-faint": `rgba(${rgbStr(ink)}, ${Math.max(0.5, theme.textStrength - 0.15).toFixed(2)})`,
    "--on-accent": onColor(c.accent),
    "--bg-rgb": rgbStr(c.bgA),
    "--glass": String(theme.glass), "--blur": `${theme.blur}px`,
    "--glass-fill": glassFill(theme),
    "--glass-edge": `rgba(${rgbStr(c.accent)}, ${lightInk ? 0.55 : 0.4})`,
    "--panel-radius": `${L.radius}px`,
    "--fs": String(DENSITY[L.density]),
    "--logo-scale": String(L.logo / 100),
    "--tone": lightInk ? "dark" : "light",
  };
}

export function themeAttrs(theme) {
  const L = theme.layout;
  return {
    "data-nav": L.nav, "data-chat": L.chat, "data-widgets": L.widgets,
    "data-rings": L.rings ? "on" : "off", "data-grid": L.grid ? "on" : "off",
    "data-density": L.density, "data-notes": L.notes ? "on" : "off",
    "data-tone": luminance(theme.colors.ink) > 0.5 ? "dark" : "light",
  };
}

export function applyTheme(theme, root = document.documentElement) {
  const vars = themeVars(theme);
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
  for (const [k, v] of Object.entries(themeAttrs(theme))) root.setAttribute(k, v);
}
