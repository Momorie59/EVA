import { useSyncExternalStore } from "react";
import { api } from "../api";
import { applyTheme, normalizeTheme, presetTheme } from "./theme";

const KEY = "eva.theme";
const listeners = new Set();
let saveTimer = null;

function load() {
  try { const raw = window.localStorage.getItem(KEY); if (raw) return normalizeTheme(JSON.parse(raw)); } catch { /* stockage indisponible ou corrompu */ }
  return presetTheme("crepuscule");
}
let current = typeof window !== "undefined" ? load() : presetTheme("crepuscule");

function emit() { listeners.forEach((l) => l()); }
function persist(theme) {
  try { window.localStorage.setItem(KEY, JSON.stringify(theme)); } catch { /* ignoré */ }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => api("/api/ui/theme", { method: "PUT", body: JSON.stringify({ theme }) }).catch(() => {}), 700);
}

export function getTheme() { return current; }
export function setTheme(next) {
  current = { ...normalizeTheme(typeof next === "function" ? next(current) : next), updatedAt: Date.now() };
  applyTheme(current);
  persist(current);
  emit();
}
export function resetTheme() {
  current = presetTheme("crepuscule");
  applyTheme(current);
  try { window.localStorage.removeItem(KEY); } catch { /* ignoré */ }
  clearTimeout(saveTimer);
  api("/api/ui/theme", { method: "PUT", body: JSON.stringify({ theme: null }) }).catch(() => {});
  emit();
}

// Applique le thème dès le chargement du module (pas de flash), puis adopte celui du serveur s'il existe
// (pour retrouver le même thème sur le téléphone et sur le PC).
if (typeof window !== "undefined") {
  applyTheme(current);
  api("/api/ui/theme").then((r) => {
    if (r?.theme && (Number(r.theme.updatedAt) || 0) > (current.updatedAt || 0)) {
      current = normalizeTheme(r.theme);
      applyTheme(current);
      try { window.localStorage.setItem(KEY, JSON.stringify(current)); } catch { /* ignoré */ }
      emit();
    }
  }).catch(() => {});
}

export function useTheme() {
  const theme = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, getTheme, getTheme);
  return [theme, setTheme, resetTheme];
}
