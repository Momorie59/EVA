import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";

export const WHO_ICON = { voice: "🎙", face: "📷", "face-live": "🔒", style: "✍" };
export const WHO_TITLE = { voice: "Reconnu à la voix", face: "Visage aperçu par la caméra (non vérifié en direct)", "face-live": "Visage vérifié en direct", style: "Indice : façon d'écrire (peu fiable)" };
export const IDENTITY_EVENT = "eva-identity-changed";

export async function postBinary(path, blob, timeoutMs = 15000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${CORE_URL}${path}`, { method: "POST", headers: authHeaders(), body: blob, signal: ctrl.signal });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Erreur ${res.status}`);
    return data;
  } finally { clearTimeout(t); }
}

const ready = (s) => s && s.models?.speaker && s.libs?.sherpa_onnx;
const faceReady = (s) => s && s.models?.face_detect && s.models?.face_recog && s.libs?.cv2;

// Qui parle ? Voix (à chaque phrase) et visage (présence devant la caméra, si activé).
// Le serveur vérifie lui-même le jeton renvoyé : le navigateur ne peut pas se faire passer pour quelqu'un.
export function useIdentity() {
  const [status, setStatus] = useState(null);
  const [who, setWho] = useState(null); // { name, source, ts }
  const statusRef = useRef(null);
  const voiceRef = useRef(null);
  const faceRef = useRef(null);
  const liveRef = useRef(null);
  statusRef.current = status;

  const refresh = useCallback(() => api("/api/identity/status").then(setStatus).catch(() => {}), []);
  useEffect(() => {
    refresh();
    window.addEventListener(IDENTITY_EVENT, refresh);
    return () => window.removeEventListener(IDENTITY_EVENT, refresh);
  }, [refresh]);

  // Le nom affiché s'efface quand la reconnaissance est trop ancienne.
  useEffect(() => {
    const id = setInterval(() => {
      const fresh = (statusRef.current?.settings?.fresh_seconds || 60) * 1000;
      setWho((w) => (w && Date.now() - w.ts > fresh ? null : w));
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const hasVoice = !!(status?.settings?.voice_id && ready(status) && status.profiles.some((p) => p.voice > 0));
  const hasFace = !!(status?.settings?.face_id && faceReady(status) && status.profiles.some((p) => p.face > 0));

  // Boucle caméra : une image toutes les 3 s tant que « me reconnaître avec la caméra » est activé.
  useEffect(() => {
    if (!hasFace) { faceRef.current = null; return undefined; }
    let stopped = false, stream = null, timer = null;
    const video = document.createElement("video");
    video.muted = true; video.playsInline = true;
    async function tick() {
      if (stopped) return;
      try {
        if (video.videoWidth) {
          const sc = Math.min(1, 480 / video.videoWidth);
          const c = document.createElement("canvas");
          c.width = Math.round(video.videoWidth * sc); c.height = Math.round(video.videoHeight * sc);
          c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
          const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.8));
          const res = await postBinary("/api/identity/identify/face", blob, 8000);
          if (res.name && res.token) {
            faceRef.current = { token: res.token, name: res.name, ts: Date.now() };
            setWho({ name: res.name, source: "face", ts: Date.now() });
          }
        }
      } catch { /* caméra ou serveur momentanément indisponible */ }
      if (!stopped) timer = setTimeout(tick, 3000);
    }
    navigator.mediaDevices?.getUserMedia({ video: { width: 640, height: 480 } })
      .then(async (s) => { if (stopped) { s.getTracks().forEach((t) => t.stop()); return; } stream = s; video.srcObject = s; await video.play(); tick(); })
      .catch(() => {});
    return () => { stopped = true; clearTimeout(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, [hasFace]);

  const freshFace = () => {
    const f = [liveRef.current, faceRef.current].filter(Boolean).sort((a, b) => (b.live ? 1 : 0) - (a.live ? 1 : 0))[0];
    const fresh = (statusRef.current?.settings?.fresh_seconds || 60) * 1000;
    return f && Date.now() - f.ts < fresh ? f : null;
  };

  // Jeton à joindre à une phrase dite : voix reconnue, sinon visage vu récemment. Jamais bloquant (2 s max).
  const forVoice = useCallback(async (blob) => {
    if (statusRef.current && ready(statusRef.current) && statusRef.current.settings.voice_id
        && statusRef.current.profiles.some((p) => p.voice > 0) && blob) {
      try {
        const res = await postBinary("/api/identity/identify/voice", blob, 2500);
        if (res.name && res.token) {
          voiceRef.current = { token: res.token, name: res.name, ts: Date.now() };
          setWho({ name: res.name, source: "voice", ts: Date.now() });
          return res.token;
        }
        setWho(null);
      } catch { /* on continue sans identification */ }
    }
    return freshFace()?.token || null;
  }, []);

  // Pour un message tapé : seulement le visage (si la caméra reconnaît quelqu'un).
  const forText = useCallback(() => freshFace()?.token || null, []);

  // Vérification « visage vivant » réussie : jeton de confiance pour les prochaines phrases.
  const acceptLive = useCallback((name, token) => {
    liveRef.current = { token, name, ts: Date.now(), live: true };
    setWho({ name, source: "face-live", ts: Date.now() });
  }, []);
  // Indice du serveur (style d'écriture) : on l'affiche, c'est tout.
  const hint = useCallback((name, source) => setWho({ name, source, ts: Date.now() }), []);

  const canVerify = !!(status && faceReady(status) && status.profiles.some((p) => p.face > 0));

  return { status, canVerify, who, forVoice, forText, refresh, acceptLive, hint };
}
