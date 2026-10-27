// URLs d'EVA CORE / EVA VOICE vues depuis le NAVIGATEUR.
// Par défaut : même origine que la page (Caddy route /ws/chat, /api, /voice).
// Surcharge possible via VITE_EVA_* (build) si tu n'utilises pas Caddy.
// Chaque variable est lue par son nom : « const env = import.meta.env » recopierait TOUTES les variables VITE_* (jeton compris) dans la page.
const isHttps = window.location.protocol === "https:";

export const WS_URL =
  import.meta.env.VITE_EVA_WS_URL ||
  `${isHttps ? "wss" : "ws"}://${window.location.host}/ws/chat`;
export const CORE_URL = import.meta.env.VITE_EVA_CORE_URL || window.location.origin;
export const VOICE_URL = import.meta.env.VITE_EVA_VOICE_URL || `${window.location.origin}/voice`;
// Le jeton d'environnement (EVA_AUTH_TOKEN) n'est jamais intégré à l'interface : il serait lisible par tout visiteur et donnerait
// l'accès administrateur sans connexion. On le saisit une fois dans le navigateur (écran « jeton ») si aucun compte n'existe.
const OUT_KEY = "eva.loggedout";
const SESSION_KEY = "eva.auth";   // ≠ "eva.session" (identifiant de conversation, App.jsx)

// Jeton envoyé à EVA : la session de connexion (Paramètres › Sécurité) en priorité, sinon le jeton de la configuration.
export function getToken() {
  try { return localStorage.getItem(SESSION_KEY) || ""; } catch { return ""; }
}
// Connexion : retire le drapeau « déconnecté ». Déconnexion volontaire : le jeton de configuration n'est plus utilisé
// (sinon il rouvrirait l'accès aussitôt) jusqu'à la prochaine connexion.
export function setSession(token) {
  try {
    if (token) { localStorage.setItem(SESSION_KEY, token); localStorage.removeItem(OUT_KEY); }
    else localStorage.removeItem(SESSION_KEY);
  } catch { /* stockage indisponible */ }
}
export function markLoggedOut() { try { localStorage.setItem(OUT_KEY, "1"); } catch { /* ignoré */ } }

export function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}
