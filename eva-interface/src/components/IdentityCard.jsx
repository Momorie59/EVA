import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { IDENTITY_EVENT, postBinary } from "../hooks/useIdentity";
import { encodeWav } from "../voice/speech";
import { confirmer } from "../confirmer";

const PHRASES = [
  "Bonjour EVA, c'est moi, quelle est la météo aujourd'hui ?",
  "Allume la lumière du salon et dis-moi quelle heure il est.",
  "Peux-tu me lire mes derniers messages importants s'il te plaît ?",
];
const changed = () => window.dispatchEvent(new Event(IDENTITY_EVENT));

// Enregistre quelques secondes au micro et renvoie un WAV 16 kHz mono.
async function recordWav(ms) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false } });
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx({ sampleRate: 16000 });
  const src = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  src.connect(proc); proc.connect(ctx.destination);
  await new Promise((r) => setTimeout(r, ms));
  proc.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop());
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const all = new Float32Array(total); let o = 0;
  for (const c of chunks) { all.set(c, o); o += c.length; }
  const rate = ctx.sampleRate; ctx.close();
  return encodeWav(all, rate);
}

export default function IdentityCard() {
  const [st, setSt] = useState(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [cam, setCam] = useState(null); // nom du profil en cours d'enregistrement de visage (ou "__test")
  const [styleFor, setStyleFor] = useState(null);
  const [styleText, setStyleText] = useState("");
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const load = () => api("/api/identity/status").then(setSt).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!st?.download?.running) return undefined;
    const id = setInterval(load, 1500);
    return () => clearInterval(id);
  }, [st?.download?.running]);
  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  const run = async (label, fn) => {
    setBusy(label); setError(""); setMsg("");
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(""); await load(); changed();
  };

  const enrollVoice = (p, n) => run("voice", async () => {
    setMsg(`Dis : « ${PHRASES[n % PHRASES.length]} » (4 secondes, maintenant)`);
    const wav = await recordWav(4200);
    const r = await postBinary(`/api/identity/enroll/voice?name=${encodeURIComponent(p)}`, wav);
    setMsg(`Échantillon de voix ajouté (${r.samples}). Recommence avec une autre phrase : 3 échantillons donnent une bonne reconnaissance.`);
  });
  const testVoice = () => run("voice", async () => {
    setMsg("Dis une phrase (3 secondes)…");
    const r = await postBinary("/api/identity/identify/voice", await recordWav(3200));
    setMsg(r.name ? `Voix reconnue : ${r.name} (similarité ${r.score}).` : r.enrolled ? `Voix inconnue (similarité ${r.score}).` : "Aucune voix enregistrée.");
  });

  async function openCam(target) {
    setError("");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      streamRef.current = s; setCam(target);
      setTimeout(async () => { if (videoRef.current) { videoRef.current.srcObject = s; await videoRef.current.play().catch(() => {}); } }, 50);
    } catch (e) { setError("Caméra inaccessible : " + e.message); }
  }
  function closeCam() { streamRef.current?.getTracks().forEach((t) => t.stop()); streamRef.current = null; setCam(null); }
  async function shot() {
    const v = videoRef.current; if (!v?.videoWidth) return null;
    const c = document.createElement("canvas"); c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    return new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
  }
  const snap = () => run("face", async () => {
    const blob = await shot(); if (!blob) throw new Error("La caméra n'est pas prête.");
    if (cam === "__test") {
      const r = await postBinary("/api/identity/identify/face", blob);
      setMsg(r.faces === 0 ? "Aucun visage détecté." : r.name ? `Visage reconnu : ${r.name} (similarité ${r.score}).` : r.enrolled ? `Visage inconnu (similarité ${r.score}).` : "Aucun visage enregistré.");
    } else {
      const r = await postBinary(`/api/identity/enroll/face?name=${encodeURIComponent(cam)}`, blob);
      setMsg(`Photo ajoutée (${r.samples}). Change un peu d'angle / d'éclairage et recommence 2 ou 3 fois.`);
    }
  });

  const addStyle = () => run("style", async () => {
    const r = await postBinary(`/api/identity/enroll/style?name=${encodeURIComponent(styleFor)}`, new Blob([styleText], { type: "text/plain; charset=utf-8" }));
    setStyleText("");
    setMsg(`Texte appris (${r.samples}/5 minimum). Le texte n'est pas conservé, seulement ses statistiques.`);
  });
  const setSetting = (patch) => run("set", () => api("/api/identity/settings", { method: "PUT", body: JSON.stringify(patch) }));
  const s = st?.settings;
  const libsOk = st && Object.values(st.libs).every(Boolean);
  const modelsOk = st && Object.values(st.models).every(Boolean);

  return (
    <div className="card routercard" data-testid="identity-card">
      <span className="card__label">Reconnaissance des personnes (voix et visage)</span>
      <p className="page__sub">
        EVA peut reconnaître qui lui parle (comme une enceinte connectée) et qui est devant la caméra, pour t'appeler par ton prénom et
        limiter ce qu'une voix inconnue peut faire. Tout reste <strong>sur ton NAS</strong> : seules des empreintes numériques sont stockées
        (ni enregistrement audio, ni photo) et tu peux les effacer à tout moment. <strong>Ce n'est pas une sécurité forte</strong> : une voix peut être
        imitée ou enregistrée. Les actions sensibles demandent toujours ta confirmation.
      </p>

      {st && !libsOk && <p className="page__warn">Bibliothèques absentes d'EVA CORE ({Object.entries(st.libs).filter(([, v]) => !v).map(([k]) => k).join(", ")}) : lance <code>docker compose build eva-core</code> puis relance.</p>}
      {st && libsOk && !modelsOk && (
        <div className="agentform__actions">
          <button className="btn btn--primary" disabled={st.download.running} onClick={() => run("dl", () => api("/api/identity/models/download", { method: "POST" }))}>
            {st.download.running ? "Téléchargement en cours…" : "Télécharger les modèles (≈ 70 Mo, une seule fois)"}
          </button>
          {st.download.error && <span className="page__warn">{st.download.error}</span>}
        </div>
      )}

      {st && libsOk && modelsOk && (
        <>
          <ul className="backuplist idlist">
            {st.profiles.map((p) => (
              <li key={p.name} className="idrow">
                <strong>{p.name}</strong>
                <span>voix : {p.voice} · visage : {p.face} · style : {p.style}</span>
                <span className="idrow__btns">
                  <button className="btn" disabled={!!busy} onClick={() => enrollVoice(p.name, p.voice)}>🎙 Enregistrer ma voix</button>
                  <button className="btn" disabled={!!busy} onClick={() => openCam(p.name)}>📷 Enregistrer mon visage</button>
                  {p.voice > 0 && <button className="btn" onClick={() => run("x", () => api(`/api/identity/profiles/${encodeURIComponent(p.name)}?kind=voice`, { method: "DELETE" }))}>Effacer la voix</button>}
                  <button className="btn" disabled={!!busy} onClick={() => { setStyleFor(p.name); setStyleText(""); }}>✍ Apprendre mon style d'écriture</button>
                  {p.style > 0 && <button className="btn" onClick={() => run("x", () => api(`/api/identity/profiles/${encodeURIComponent(p.name)}?kind=style`, { method: "DELETE" }))}>Effacer le style</button>}
                  {p.face > 0 && <button className="btn" onClick={() => run("x", () => api(`/api/identity/profiles/${encodeURIComponent(p.name)}?kind=face`, { method: "DELETE" }))}>Effacer le visage</button>}
                  <button className="btn" onClick={() => confirmer(`Supprimer le profil ${p.name} et ses empreintes ?`).then((ok) => ok && (run("x", () => api(`/api/identity/profiles/${encodeURIComponent(p.name)}`, { method: "DELETE" }))))}>Supprimer</button>
                </span>
              </li>
            ))}
          </ul>
          <form className="agentform__actions" onSubmit={(e) => { e.preventDefault(); if (name.trim()) run("add", async () => { await api("/api/identity/profiles", { method: "POST", body: JSON.stringify({ name }) }); setName(""); }); }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Prénom de la personne à enregistrer" maxLength={40} />
            <button className="btn btn--primary" type="submit" disabled={!name.trim() || !!busy}>Ajouter</button>
            <button className="btn" type="button" disabled={!!busy} onClick={testVoice}>Tester ma voix</button>
            <button className="btn" type="button" disabled={!!busy} onClick={() => openCam("__test")}>Tester mon visage</button>
          </form>

          {styleFor && (
            <div className="idcam">
              <p className="page__sub">Écris comme tu écris d'habitude à EVA (2 ou 3 phrases), puis « Ajouter ». Répète au moins 5 fois, avec des sujets différents. La reconnaissance par le style ne marche qu'entre personnes enregistrées (au moins deux) et reste un indice faible.</p>
              <textarea value={styleText} onChange={(e) => setStyleText(e.target.value)} rows={4} placeholder={`Message de ${styleFor}…`} style={{ width: "100%" }} />
              <div className="agentform__actions">
                <button className="btn btn--primary" disabled={!!busy || styleText.trim().length < 20} onClick={addStyle}>Ajouter</button>
                <button className="btn" onClick={() => setStyleFor(null)}>Terminer</button>
              </div>
            </div>
          )}

          {cam && (
            <div className="idcam">
              <video ref={videoRef} playsInline muted />
              <div className="agentform__actions">
                <button className="btn btn--primary" disabled={!!busy} onClick={snap}>{cam === "__test" ? "Tester" : "Prendre la photo"}</button>
                <button className="btn" onClick={closeCam}>Fermer la caméra</button>
              </div>
            </div>
          )}

          {s && (
            <div className="idsettings">
              <label><input type="checkbox" checked={s.voice_id} onChange={(e) => setSetting({ voice_id: e.target.checked })} /> Reconnaître les gens à leur voix</label>
              <label><input type="checkbox" checked={s.face_id} onChange={(e) => setSetting({ face_id: e.target.checked })} /> Reconnaître la personne devant la caméra (la caméra reste allumée sur cette page)</label>
              <label><input type="checkbox" checked={s.face_liveness} onChange={(e) => setSetting({ face_liveness: e.target.checked })} /> Exiger la vérification « visage vivant » (tourner la tête) pour qu'un visage lève les restrictions — bouton « 🔒 Me présenter » ou dis « EVA, c'est moi »</label>
              <label><input type="checkbox" checked={s.style_id} onChange={(e) => setSetting({ style_id: e.target.checked })} /> Deviner qui écrit d'après sa façon d'écrire (indice faible, entre personnes enregistrées, jamais utilisé pour donner des accès)</label>
              <label><input type="checkbox" checked={s.restrict_unknown} onChange={(e) => setSetting({ restrict_unknown: e.target.checked })} /> Voix inconnue = invité : seulement météo, recherche web et état du système (pas de mails, fichiers, domotique…)</label>
              <label>Exigence voix : {s.voice_threshold.toFixed(2)} <input type="range" min="0.4" max="0.85" step="0.01" value={s.voice_threshold} onChange={(e) => setSt({ ...st, settings: { ...s, voice_threshold: +e.target.value } })} onMouseUp={(e) => setSetting({ voice_threshold: +e.target.value })} onTouchEnd={(e) => setSetting({ voice_threshold: +e.target.value })} onKeyUp={(e) => setSetting({ voice_threshold: +e.target.value })} /></label>
              <label>Exigence visage : {s.face_threshold.toFixed(2)} <input type="range" min="0.25" max="0.6" step="0.01" value={s.face_threshold} onChange={(e) => setSt({ ...st, settings: { ...s, face_threshold: +e.target.value } })} onMouseUp={(e) => setSetting({ face_threshold: +e.target.value })} onTouchEnd={(e) => setSetting({ face_threshold: +e.target.value })} onKeyUp={(e) => setSetting({ face_threshold: +e.target.value })} /></label>
              <p className="page__sub">Plus l'exigence est haute, moins EVA se trompe de personne, mais plus elle te demande de répéter. Utilise « Tester » pour régler.</p>
            </div>
          )}
        </>
      )}
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
