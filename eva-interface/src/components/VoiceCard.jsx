import { useVoicePrefs } from "../hooks/useVoicePrefs";
import { useEffect, useState } from "react";
import VoiceDiagnostic from "./VoiceDiagnostic";
import { VOICE_URL, authHeaders } from "../urls";
import { listFrenchVoices, nativeSttSupported, nativeTtsSupported, speakNative } from "../voice/native";
import { readLatency } from "../voice/latency";


const LANGUES_VOIX = [["fr", "🇫🇷 Français", "Bonsoir. Je suis Éva. Prends ton temps, je suis là."], ["it", "🇮🇹 Italien", "Buonasera. Sono Eva, sono qui per aiutarti."],
  ["en", "🇬🇧 Anglais", "Good evening. I'm Eva, I'm here to help."], ["es", "🇪🇸 Espagnol", "Buenas noches. Soy Eva, estoy aquí para ayudarte."],
  ["de", "🇩🇪 Allemand", "Guten Abend. Ich bin Eva und helfe dir gern."], ["pt", "🇵🇹 Portugais", "Boa noite. Sou a Eva, estou aqui para ajudar."],
  ["nl", "🇳🇱 Néerlandais", "Goedenavond. Ik ben Eva, ik help je graag."]];

// Une voix par langue : quand EVA parle italien, c'est cette voix-là (téléchargée une fois depuis le catalogue Piper).
function VoixParLangue({ prefs, update }) {
  const [listes, setListes] = useState({});
  const [msg, setMsg] = useState("");
  const choix = prefs.voixLangues || {};
  const charger = (l) => {
    if (listes[l]) return;
    fetch(`${VOICE_URL}/voix/langue/${l}`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`réponse ${r.status}`))))
      .then((d) => setListes((x) => ({ ...x, [l]: d.voix }))).catch((e) => setMsg(`Liste des voix indisponible (${e.message}) : mets eva-voice à jour.`));
  };
  async function choisir(l, v) {
    const n = { ...choix };
    if (v) n[l] = v; else delete n[l];
    update({ voixLangues: n });
    if (v && !(listes[l] || []).find((x) => x.id === v)?.installee) {
      await fetch(`${VOICE_URL}/voix/telecharger`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ voix: v }) }).catch(() => {});
      setMsg("Voix en cours de téléchargement (une fois, quelques Mo) : réessaie l'écoute dans une minute.");
    }
  }
  async function ecouter(l, phrase) {
    setMsg("");
    try {
      const res = await fetch(`${VOICE_URL}/tts`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ text: phrase, lang: l, voix_langues: choix, speed: Number(prefs.rate) || undefined, voice: prefs.voice || undefined }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `réponse ${res.status}`);
      const url = URL.createObjectURL(await res.blob()); const a = new Audio(url); a.onended = () => URL.revokeObjectURL(url); await a.play();
    } catch (e) { setMsg(e.message); }
  }
  return (
    <div className="voixlangues" data-testid="voix-langues">
      <span className="card__label">Voix par langue</span>
      <p className="page__sub">EVA répond dans la langue où on lui parle. Choisis ici la voix de chaque langue ; « automatique » prend la meilleure voix disponible.</p>
      {LANGUES_VOIX.map(([l, nom, phrase]) => (
        <div key={l} className="pj-row">
          <span style={{ minWidth: 120 }}>{nom}</span>
          <select value={choix[l] || ""} onFocus={() => charger(l)} onMouseDown={() => charger(l)} onChange={(e) => choisir(l, e.target.value)} aria-label={`Voix ${nom}`} data-testid={`voix-${l}`}>
            <option value="">Automatique</option>
            {choix[l] && !(listes[l] || []).some((v) => v.id === choix[l]) && <option value={choix[l]}>{choix[l]}</option>}
            {(listes[l] || []).map((v) => <option key={v.id} value={v.id}>{v.nom} — {v.region} · {v.qualite}{v.locuteurs > 1 ? ` · ${v.locuteurs} voix` : ""}{v.installee ? " ✓" : " (à télécharger)"}</option>)}
          </select>
          <button className="btn btn--ghost" onClick={() => ecouter(l, phrase)} title="Écouter">▶</button>
        </div>
      ))}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}


// Moteur de la voix d'EVA (pour tous : navigateur, satellites, enceintes) : Piper local, ou voix neuronales Microsoft en ligne.
function MoteurVoix() {
  const [m, setM] = useState(null); const [liste, setListe] = useState([]); const [msg, setMsg] = useState("");
  const h = { "Content-Type": "application/json", ...authHeaders() };
  useEffect(() => { fetch(`${VOICE_URL}/moteur`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : null)).then(setM).catch(() => setM(null)); }, []);
  useEffect(() => {
    if (m?.moteur !== "edge" || liste.length) return;
    fetch(`${VOICE_URL}/moteur/voix/fr`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`réponse ${r.status}`))))
      .then((d) => setListe(d.voix || [])).catch((e) => setMsg(`Liste des voix Microsoft indisponible (${e.message}).`));
  }, [m?.moteur, liste.length]);
  if (!m) return null;
  const changer = (chg) => fetch(`${VOICE_URL}/moteur`, { method: "PUT", headers: h, body: JSON.stringify(chg) }).then((r) => r.json()).then(setM).catch((e) => setMsg(e.message));
  return (
    <div className="routergrid" data-testid="moteur-voix">
      <label className="field"><span>Moteur de la voix d'EVA (pour tous les écrans et satellites)</span>
        <select value={m.moteur} onChange={(e) => changer({ moteur: e.target.value })}>
          <option value="piper">Piper — sur mon serveur, rien ne sort (voix plus robotique)</option>
          <option value="edge">Microsoft — voix naturelles en ligne (le texte lu part chez Microsoft)</option>
        </select>
      </label>
      {m.moteur === "edge" && (
        <label className="field"><span>Voix française</span>
          <select value={m.voix_edge?.fr || ""} onChange={(e) => changer({ voix_edge: { fr: e.target.value } })}>
            {!liste.some((v) => v.id === m.voix_edge?.fr) && <option value={m.voix_edge?.fr}>{m.voix_edge?.fr}</option>}
            {liste.map((v) => <option key={v.id} value={v.id}>{v.id.replace(/^fr-(FR|CA|BE|CH)-/, "").replace("Neural", "")} — {v.locale} · {v.genre === "Female" ? "femme" : "homme"}</option>)}
          </select>
        </label>
      )}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}

export default function VoiceCard() {
  const [prefs, update] = useVoicePrefs();
  const [voices, setVoices] = useState(null);
  const [sampleError, setSampleError] = useState("");
  const [lat, setLat] = useState(readLatency);
  const [nvoices, setNvoices] = useState(listFrenchVoices);
  const sttOk = nativeSttSupported(), ttsOk = nativeTtsSupported();
  useEffect(() => {
    const f = () => setLat(readLatency());
    window.addEventListener("eva-latency", f);
    const v = () => setNvoices(listFrenchVoices());
    if (ttsOk) window.speechSynthesis.addEventListener?.("voiceschanged", v);
    return () => { window.removeEventListener("eva-latency", f); if (ttsOk) window.speechSynthesis.removeEventListener?.("voiceschanged", v); };
  }, [ttsOk]);
  useEffect(() => {
    fetch(`${VOICE_URL}/voices`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : Promise.reject())).then(setVoices).catch(() => setVoices({ voices: [], default: "" }));
  }, []);

  async function sample() {
    setSampleError("");
    if (prefs.tts === "browser" && ttsOk) { await speakNative("Bonsoir. Je suis Éva. Prends ton temps, je suis là.", { voice: prefs.browserVoice, rate: prefs.rate }); return; }
    try {
      const res = await fetch(`${VOICE_URL}/tts`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ text: "Bonsoir. Je suis Éva. Prends ton temps, je suis là.", voice: prefs.voice || undefined, speed: Number(prefs.rate) || undefined }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `réponse ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = new Audio(url); a.onended = () => URL.revokeObjectURL(url); await a.play();
    } catch (e) { setSampleError(e.message); }
  }
  return (
    <div className="card routercard">
      <span className="card__label">Voix</span>
      <p className="page__sub">
        L'écoute et la lecture se font dans ce navigateur ; la reconnaissance (Whisper) et la voix (Piper) tournent sur ton serveur, rien ne part dans le cloud.
        Le micro exige HTTPS (c'est le cas avec Caddy). Ces réglages sont propres à cet appareil.
      </p>
      <MoteurVoix />
      <div className="routergrid">
        <label className="field"><span>Lire les réponses à voix haute</span>
          <select value={prefs.speakAll ? "1" : "0"} onChange={(e) => update({ speakAll: e.target.value === "1" })}>
            <option value="0">Seulement quand je parle à EVA</option>
            <option value="1">Toujours</option>
          </select>
        </label>
        <label className="field"><span>Écoute mains libres (mot d'éveil)</span>
          <select value={prefs.wake ? "1" : "0"} onChange={(e) => update({ wake: e.target.value === "1" })}>
            <option value="0">Désactivée</option>
            <option value="1">Activée (tant que cette page est ouverte)</option>
          </select>
        </label>
        <label className="field"><span>Voix d'EVA</span>
          <select value={prefs.voice} onChange={(e) => update({ voice: e.target.value })}>
            <option value="">Voix par défaut{voices?.default ? ` (${voices.default})` : ""}</option>
            {(voices?.voices || []).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select>
        </label>
        <label className="field"><span>Débit</span>
          <select value={String(prefs.rate)} onChange={(e) => update({ rate: Number(e.target.value) })}>
            <option value="0.8">Très lent et posé</option>
            <option value="0.9">Lent</option>
            <option value="1">Normal (déjà adouci)</option>
            <option value="1.15">Plus vif</option>
          </select>
        </label>
        <label className="field"><span>Reconnaissance de ma voix (écoute)</span>
          <select data-testid="engine" value={prefs.engine} onChange={(e) => update({ engine: e.target.value })}>
            <option value="local">Whisper sur mon serveur (100 % local)</option>
            <option value="browser" disabled={!sttOk}>Navigateur — rapide{sttOk ? "" : " (non disponible ici)"}</option>
          </select>
        </label>
        <label className="field"><span>Voix d'EVA (lecture)</span>
          <select data-testid="ttsengine" value={prefs.tts} onChange={(e) => update({ tts: e.target.value })}>
            <option value="local">Piper sur mon serveur (100 % local)</option>
            <option value="browser" disabled={!ttsOk}>Navigateur — instantanée{ttsOk ? "" : " (non disponible ici)"}</option>
          </select>
        </label>
        {prefs.tts === "browser" && (
          <label className="field"><span>Voix du navigateur</span>
            <select value={prefs.browserVoice} onChange={(e) => update({ browserVoice: e.target.value })}>
              <option value="">Voix française par défaut</option>
              {nvoices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </label>
        )}
        <label className="field"><span>Mot d'éveil</span>
          <input value={prefs.word} onChange={(e) => update({ word: e.target.value })} placeholder="eva" />
        </label>
      </div>
      <p className="page__sub">
        Dis « Eva » puis ta demande (« Eva, quelle heure est-il ? »), ou « Eva » seul, un bip te confirme l'écoute. Après une réponse parlée, EVA t'écoute encore 6 secondes. Pour plus de rapidité sur un NAS sans GPU, mets <code>WHISPER_MODEL_SIZE=base</code> dans le fichier .env.
      </p>
      {(prefs.engine === "browser" || prefs.tts === "browser") && (
        <p className="page__sub">
          ⚠ Le moteur du navigateur est plus rapide (comme ton appli Android) mais n'est plus 100 % local : sous Chrome et Android, la reconnaissance
          envoie l'audio aux serveurs de Google. Avec ce moteur, la reconnaissance de ta voix par le timbre n'est pas disponible (le visage et le style d'écriture restent utilisables).
        </p>
      )}
      <p className="page__sub" data-testid="latency">
        Derniers temps mesurés — écoute : {lat.stt != null ? `${lat.stt} ms` : "—"} · 1er mot d'EVA : {lat.ttft != null ? `${lat.ttft} ms` : "—"} ·
        réponse complète : {lat.total != null ? `${lat.total} ms` : "—"} · début de la voix : {lat.tts != null ? `${lat.tts} ms` : "—"}
      </p>
      <div className="routergrid">
        <label className="field"><span>Pilotage par gestes (caméra)</span>
          <select data-testid="gestures" value={prefs.gestures ? "1" : "0"} onChange={(e) => update({ gestures: e.target.value === "1" })}>
            <option value="0">Désactivé</option>
            <option value="1">Activé (tant que cette page est ouverte)</option>
          </select>
        </label>
      </div>
      <p className="page__sub">
        Gestes (100 % local, la caméra n'enregistre rien) : <b>balaie la main ouverte vers ta gauche</b> = diapo suivante, <b>vers ta droite</b> = précédente ;
        <b> paume ouverte immobile 1 s</b> = épingler ; <b>signe de paix tenu</b> = effacer l'écran ; <b>poing fermé tenu</b> = résumer ; <b>pouce levé 👍 / baissé 👎</b> = répondre oui / non quand EVA demande ton accord. Place ta main à 30-60 cm de la caméra, bien éclairée.
      </p>
      <div className="agentform__actions"><button className="btn" onClick={sample}>▶ Écouter un échantillon</button></div>
      {prefs.tts !== "browser" && <VoixParLangue prefs={prefs} update={update} />}
      {sampleError && <p className="page__warn">{sampleError}</p>}
      <p className="page__sub">Plus de voix : télécharge-en d'autres dans <code>eva-voice/models</code> (ex. <code>fr_FR-upmc-medium</code>, <code>fr_FR-mls-medium</code>), elles apparaissent ici après le redémarrage de eva-voice.</p>
      <VoiceDiagnostic word={prefs.word || "eva"} />
    </div>
  );
}
