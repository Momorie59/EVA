// Voix « native » du navigateur (Web Speech API), comme dans l'appli Android : pas d'envoi de l'audio
// à Whisper, pas d'attente de synthèse Piper → bien plus rapide. Contrepartie : sous Chrome/Android,
// la reconnaissance passe par les serveurs de Google (le navigateur, pas EVA). C'est donc un choix, désactivé par défaut.
const SR = () => (typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null);

export const nativeSttSupported = () => !!SR();
export const nativeTtsSupported = () => typeof window !== "undefined" && "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance !== "undefined";

// Reconnaissance : { start, stop, abort }. onFinal(texte) à chaque phrase terminée ; onInterim(texte) en cours de route.
// continuous=true : relance automatiquement quand le navigateur coupe (silence, limite de durée).
export function createRecognizer({ lang = "fr-FR", continuous = false, onFinal, onInterim, onError, onEnd }) {
  const Ctor = SR();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = lang;
  rec.continuous = continuous;
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  let wanted = false;
  let t0 = 0;
  rec.onstart = () => { t0 = performance.now(); };
  rec.onresult = (ev) => {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const r = ev.results[i];
      const txt = (r[0]?.transcript || "").trim();
      if (r.isFinal) { if (txt) onFinal?.(txt, Math.round(performance.now() - t0)); }
      else interim += txt + " ";
    }
    if (interim.trim()) onInterim?.(interim.trim());
  };
  rec.onerror = (ev) => {
    if (ev.error === "no-speech" || ev.error === "aborted") return;
    if (ev.error === "not-allowed" || ev.error === "service-not-allowed") wanted = false;
    onError?.(ev.error);
  };
  rec.onend = () => {
    if (wanted && continuous) { try { rec.start(); } catch { /* déjà relancée */ } return; }
    wanted = false;
    onEnd?.();
  };
  return {
    start() { wanted = true; try { rec.start(); } catch { /* déjà démarrée */ } },
    stop() { wanted = false; try { rec.stop(); } catch { /* rien */ } },
    abort() { wanted = false; try { rec.abort(); } catch { /* rien */ } },
  };
}

export function listFrenchVoices() {
  if (!nativeTtsSupported()) return [];
  return window.speechSynthesis.getVoices().filter((v) => /^fr/i.test(v.lang)).map((v) => ({ id: v.voiceURI || v.name, label: `${v.name} (${v.lang})` }));
}

// Lit un texte ; résout à la fin (ou en cas d'erreur). `onStart` à l'attaque du son.
export function speakNative(text, { voice = "", rate = 1, onStart, lang = "" } = {}) {
  return new Promise((resolve) => {
    const u = new window.SpeechSynthesisUtterance(text);
    const autre = lang && !/^fr/i.test(lang);
    u.lang = autre ? lang : "fr-FR";          // une autre langue : le navigateur choisit une voix de cette langue
    u.rate = Number(rate) || 1;
    if (voice && !autre) {
      const v = window.speechSynthesis.getVoices().find((x) => (x.voiceURI || x.name) === voice);
      if (v) u.voice = v;
    }
    u.onstart = () => onStart?.();
    u.onend = u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}
export const cancelNative = () => { try { window.speechSynthesis.cancel(); } catch { /* rien */ } };
