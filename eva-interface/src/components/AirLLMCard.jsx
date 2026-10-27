import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

const go = (n) => `${String(n).replace(".", ",")} Go`;

// AirLLM : très gros modèles couche par couche (repli lent). Choix du modèle, état, place sur le disque.
export default function AirLLMCard() {
  const [d, setD] = useState(null);
  const [absent, setAbsent] = useState("");
  const [choix, setChoix] = useState("");
  const [libre, setLibre] = useState("");
  const [msg, setMsg] = useState(""); const [err, setErr] = useState(""); const [occupe, setOccupe] = useState(false);
  const load = useCallback(async () => {
    try {
      const r = await api("/api/airllm");
      setD(r); setAbsent("");
      setChoix((c) => c || r.model);
    } catch (e) { setAbsent(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!d?.sante?.loading && !d?.sante?.busy) return undefined;
    const t = setInterval(load, 5000);                     // pendant un téléchargement ou une réponse
    return () => clearInterval(t);
  }, [d, load]);

  if (!d) {
    if (!absent) return null;
    return (
      <section className="card" data-testid="airllm-card">
        <span className="card__label">AirLLM (repli lent)</span>
        <p className="page__warn">{absent}</p>
      </section>
    );
  }
  const modele = (choix === "__autre" ? libre : choix).trim();
  const dans = (id) => d.catalogue.find((c) => c.id === id);
  const info = dans(modele);
  const trop = info && !d.gpu && info.taille_go > d.ram_go * 0.6;
  const place = info && info.taille_go * 2.1 > d.disque_libre_go + (d.presents.find((p) => p.id === modele)?.taille_go || 0);

  async function utiliser() {
    setErr(""); setMsg(""); setOccupe(true);
    try {
      const r = await api("/api/airllm", { method: "PUT", body: JSON.stringify({ model: modele }) });
      setD((x) => ({ ...x, ...r })); setChoix(r.model);
      setMsg(`AirLLM utilisera « ${r.model} ». Il sera téléchargé et découpé à la prochaine question (la première est longue).`);
      load();
    } catch (e) { setErr(e.message); } finally { setOccupe(false); }
  }
  async function repli(v) {
    setErr("");
    try { const r = await api("/api/airllm/repli", { method: "PUT", body: JSON.stringify({ repli_auto: v }) }); setD((x) => ({ ...x, ...r })); }
    catch (e) { setErr(e.message); }
  }
  async function supprimer(id) {
    if (!(await confirmer(`Supprimer « ${id} » du disque ? Il faudra le retélécharger pour l'utiliser.`))) return;
    setErr(""); setMsg("");
    try { const r = await api(`/api/airllm/modeles/${id}`, { method: "DELETE" }); setD((x) => ({ ...x, ...r })); setMsg(`« ${id} » supprimé.`); }
    catch (e) { setErr(e.message); }
  }
  const s = d.sante || {};
  const etat = s.loading ? "téléchargement / chargement en cours…" : s.busy ? "en train de répondre…" : s.loaded ? "prêt (chargé)" : "en attente (chargé à la première question)";
  return (
    <section className="card" data-testid="airllm-card">
      <span className="card__label">AirLLM (repli lent)</span>
      <p className="page__sub">
        Seulement quand tu le choisis : sélecteur de modèle de la conversation › « airllm ». Sans outils, une demande à la fois.
        {d.gpu ? " Carte graphique NVIDIA détectée." : ` Sans carte graphique : tourne sur le processeur (${go(d.ram_go)} de mémoire), donc lent — un modèle qui tient en mémoire répond bien plus vite.`}
      </p>
      <label className="checkrow"><input type="checkbox" checked={!!d.repli_auto} onChange={(e) => repli(e.target.checked)} data-testid="airllm-repli" /> Utiliser aussi AirLLM automatiquement quand mon serveur IA ne répond pas (sinon EVA dit simplement que le serveur IA est injoignable)</label>
      <p className="page__sub">Modèle actuel : <b>{d.model}</b> · {etat}{s.last_ms ? ` · dernière réponse en ${Math.round(s.last_ms / 1000)} s` : ""}</p>
      {s.error && <p className="page__warn">Dernière erreur : {s.error}</p>}
      <div className="routercard">
        <label>Modèle
          <select value={choix} onChange={(e) => setChoix(e.target.value)} data-testid="airllm-choix">
            {!dans(d.model) && <option value={d.model}>{d.model}</option>}
            {d.catalogue.map((c) => <option key={c.id} value={c.id}>{c.id} — {go(c.taille_go)}</option>)}
            <option value="__autre">Autre modèle Hugging Face…</option>
          </select>
        </label>
        {choix === "__autre" && <label>Nom sur Hugging Face <input value={libre} onChange={(e) => setLibre(e.target.value)} placeholder="auteur/modèle, ex. Qwen/Qwen2.5-1.5B-Instruct" /></label>}
        {info && <p className="page__sub">{info.note}.</p>}
        {trop && <p className="page__warn">Plus gros que la mémoire de cette machine sans carte graphique : chaque mot relit le modèle sur le disque (des dizaines de minutes par réponse).</p>}
        {place && <p className="page__warn">Place sur le disque peut-être insuffisante ({go(d.disque_libre_go)} libres ; il faut environ deux fois la taille du modèle).</p>}
        <div className="pj-row">
          <button className="btn btn--primary" onClick={utiliser} disabled={occupe || !modele || modele === d.model || d.busy} data-testid="airllm-utiliser">Utiliser ce modèle</button>
          <button className="btn btn--ghost" onClick={load}>Actualiser</button>
        </div>
      </div>
      {d.presents.length > 0 && (
        <>
          <span className="card__label">Sur le disque ({go(d.disque_libre_go)} libres)</span>
          <ul className="pj-trash__list">
            {d.presents.map((p) => (
              <li key={p.id}><span><b>{p.id}</b> <small>{go(p.taille_go)}{p.id === d.model ? " · utilisé" : ""}</small></span>
                {p.id !== d.model && <span><button className="btn btn--ghost" onClick={() => supprimer(p.id)}>Supprimer</button></span>}</li>
            ))}
          </ul>
        </>
      )}
      {msg && <p className="page__sub">{msg}</p>}
      {err && <p className="page__warn">{err}</p>}
    </section>
  );
}
