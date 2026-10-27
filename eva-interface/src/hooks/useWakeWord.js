import { useCallback, useEffect, useRef, useState } from "react";
import { VOICE_URL, authHeaders } from "../urls";
import { encodeWav, isHallucination, matchWake } from "../voice/speech";
import { record } from "../voice/latency";
import { createRecognizer, nativeSttSupported } from "../voice/native";

// Écoute continue : détecte la parole (VAD par énergie, dans le navigateur), envoie chaque phrase à
// Whisper local (/voice/stt) et ne réagit que si elle commence par le mot d'éveil. Rien n'est conservé,
// rien ne sort du réseau local. Mis en pause pendant que EVA parle (pas d'écho) ou réfléchit.
const AWAKE_MS = 8000;
const MIN_SPEECH_MS = 300;
const MAX_SPEECH_MS = 12000;
const END_SILENCE_MS = 650;
const PREROLL_MS = 350;
const GRACE_MS = 500;        // après la fin d'une lecture : on ignore l'écho résiduel d'EVA
const STT_TIMEOUT_MS = 20000; // jamais bloqué indéfiniment en attendant Whisper

function beep(ctx, freq = 880) {
  try {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = freq; g.gain.value = 0.05;
    o.connect(g); g.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.12);
  } catch { /* son facultatif */ }
}

export function useWakeWord({ enabled, word, paused, onCommand, engine = "local" }) {
  const [phase, setPhase] = useState("off"); // off | sleep | awake | sending
  const [error, setError] = useState("");
  const [heard, setHeard] = useState("");
  const [level, setLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [needsGesture, setNeedsGesture] = useState(false);
  const phaseRef = useRef("off");
  const pausedRef = useRef(paused);
  const awakeTimer = useRef(null);
  const onCommandRef = useRef(onCommand);
  const wordRef = useRef(word);
  const ctxRef = useRef(null);
  onCommandRef.current = onCommand;
  wordRef.current = word;
  pausedRef.current = paused;

  const setPh = (p) => { phaseRef.current = p; setPhase(p); };

  const wake = useCallback((ms = AWAKE_MS, withBeep = true) => {
    clearTimeout(awakeTimer.current);
    if (withBeep && ctxRef.current) beep(ctxRef.current);
    setPh("awake");
    awakeTimer.current = setTimeout(() => { if (phaseRef.current === "awake") setPh("sleep"); }, ms);
  }, []);

  // Fenêtre d'écoute de suivi, rouverte après chaque réponse parlée.
  const listenAgain = useCallback((ms = 6000) => {
    if (phaseRef.current !== "off") wake(ms, false);
  }, [wake]);

  useEffect(() => {
    if (!enabled) { setPh("off"); return undefined; }
    let stopped = false;

    // Moteur du navigateur : reconnaissance continue native (rapide, comme l'appli Android), sans VAD ni Whisper.
    if (engine === "browser" && nativeSttSupported()) {
      let running = false, resumeAt = 0, wasPaused = false;
      const decide = (text) => {
        setHeard(text || "…");
        if (isHallucination(text)) return;
        const awake = phaseRef.current === "awake";
        const m = matchWake(text, wordRef.current);
        if (m.woke && m.command) {
          clearTimeout(awakeTimer.current); setPh("sleep"); onCommandRef.current?.(m.command, null);
        } else if (m.woke) wake(AWAKE_MS, false);
        else if (awake) { clearTimeout(awakeTimer.current); setPh("sleep"); onCommandRef.current?.(text, null); }
      };
      const rec = createRecognizer({
        continuous: true,
        onFinal: (text) => { if (!pausedRef.current) { setError(""); decide(text); } },
        onInterim: (t) => setHeard(t),
        onError: (e) => setError(e === "not-allowed" ? "Micro refusé : autorise-le dans le navigateur (HTTPS requis)." : `Reconnaissance du navigateur : ${e}`),
        onEnd: () => { running = false; },
      });
      const tick = setInterval(() => {
        if (pausedRef.current) { wasPaused = true; if (running) { rec.abort(); running = false; } return; }
        if (wasPaused) { wasPaused = false; resumeAt = performance.now() + 700; }   // laisse l'écho d'EVA se dissiper
        if (!running && performance.now() >= resumeAt) { rec.start(); running = true; }
      }, 250);
      setPh("sleep");
      return () => {
        stopped = true; clearInterval(tick); clearTimeout(awakeTimer.current);
        rec.abort(); setPh("off");
      };
    }

    let stream, ctx, proc, src;
    let inFlight = false;

    async function transcribe(blob) {
      const fd = new FormData();
      fd.append("audio", blob, "wake.wav");
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), STT_TIMEOUT_MS);
      try {
        const t0 = performance.now();
        const res = await fetch(`${VOICE_URL}/stt?mode=fast`, { method: "POST", headers: authHeaders(), body: fd, signal: ctrl.signal });
        if (!res.ok) {
          let d = ""; try { d = (await res.json()).detail || ""; } catch { /* corps non JSON */ }
          throw new Error(`Reconnaissance vocale : ${d || `réponse ${res.status}`}`);
        }
        const out = ((await res.json()).text || "").trim();
        record("stt", performance.now() - t0);
        return out;
      } catch (e) {
        throw new Error(e.name === "AbortError" ? "Reconnaissance vocale trop lente (plus de 20 s)." : e.message);
      } finally { clearTimeout(timer); }
    }

    let pending = null;
    async function handleSegment(blob) {
      if (stopped) return;
      if (inFlight) { pending = blob; return; }   // on garde la plus récente au lieu de la perdre
      inFlight = true;
      setBusy(true);
      const before = phaseRef.current;
      try {
        const text = await transcribe(blob);
        setError("");
        if (stopped) return;
        setHeard(text || "…");
        if (isHallucination(text)) return;
        const awake = before === "awake" || phaseRef.current === "awake";
        const m = matchWake(text, wordRef.current);
        if (m.woke && m.command && !isHallucination(m.command)) {
          clearTimeout(awakeTimer.current); setPh("sleep");
          if (ctxRef.current) beep(ctxRef.current, 660);
          onCommandRef.current?.(m.command, blob);
        } else if (m.woke) {
          wake();
        } else if (awake) {
          clearTimeout(awakeTimer.current); setPh("sleep");
          onCommandRef.current?.(text, blob);
        }
      } catch (e) {
        setError(e.message || "Erreur de reconnaissance vocale");
      } finally {
        inFlight = false;
        setBusy(false);
        if (pending && !stopped) { const next = pending; pending = null; handleSegment(next); }
      }
    }

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      } catch (e) {
        setError("Micro inaccessible : autorise-le dans le navigateur (HTTPS requis).");
        setPh("off");
        return;
      }
      if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      ctxRef.current = ctx;
      // Après un rechargement, le navigateur laisse l'audio « suspendu » tant que l'utilisateur n'a pas cliqué.
      const resume = () => ctx.resume().then(() => setNeedsGesture(ctx.state === "suspended")).catch(() => {});
      if (ctx.state === "suspended") {
        setNeedsGesture(true);
        ctx.resume().then(() => setNeedsGesture(ctx.state === "suspended")).catch(() => {});
        document.addEventListener("pointerdown", resume, { once: true });
        document.addEventListener("keydown", resume, { once: true });
      }
      src = ctx.createMediaStreamSource(stream);
      proc = ctx.createScriptProcessor(2048, 1, 1);
      const rate = ctx.sampleRate;
      const prerollMax = Math.ceil((PREROLL_MS / 1000) * rate / 2048);
      let preroll = [], speech = [], speaking = false, loud = 0, silentMs = 0, speechMs = 0, floor = 0.004, lastLevelAt = 0, resumeAt = 0, wasPaused = false;

      proc.onaudioprocess = (ev) => {
        const data = new Float32Array(ev.inputBuffer.getChannelData(0));
        const frameMs = (data.length / rate) * 1000;
        if (pausedRef.current || phaseRef.current === "off") { preroll = []; speech = []; speaking = false; loud = 0; wasPaused = true; return; }
        if (wasPaused) { wasPaused = false; resumeAt = performance.now() + GRACE_MS; }
        if (performance.now() < resumeAt) { preroll = []; return; }
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        const thr = Math.max(0.01, floor * 3.5);
        const nowMs = performance.now();
        if (nowMs - lastLevelAt > 120) { lastLevelAt = nowMs; setLevel(rms); }
        if (!speaking) {
          floor = floor * 0.95 + rms * 0.05;
          preroll.push(data); if (preroll.length > prerollMax) preroll.shift();
          loud = rms > thr ? loud + 1 : 0;
          if (loud >= 2) { speaking = true; speech = [...preroll]; speechMs = 0; silentMs = 0; }
        } else {
          speech.push(data); speechMs += frameMs;
          silentMs = rms > thr * 0.7 ? 0 : silentMs + frameMs;
          if (silentMs >= END_SILENCE_MS || speechMs >= MAX_SPEECH_MS) {
            const total = speech.reduce((n, a) => n + a.length, 0);
            const all = new Float32Array(total);
            let o = 0; for (const a of speech) { all.set(a, o); o += a.length; }
            const ok = speechMs - silentMs >= MIN_SPEECH_MS;
            speaking = false; speech = []; preroll = []; loud = 0;
            if (ok) handleSegment(encodeWav(all, rate));
          }
        }
      };
      src.connect(proc);
      proc.connect(ctx.destination); // nécessaire pour que le traitement tourne ; la sortie est muette
      setPh("sleep");
    })();

    return () => {
      stopped = true;
      clearTimeout(awakeTimer.current);
      try { proc && (proc.onaudioprocess = null); src?.disconnect(); proc?.disconnect(); } catch { /* rien */ }
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
      ctxRef.current = null;
      setPh("off");
    };
  }, [enabled, wake, engine]);

  return { level, busy, phase, error: error || (enabled && needsGesture ? "Clique n'importe où sur la page pour activer l'écoute." : ""), heard, listenAgain };
}
