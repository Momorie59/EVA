import { useCallback, useRef, useState } from "react";
import { VOICE_URL, authHeaders } from "../urls";
import { cleanForSpeech, encodeWav, splitSentences } from "../voice/speech";
import { read as readVoicePrefs } from "./useVoicePrefs";
import { cancelNative, createRecognizer, nativeSttSupported, nativeTtsSupported, speakNative } from "../voice/native";
import { record } from "../voice/latency";

// Dernière langue entendue par Whisper (3 min) : la voix de la réponse suit la langue de la personne.
let heardLang = null;



async function httpDetail(res, what) {
  let detail = "";
  try { detail = (await res.json()).detail || ""; } catch { /* corps non JSON */ }
  return `${what} : ${detail || `réponse ${res.status}`}`;
}

export function useVoice({ onTranscript, onSpeakEnd }) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState("");
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const recogRef = useRef(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const startRecording = useCallback(async () => {
    // Moteur du navigateur : pas d'enregistrement ni d'envoi à Whisper, le texte arrive directement.
    if (readVoicePrefs().engine === "browser" && nativeSttSupported()) {
      const t0 = performance.now();
      let got = false;
      recogRef.current = createRecognizer({
        continuous: false,
        onFinal: (text) => { got = true; record("stt", performance.now() - t0); onTranscriptRef.current(text, null); },
        onError: (e) => setError(`Reconnaissance du navigateur : ${e}`),
        onEnd: () => { setIsRecording(false); if (!got) setError((x) => x || "Je n'ai rien entendu."); },
      });
      setError("");
      recogRef.current.start();
      setIsRecording(true);
      return true;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.error("Micro inaccessible :", err);
      setError("Micro inaccessible : autorise-le dans le navigateur (adresse en https://).");
      return false;
    }

    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      let blob = new Blob(chunksRef.current, { type: "audio/webm" });
      let filename = "recording.webm";
      // On convertit en WAV 16 kHz dans le navigateur : le serveur n'a plus rien à décoder (pas de dépendance à ffmpeg/PyAV).
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        const ctx = new Ctx();
        const audio = await ctx.decodeAudioData(await blob.arrayBuffer());
        ctx.close();
        blob = encodeWav(audio.getChannelData(0), audio.sampleRate);
        filename = "recording.wav";
      } catch (e) {
        console.warn("Conversion WAV impossible, envoi du format brut :", e);
      }

      const formData = new FormData();
      formData.append("audio", blob, filename);

      const sttStart = performance.now();
      try {
        const res = await fetch(`${VOICE_URL}/stt`, {
          method: "POST",
          headers: authHeaders(),
          body: formData,
        });
        if (!res.ok) throw new Error(await httpDetail(res, "Reconnaissance vocale"));
        const data = await res.json();
        setError("");
        record("stt", performance.now() - sttStart);
        if (data.language) heardLang = { code: data.language, at: Date.now() };   // langue entendue : guide la voix de la réponse
        if (data.text?.trim()) onTranscript(data.text.trim(), blob);
        else setError("Je n'ai rien entendu.");
      } catch (err) {
        console.error("Erreur STT :", err);
        setError(err.message || "Erreur de reconnaissance vocale");
      }
    };

    recorder.start();
    mediaRecorderRef.current = recorder;
    setIsRecording(true);
    return true;
  }, [onTranscript]);

  const stopRecording = useCallback(() => {
    if (recogRef.current) { recogRef.current.stop(); recogRef.current = null; setIsRecording(false); return; }
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }, []);

  // Lecture à voix haute au fil de l'eau : une file de phrases ; la synthèse de la suivante se prépare
  // pendant qu'on lit la courante. `enqueue` peut être appelé dès que la 1re phrase de la réponse existe.
  const [isSpeaking, setIsSpeaking] = useState(false);
  const queueRef = useRef([]);          // [{ text, p: Promise<url>|null }]
  const runningRef = useRef(false);
  const runIdRef = useRef(0);
  const audioRef = useRef(null);
  const onSpeakEndRef = useRef(onSpeakEnd);
  onSpeakEndRef.current = onSpeakEnd;

  const firstEnqAt = useRef(0);
  const synth = (item) => {
    if (!item.p) {
      const prefs = readVoicePrefs();
      item.p = fetch(`${VOICE_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ text: item.text, voice: prefs.voice || undefined, speed: Number(prefs.rate) || undefined,
          lang: heardLang && Date.now() - heardLang.at < 180000 ? heardLang.code : undefined,
          voix_langues: prefs.voixLangues && Object.keys(prefs.voixLangues).length ? prefs.voixLangues : undefined }),
      }).then(async (res) => {
        if (!res.ok) throw new Error(await httpDetail(res, "Synthèse vocale"));
        return URL.createObjectURL(await res.blob());
      });
      item.p.catch(() => {});
    }
    return item.p;
  };

  const runQueue = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    const run = runIdRef.current;
    setIsSpeaking(true);
    try {
      while (queueRef.current.length && run === runIdRef.current) {
        const item = queueRef.current[0];
        const next = queueRef.current[1];
        if (readVoicePrefs().tts === "browser" && nativeTtsSupported()) {
          queueRef.current.shift();
          await speakNative(item.text, {
            voice: readVoicePrefs().browserVoice, rate: readVoicePrefs().rate,
            lang: heardLang && Date.now() - heardLang.at < 180000 ? heardLang.code : "",
            onStart: () => { if (firstEnqAt.current) { record("tts", performance.now() - firstEnqAt.current); firstEnqAt.current = 0; } },
          });
          continue;
        }
        const urlPromise = synth(item);
        if (next) synth(next);                         // prépare la suivante pendant la lecture
        let url;
        try { url = await urlPromise; } catch (err) { setError(err.message || "Erreur de synthèse vocale"); queueRef.current.shift(); continue; }
        if (run !== runIdRef.current) { URL.revokeObjectURL(url); break; }
        queueRef.current.shift();
        await new Promise((resolve) => {
          const audio = new Audio(url);
          audioRef.current = audio;
          audio.onended = audio.onerror = () => { URL.revokeObjectURL(url); resolve(); };
          if (firstEnqAt.current) { record("tts", performance.now() - firstEnqAt.current); firstEnqAt.current = 0; }
          audio.play().catch(resolve);
        });
      }
    } finally {
      if (run === runIdRef.current) {
        runningRef.current = false;
        audioRef.current = null;
        setIsSpeaking(false);
        onSpeakEndRef.current?.();
      }
    }
  }, []);

  const enqueue = useCallback((text) => {
    const clean = cleanForSpeech(text);
    if (!clean) return;
    if (!runningRef.current) firstEnqAt.current = performance.now();
    for (const chunk of splitSentences(clean)) queueRef.current.push({ text: chunk, p: null });
    if (queueRef.current.length > 40) queueRef.current.length = 40;
    runQueue();
  }, [runQueue]);

  const stopSpeaking = useCallback(() => {
    runIdRef.current += 1;
    queueRef.current = [];
    cancelNative();
    try { audioRef.current?.pause(); } catch { /* rien */ }
    audioRef.current = null;
    runningRef.current = false;
    setIsSpeaking(false);
  }, []);

  // Lecture d'un texte complet (anciennes utilisations : message proactif, échantillons).
  const speak = useCallback((text) => { enqueue(text); }, [enqueue]);

  return { isRecording, startRecording, stopRecording, speak, enqueue, stopSpeaking, isSpeaking, error };
}
