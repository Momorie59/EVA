// Présentation des modèles d'IA : nom lisible, origine (mon serveur, IA gratuites, IA du marché, AirLLM), badges.
// Fonctions pures, partagées par le sélecteur de la conversation et les Paramètres.

export const AUTO_GRATUIT = "cloud:auto/gratuit";

export const GROUPES = [
  { id: "local", label: "Mon serveur IA", icone: "🖥️", aide: "Sur ton serveur : rien ne sort de la maison." },
  { id: "gratuit", label: "IA gratuites", icone: "🆓", aide: "Sur Internet, gratuites (avec des limites)." },
  { id: "marche", label: "IA du marché", icone: "☁️", aide: "Sur Internet, payantes selon l'usage." },
  { id: "airllm", label: "AirLLM", icone: "🐢", aide: "Très gros modèle, très lent (minutes)." },
];

const MARQUES = {
  qwen: "Qwen", llama: "Llama", llava: "LLaVA", mistral: "Mistral", mixtral: "Mixtral", gemma: "Gemma", phi: "Phi", deepseek: "DeepSeek",
  codellama: "Code Llama", starcoder: "StarCoder", nomic: "Nomic", minicpm: "MiniCPM", "gpt-oss": "GPT-OSS", granite: "Granite",
  smollm: "SmolLM", moondream: "Moondream", nemotron: "Nemotron", command: "Command", olmo: "OLMo", hermes: "Hermes", glm: "GLM",
  gemini: "Gemini", claude: "Claude", gpt: "GPT", ministral: "Ministral", codestral: "Codestral", kimi: "Kimi", minimax: "MiniMax",
};

const maj = (s) => s.charAt(0).toUpperCase() + s.slice(1);

const VIDE = /^(it|instruct|latest|hf|gguf|fp8|fp16|bf16|int4|int8|awq|gptq|free|chat|preview|q\d.*|iq\d.*|a\d+(\.\d+)?b)$/i;
const TAILLE = /^(\d+(?:\.\d+)?)([bm])$/i;

// « qwen2.5-coder:7b » → « Qwen 2.5 Coder » + « 7B » ; « llama3.2:3b-instruct-q4_K_M » → « Llama 3.2 » + « 3B »
export function nomLisible(brut) {
  const [base, tag = ""] = String(brut).split(":");
  let nom = base.split("/").pop().toLowerCase();
  let marque = "";
  for (const k of Object.keys(MARQUES).sort((x, y) => y.length - x.length)) {
    if (nom.startsWith(k)) { marque = MARQUES[k]; nom = nom.slice(k.length); break; }
  }
  let variante = "";
  const mots = [];
  for (const brutMot of nom.split(/[-_]+/).filter(Boolean)) {
    const t = brutMot.match(TAILLE);
    if (t) { variante = variante || `${t[1]}${t[2].toUpperCase()}`; continue; }
    if (VIDE.test(brutMot)) continue;
    // lettres et chiffres collés : « small3.2 » → « Small 3.2 », « r1 » reste « R1 »
    const coupe = brutMot.match(/^([a-z]{3,})(\d+(?:\.\d+)*)$/i);
    if (coupe) mots.push(maj(coupe[1]), coupe[2]);
    else if (/^\d+$/.test(brutMot) && /^\d+$/.test(mots[mots.length - 1] || "")) mots[mots.length - 1] += `.${brutMot}`;   // « 4-5 » → « 4.5 »
    else mots.push(/^[a-z]\d+$/i.test(brutMot) ? brutMot.toUpperCase() : /^\d/.test(brutMot) ? brutMot : maj(brutMot));
  }
  if (!marque && mots.length) marque = mots.shift();
  for (const m of tag.split(/[-_]+/)) {
    const t = m.match(TAILLE);
    if (t && !variante) variante = `${t[1]}${t[2].toUpperCase()}`;
  }
  if (!variante && tag && !/^latest$/i.test(tag) && !/^q\d/i.test(tag)) variante = tag;
  return { titre: [marque, ...mots].join(" ").trim() || base, variante };
}

export function decrire(m) {
  const name = m.name;
  if (name === AUTO_GRATUIT) {
    return { ...m, groupe: "gratuit", titre: "IA gratuites — automatique", variante: "", source: (m.services || []).join(", ") || "rotation",
             auto: true, internet: true };
  }
  if (name === "airllm") return { ...m, groupe: "airllm", titre: "AirLLM", variante: "", source: "Très gros modèle", lent: true };
  if (name.startsWith("cloud:")) {
    const reste = name.slice(6);
    const modele = reste.slice(reste.indexOf("/") + 1);
    const { titre, variante } = nomLisible(modele.replace(/:free$/, ""));
    return { ...m, groupe: m.gratuit ? "gratuit" : "marche", titre, variante, source: m.provider || reste.split("/")[0], internet: true };
  }
  const { titre, variante } = nomLisible(name);
  return { ...m, groupe: "local", titre, variante, source: m.size_gb ? `${String(m.size_gb).replace(".", ",")} Go` : "" };
}

export function badges(d) {
  const out = [];
  if (d.charge) out.push({ t: "⚡ en mémoire", k: "ok", aide: "Déjà chargé : répond sans attente" });
  if (d.tools) out.push({ t: "🛠 outils", k: "", aide: "Peut utiliser les outils d'EVA (maison, agenda, recherche…)" });
  else if (d.tools === false) out.push({ t: "sans outils", k: "faible", aide: "Répond, mais EVA ne peut pas utiliser ses outils avec lui" });
  if (d.vision) out.push({ t: "👁 images", k: "", aide: "Comprend les photos" });
  if (d.lent) out.push({ t: "🐢 très lent", k: "attention", aide: "Des minutes par réponse" });
  if (d.internet) out.push({ t: "🌐 Internet", k: "attention", aide: "Tes messages partent chez ce service" });
  if (d.entrainement === "oui") out.push({ t: "⚠️ entraînement", k: "attention", aide: "Ce service peut entraîner ses modèles avec tes messages" });
  return out;
}

export function grouper(modeles) {
  const ds = modeles.filter((m) => !m.embedding && !/embed/i.test(m.name)).map(decrire);
  return GROUPES.map((g) => ({ ...g, modeles: ds.filter((d) => d.groupe === g.id).sort((a, b) => (b.auto ? 1 : 0) - (a.auto ? 1 : 0) || a.titre.localeCompare(b.titre)) }))
    .filter((g) => g.modeles.length);
}

export function libelle(name, modeles = []) {
  if (!name) return "Automatique";
  const m = modeles.find((x) => x.name === name) || { name };
  const d = decrire(m);
  return `${d.titre}${d.variante ? ` ${d.variante}` : ""}`;
}
