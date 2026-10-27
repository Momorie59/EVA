import { useEffect, useState } from "react";
import { api } from "../api";
import HFRecommend from "./HFRecommend";
import ModelSelect from "./ModelSelect";
import { libelle } from "../models/catalogue";

const SLOTS = [
  ["default", "Modèle par défaut", "demandes courantes"],
  ["fast", "Rapide", "salutations, échanges courts"],
  ["code", "Code", "programmation, scripts, erreurs"],
  ["reasoning", "Raisonnement", "analyses, comparaisons, longues demandes"],
  ["vision", "Vision", "messages avec image"],
];

export default function ModelRouterCard() {
  const [data, setData] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [testText, setTestText] = useState("");
  const [test, setTest] = useState(null);
  const [rec, setRec] = useState(false);

  function load() {
    api("/api/models").then((d) => { setData(d); setCfg(d.config); }).catch((e) => setError(e.message));
  }
  useEffect(load, []);

  async function save() {
    setError(""); setMsg("");
    try { const c = await api("/api/models/router", { method: "PUT", body: JSON.stringify(cfg) }); setCfg(c); setMsg("Réglages enregistrés."); }
    catch (e) { setError(e.message); }
  }
  async function runTest(e) {
    e.preventDefault();
    try { setTest(await api("/api/models/preview", { method: "POST", body: JSON.stringify({ text: testText }) })); } catch (err) { setError(err.message); }
  }

  if (!data || !cfg) return <div className="card"><span className="card__label">Modèles</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  const chat = data.installed.filter((m) => !m.embedding);

  return (
    <div className="card routercard">
      <span className="card__label">Choix automatique du modèle</span>
      {!data.reachable && <p className="page__warn">Serveur IA injoignable : impossible de lister les modèles.</p>}
      <label className="field">
        <span>Mode</span>
        <select value={cfg.mode} onChange={(e) => setCfg({ ...cfg, mode: e.target.value })}>
          <option value="auto">Automatique selon la demande</option>
          <option value="fixed">Toujours le modèle par défaut</option>
        </select>
      </label>
      <div className="profils" role="radiogroup" aria-label="Profil de vitesse" data-testid="profil-vitesse">
        {[["equilibre", "⚖️ Équilibré", "Le modèle principal répond à tout. Le plus malin, plus lent."],
          ["rapide", "⚡ Rapide", "Un petit modèle répond à presque tout (2 à 3 fois plus vite) ; le principal garde le code et les analyses poussées."]].map(([id, label, hint]) => (
          <label key={id} className={`profil ${cfg.profil === id ? "is-on" : ""}`}>
            <input type="radio" name="profil" checked={cfg.profil === id} onChange={() => setCfg({ ...cfg, profil: id })} />
            <b>{label}</b><small>{hint}</small>
          </label>
        ))}
      </div>
      {cfg.profil === "rapide" && (
        <label className="field">
          <span>Petit modèle <em className="routerhint">— conseillé : qwen3.5:4b (3,5 Go, outils et images)</em></span>
          <span className="schedrow">
            <ModelSelect value={cfg.petit} onChange={(v) => setCfg({ ...cfg, petit: v })} modeles={chat.filter((m) => !m.cloud && !m.slow)} />
            {cfg.petit && !chat.some((m) => m.name === cfg.petit) && (
              <button type="button" className="btn" onClick={async () => { try { await api("/api/models/pull", { method: "POST", body: JSON.stringify({ name: cfg.petit }) }); setMsg(`Téléchargement de ${cfg.petit} lancé (suivi dans « Modèles » ci-dessous).`); } catch (er) { setError(er.message); } }} data-testid="profil-telecharger">Télécharger</button>
            )}
          </span>
        </label>
      )}
      <div className="routergrid">
        {SLOTS.map(([key, label, hint]) => (
          <label className="field" key={key}>
            <span>{label} <em className="routerhint">— {hint}</em></span>
            <ModelSelect value={cfg[key]} onChange={(v) => setCfg({ ...cfg, [key]: v })} modeles={chat} vide={key === "default" ? "(modèle de .env)" : "(comme le défaut)"} manquant="introuvable" />
          </label>
        ))}
      </div>
      <p className="page__sub">Les modèles sont rangés par origine : 🖥️ ton serveur (rien ne sort de la maison), 🆓 IA gratuites et ☁️ IA du marché (sur Internet), 🐢 AirLLM (très lent). « Sans outils » : le modèle répond, mais EVA ne peut pas utiliser ses outils avec lui.</p>
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
      <div className="agentform__actions">
        <button className="btn" data-testid="router-suggest" onClick={() => { if (data.suggestion) setCfg({ ...cfg, ...Object.fromEntries(Object.entries(data.suggestion).filter(([, v]) => v)) }); setRec(true); }}>Suggestions</button>
        <button className="btn btn--primary" onClick={save}>Enregistrer</button>
      </div>
      {rec && <HFRecommend installed={data.installed} cfg={cfg} onApply={async (assign) => {
        const next = { ...cfg, ...Object.fromEntries(Object.entries(assign).filter(([, v]) => v)) };
        const c = await api("/api/models/router", { method: "PUT", body: JSON.stringify(next) }); setCfg(c); load();
      }} />}
      <form className="schedrow" onSubmit={runTest}>
        <input className="skillinstall__input" value={testText} onChange={(e) => setTestText(e.target.value)} placeholder="Tester : quel modèle pour « écris un script python » ?" />
        <button className="btn" type="submit" disabled={!testText.trim()}>Tester</button>
      </form>
      {test && <p className="page__sub">→ <b>{libelle(test.model, chat)}</b> <small>({test.model})</small> — {test.reason}{test.tools ? "" : " · sans outils"}</p>}
    </div>
  );
}
