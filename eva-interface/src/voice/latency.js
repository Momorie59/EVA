// Petites mesures de latence affichées dans Paramètres → Voix (aucune donnée n'est envoyée nulle part).
const KEY = "eva.latency";
const state = {};
export function record(name, ms) {
  state[name] = Math.round(ms);
  try { window.sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* facultatif */ }
  window.dispatchEvent(new Event("eva-latency"));
}
export function readLatency() {
  try { return { ...JSON.parse(window.sessionStorage.getItem(KEY) || "{}"), ...state }; } catch { return { ...state }; }
}
