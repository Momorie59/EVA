import { useEffect, useRef, useState } from "react";
import { createDetector } from "../gestures/classify";
import { createPointer } from "../gestures/pointer";

export const GESTURE_EVENT = "eva-gesture";
export const HAND_EVENT = "eva-hand";
const BASE = "/vendor/mediapipe";
const FPS_MS = 80;

// Pilotage à la main devant la caméra (MediaPipe, embarqué : aucune donnée ne quitte le navigateur, rien n'est enregistré).
async function loadLandmarker() {
  if (typeof window.__evaLandmarker === "function") return window.__evaLandmarker();   // point d'injection pour les tests
  const mp = await import(/* @vite-ignore */ `${BASE}/vision_bundle.mjs`);
  const files = await mp.FilesetResolver.forVisionTasks(`${BASE}/wasm`);
  const opts = (delegate) => ({ baseOptions: { modelAssetPath: `${BASE}/hand_landmarker.task`, delegate }, runningMode: "VIDEO", numHands: 2 });
  try { return await mp.HandLandmarker.createFromOptions(files, opts("GPU")); }
  catch { return mp.HandLandmarker.createFromOptions(files, opts("CPU")); }
}

export function useGestures({ enabled }) {
  const [state, setState] = useState("off");   // off | loading | ready | error
  const [error, setError] = useState("");
  const [last, setLast] = useState(null);
  const [handSeen, setHandSeen] = useState(false);
  const lastTimer = useRef(null);

  useEffect(() => {
    if (!enabled) { setState("off"); return undefined; }
    let stopped = false, stream, video, landmarker, raf;
    setState("loading"); setError("");
    (async () => {
      try {
        landmarker = await loadLandmarker();
        if (typeof window.__evaLandmarker !== "function") {
          stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, facingMode: "user" } });
        }
        if (stopped) { stream?.getTracks().forEach((t) => t.stop()); return; }
        video = document.createElement("video");
        video.muted = true; video.playsInline = true;
        if (stream) { video.srcObject = stream; await video.play(); }
        setState("ready");
        const step = createDetector();
        const pointer = createPointer();
        let prev = 0, lastVideoTime = -1;
        const loop = (now) => {
          if (stopped) return;
          raf = requestAnimationFrame(loop);
          if (now - prev < FPS_MS) return;
          prev = now;
          if (stream && (video.readyState < 2 || video.currentTime === lastVideoTime)) return;
          lastVideoTime = video.currentTime;
          let hands = [];
          try { hands = landmarker.detectForVideo(video, now)?.landmarks || []; } catch { hands = []; }
          const lm = hands[0] || null;
          const ph = pointer(now, hands);
          if (ph.hands.length || ph.events.length) window.dispatchEvent(new CustomEvent(HAND_EVENT, { detail: ph }));
          setHandSeen(ph.hands.length > 0);
          const g = step(now, hands.length >= 2 ? null : lm);   // à deux mains : zoom, pas de gestes isolés
          if (g) {
            window.dispatchEvent(new CustomEvent(GESTURE_EVENT, { detail: g }));
            setLast(g);
            clearTimeout(lastTimer.current);
            lastTimer.current = setTimeout(() => setLast(null), 1500);
          }
        };
        raf = requestAnimationFrame(loop);
      } catch (e) {
        if (stopped) return;
        setState("error");
        setError(e?.name === "NotAllowedError" ? "Caméra refusée : autorise-la dans le navigateur (HTTPS requis)." : `Gestes indisponibles : ${e?.message || e}`);
      }
    })();
    return () => {
      stopped = true; cancelAnimationFrame(raf); clearTimeout(lastTimer.current);
      stream?.getTracks().forEach((t) => t.stop());
      try { landmarker?.close?.(); } catch { /* rien */ }
    };
  }, [enabled]);

  return { state, error, last, handSeen };
}
