import { useCallback, useEffect, useState } from "react";

const KEY = "eva.voice.prefs";
const DEFAULTS = { speakAll: false, wake: false, word: "eva", voice: "", rate: 1, engine: "local", tts: "local", browserVoice: "", gestures: false, voixLangues: {} };

export function read() {
  try { return { ...DEFAULTS, ...JSON.parse(window.localStorage.getItem(KEY) || "{}") }; } catch { return { ...DEFAULTS }; }
}

// Préférences vocales, partagées entre la barre de contrôle et Paramètres (même onglet : événement dédié).
export function useVoicePrefs() {
  const [prefs, setPrefs] = useState(read);
  useEffect(() => {
    const sync = () => setPrefs(read());
    window.addEventListener("eva-voice-prefs", sync);
    return () => window.removeEventListener("eva-voice-prefs", sync);
  }, []);
  const update = useCallback((patch) => {
    const next = { ...read(), ...patch };
    try { window.localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* stockage indisponible */ }
    setPrefs(next);
    window.dispatchEvent(new Event("eva-voice-prefs"));
  }, []);
  return [prefs, update];
}
