import { useState } from "react";
import { VOICE_URL, authHeaders } from "../urls";
import { encodeWav, matchWake } from "../voice/speech";

const ICON = { ok: "✅", ko: "❌", run: "⏳" };

async function detail(res) {
  try { return (await res.json()).detail || `réponse ${res.status}`; } catch { return `réponse ${res.status}`; }
}

// Teste chaque maillon de la chaîne vocale et dit lequel casse.
export default function VoiceDiagnostic({ word }) {
  const [rows, setRows] = useState([]);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    const out = [];
    const push = (label, status, msg = "") => { out.push({ label, status, msg }); setRows([...out]); };
    const upd = (status, msg) => { out[out.length - 1] = { ...out[out.length - 1], status, msg }; setRows([...out]); };

    push("Page sécurisée (HTTPS)", window.isSecureContext && navigator.mediaDevices ? "ok" : "ko",
      window.isSecureContext && navigator.mediaDevices ? "" : "Le micro n'est autorisé qu'en https:// (ex. https://IP-du-NAS:8443), jamais en http://.");

    push("Service voix (eva-voice)", "run");
    try {
      const res = await fetch(`${VOICE_URL}/api/health`);
      if (!res.ok) throw new Error(`réponse ${res.status}`);
      const h = await res.json();
      upd(h.piper_voice_present ? "ok" : "ko",
        h.piper_voice_present ? `Whisper « ${h.whisper_model} », voix « ${h.piper_voice} ».`
          : `Voix « ${h.piper_voice} » absente du dossier eva-voice/models : elle se télécharge toute seule au démarrage d'eva-voice si internet est joignable (sinon : MANUEL-INSTALLATION.md, §3.3).`);
    } catch (e) { upd("ko", `Injoignable (${e.message}). Vérifie : docker compose ps, et docker compose logs eva-voice.`); }

    push("Synthèse vocale (EVA parle)", "run");
    try {
      const res = await fetch(`${VOICE_URL}/tts`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ text: "Bonjour, je suis Éva. Tu m'entends bien ?" }) });
      if (!res.ok) throw new Error(await detail(res));
      const url = URL.createObjectURL(await res.blob());
      const a = new Audio(url); a.onended = () => URL.revokeObjectURL(url);
      await a.play();
      upd("ok", "Tu dois entendre « Bonjour, je suis Éva ». Sinon, vérifie le volume de l'ordinateur.");
    } catch (e) { upd("ko", e.message); }

    push("Micro", "run");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      upd("ok", "Micro accessible.");
    } catch (e) { upd("ko", "Accès refusé ou aucun micro : autorise-le (cadenas de la barre d'adresse)."); setRunning(false); return; }

    push("Reconnaissance : dis maintenant « " + word + ", bonjour » (4 s)", "run");
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(2048, 1, 1);
      const chunks = []; let peak = 0;
      proc.onaudioprocess = (ev) => {
        const d = new Float32Array(ev.inputBuffer.getChannelData(0)); chunks.push(d);
        for (let i = 0; i < d.length; i++) peak = Math.max(peak, Math.abs(d[i]));
      };
      src.connect(proc); proc.connect(ctx.destination);
      await new Promise((r) => setTimeout(r, 4000));
      src.disconnect(); proc.disconnect(); stream.getTracks().forEach((t) => t.stop());
      const rate = ctx.sampleRate; ctx.close();
      if (peak < 0.02) { upd("ko", "Micro muet (niveau ≈ 0) : mauvais micro sélectionné, ou micro coupé dans le système."); setRunning(false); return; }
      const all = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
      let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
      const fd = new FormData(); fd.append("audio", encodeWav(all, rate), "diag.wav");
      const res = await fetch(`${VOICE_URL}/stt?mode=fast`, { method: "POST", headers: authHeaders(), body: fd });
      if (!res.ok) throw new Error(await detail(res));
      const text = ((await res.json()).text || "").trim();
      const m = matchWake(text, word);
      upd(text ? "ok" : "ko", text ? `J'ai compris : « ${text} » — mot d'éveil ${m.woke ? "reconnu ✔" : "non reconnu (dis « " + word + " » au début)"}.` : "Rien compris : parle plus fort / plus près.");
    } catch (e) { upd("ko", e.message + " (le premier appel télécharge le modèle Whisper : le serveur doit avoir Internet et ça peut prendre une minute — réessaie)."); }
    setRunning(false);
  }

  return (
    <div className="voicediag">
      <button className="btn" disabled={running} onClick={run}>{running ? "Test en cours…" : "Tester la voix"}</button>
      <ul>{rows.map((r, i) => <li key={i}><span>{ICON[r.status]}</span> <strong>{r.label}</strong>{r.msg && <div className="page__sub">{r.msg}</div>}</li>)}</ul>
    </div>
  );
}
