// Fonctions pures de la voix (testables sans navigateur).

// Whisper écrit « Eva » de bien des façons (Éva, Ève, Ava, Eba, « Et va »…) : comparaison sans accents ni
// majuscules, avec les variantes courantes. Un mot d'éveil personnalisé reste exact.
const GREET = "(?:hey|he|hei|ok|okay|dis|salut|bonjour|coucou|yo|oh|eh|ah|hola)";
const EVA_FORMS = "(?:e[\\s-]?va|et[\\s-]va|eh[\\s-]va|ava|eba|eve|eva|ewa|iva|evah|evaa)";

function esc(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Même longueur que l'original (une unité UTF-16 → une unité) : les indices restent valables.
function fold(text) {
  return text.split("").map((c) => (c.normalize("NFD")[0] || c).toLowerCase()).join("");
}

export function wakeRegex(word = "eva") {
  const w = fold((word || "eva").trim());
  const core = w === "eva" ? EVA_FORMS : esc(w);
  return new RegExp(`^\\W*(?:${GREET}[\\s,.-]+)?${core}(?![a-z0-9])[\\s,.:;!?-]*`, "i");
}

// → { woke, command } ; command = ce qui suit le mot d'éveil dans la même phrase.
export function matchWake(text, word = "eva") {
  const t = (text || "").trim();
  const m = fold(t).match(wakeRegex(word));
  if (!m) return { woke: false, command: "" };
  return { woke: true, command: t.slice(m[0].length).trim() };
}

// Whisper invente du texte sur du bruit ou du silence ; on l'écarte.
const HALLUCINATIONS = [
  /sous-?titr/i, /amara\.org/i, /merci d'avoir regard/i, /abonne/i, /^\W*merci\W*$/i,
  /^\W*(?:\.{2,}|…)\W*$/, /^\W*(?:euh+|hum+|hmm+|ah+|oh+)\W*$/i,
];
export function isHallucination(text) {
  const t = (text || "").trim();
  if (t.length < 2) return true;
  return HALLUCINATIONS.some((re) => re.test(t));
}

// Texte → ce qu'on lit à voix haute : sans code, liens ni markdown.
export function cleanForSpeech(text) {
  let t = String(text || "");
  t = t.replace(/```[\s\S]*?```/g, " (voir le bloc de code à l'écran) ");
  t = t.replace(/`([^`]*)`/g, "$1");
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, " ");
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  t = t.replace(/https?:\/\/\S+/g, " lien ");
  t = t.replace(/^\s{0,3}#{1,6}\s*/gm, "");
  t = t.replace(/^\s*[-*•]\s+/gm, "");
  t = t.replace(/[*_~>|]/g, "");
  t = t.replace(/\s*\n+\s*/g, ". ").replace(/\.{2,}/g, ".").replace(/\s{2,}/g, " ");
  return t.trim();
}

// Découpe en morceaux ≤ max caractères, à la fin des phrases : lecture qui démarre vite.
export function splitSentences(text, max = 260) {
  const parts = text.match(/[^.!?…]+[.!?…]*\s*/g) || [text];
  const out = [];
  let cur = "";
  for (const p of parts) {
    if ((cur + p).length > max && cur) { out.push(cur.trim()); cur = ""; }
    if (p.length > max) {
      for (let i = 0; i < p.length; i += max) out.push(p.slice(i, i + max).trim());
    } else cur += p;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.filter(Boolean);
}

// PCM Float32 → WAV 16 bits mono (rééchantillonné à 16 kHz : léger et suffisant pour Whisper).
export function encodeWav(samples, inRate, outRate = 16000) {
  const ratio = inRate / outRate;
  const n = Math.floor(samples.length / ratio);
  const pcm = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    const start = Math.floor(i * ratio), end = Math.max(start + 1, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end && j < samples.length; j++) sum += samples[j];
    const v = Math.max(-1, Math.min(1, sum / (end - start)));
    pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const dv = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, outRate, true); dv.setUint32(28, outRate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
  w(36, "data"); dv.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm);
  return new Blob([buf], { type: "audio/wav" });
}

// Lecture au fil de l'eau : donne les phrases COMPLÈTES apparues depuis `from` (jamais au milieu d'un bloc de code).
export function nextSpeakable(text, from = 0) {
  let limit = text.length;
  const fences = (text.match(/```/g) || []).length;
  if (fences % 2 === 1) limit = text.lastIndexOf("```");     // bloc de code encore ouvert : on attend sa fermeture
  const rest = text.slice(from, Math.max(from, limit));
  let cut = -1;
  const re = /[.!?…]+["»)]*(?:\s|$)|\n+/g;
  let m;
  while ((m = re.exec(rest))) cut = m.index + m[0].length;
  if (cut < 0 && from === 0 && rest.length >= 28) {          // 1re phrase longue : on démarre sur une virgule (voix plus tôt)
    const c = Math.max(rest.lastIndexOf(", "), rest.lastIndexOf("; "), rest.lastIndexOf(": "));
    if (c >= 16) cut = c + 2;
    else if (rest.length >= 70) { const sp = rest.lastIndexOf(" "); if (sp >= 50) cut = sp + 1; }  // sans ponctuation : au mot près
  }
  if (cut < 0) return { chunks: [], upto: from };
  const chunk = cleanForSpeech(rest.slice(0, cut));
  return { chunks: chunk ? [chunk] : [], upto: from + cut };
}

// « EVA, efface », « ferme l'affichage », « retour au menu » : vide l'écran sans passer par le modèle.
// Seuls ces mots-là sont acceptés après le verbe : « ferme la porte du garage » reste une vraie demande.
const CLEAR_WORDS = new Set(["eva", "efface", "effacer", "ferme", "fermer", "masque", "cache", "retour", "reviens", "quitte", "tout", "ca", "cela", "l", "affichage", "ecran", "la", "le", "presentation", "diaporama", "meteo", "au", "a", "menu", "initial", "principal", "accueil", "s", "il", "te", "plait", "stp", "merci", "de", "ici"]);
export function isClearCommand(text) {
  const words = fold(text).replace(/[^\w ]/g, " ").replace(/\s+/g, " ").trim().split(" ");
  const verbs = ["efface", "effacer", "ferme", "fermer", "masque", "cache", "retour", "reviens", "quitte"];
  return words.length <= 7 && words.some((w) => verbs.includes(w)) && words.every((w) => CLEAR_WORDS.has(w)) && verbs.includes(words[0] === "eva" ? words[1] : words[0]);
}

// « EVA, c'est moi », « vérifie-moi », « reconnais-moi » : lance la vérification du visage en direct.
export function isVerifyCommand(text) {
  const t = fold(text).replace(/[^\w ]/g, " ").replace(/\s+/g, " ").trim().replace(/^eva /, "");
  return /^(c est moi|c est bien moi|verifie moi|verifie que c est moi|reconnais moi|identifie moi|je suis la|presente moi)( eva| s il te plait| stp)?$/.test(t);
}


// Réponse parlée à « tu confirmes ? » : seulement une réponse courte et nette (une phrase longue reste une vraie demande).
const YES = ["oui", "ouais", "ok", "okay", "d accord", "vas y", "va y", "confirme", "je confirme", "valide", "go", "bien sur", "fais le", "c est bon", "affirmatif", "yes"];
const NO = ["non", "nan", "annule", "annuler", "refuse", "stop", "arrete", "pas question", "laisse tomber", "surtout pas", "negatif", "no"];
export function parseYesNo(text) {
  const t = fold(text).replace(/[^\w ]/g, " ").replace(/\s+/g, " ").trim().replace(/^(eva|alors|bon|euh) /, "");
  if (!t || t.split(" ").length > 5) return null;
  if (NO.some((w) => t === w || t.startsWith(w + " "))) return "no";
  if (YES.some((w) => t === w || t.startsWith(w + " "))) return "yes";
  return null;
}
