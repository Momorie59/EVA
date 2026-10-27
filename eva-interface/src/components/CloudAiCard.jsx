import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { libelle } from "../models/catalogue";
import { confirmer } from "../confirmer";

const EMPTY = { id: "", preset: "openai", base_url: "", api_key: "", models: "", fallback: false, vision: false, prix_entree: "", prix_sortie: "", budget_mois: "" };

// IA du marché (OpenAI, Claude, Gemini…) — facultatif. Rien ne part sur Internet tant qu'un de ses modèles n'est pas choisi.
export default function CloudAiCard() {
  const [data, setData] = useState(null); const [form, setForm] = useState(null);
  const [msg, setMsg] = useState(""); const [error, setError] = useState(""); const [found, setFound] = useState([]);
  const [gratuites, setGratuites] = useState(null); const [ouvertG, setOuvertG] = useState(false); const [majG, setMajG] = useState(false);
  const load = useCallback(async () => { try { setData(await api("/api/cloud")); } catch (e) { setError(e.message); } }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (ouvertG && !gratuites) api("/api/cloud/gratuites").then(setGratuites).catch((e) => setError(e.message)); }, [ouvertG, gratuites]);
  if (!data) return null;
  const presets = data.presets;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  function edit(id) {
    const p = data.providers[id];
    setFound([]); setMsg(""); setError("");
    setForm(p ? { id, preset: p.preset, base_url: p.base_url, api_key: "", models: (p.models || []).join(", "), fallback: p.fallback, vision: p.vision, has_key: p.has_key,
                  prix_entree: p.prix_entree || "", prix_sortie: p.prix_sortie || "", budget_mois: p.budget_mois || "", sans_cle: !!p.sans_cle, gratuit: !!p.gratuit, entrainement: p.entrainement ?? null }
              : { ...EMPTY, id: "openai", base_url: presets.openai.base_url, models: presets.openai.example });
  }
  function ajouterGratuit(g) {
    setFound([]); setMsg(""); setError("");
    const existe = data.providers[g.id];
    setForm({ ...EMPTY, id: g.id, preset: "custom", label: g.nom, base_url: g.base_url, models: g.modeles.map((m) => m.id).join(", "),
              vision: g.modeles.length > 0 && g.modeles.every((m) => m.vision), sans_cle: g.cle_facultative, cle_facultative: g.cle_facultative, gratuit: true, entrainement: g.entrainement,
              prix_entree: "0", prix_sortie: "0", budget_mois: "", has_key: !!existe?.has_key, page_cle: g.page_cle, compte_cloudflare: g.compte_cloudflare });
    window.scrollTo({ top: 0 });
  }
  async function rotation(patch) {
    setError("");
    try { const r = await api("/api/cloud/rotation", { method: "PUT", body: JSON.stringify(patch) }); setData((d) => ({ ...d, rotation: r })); }
    catch (e) { setError(e.message); }
  }
  function cocher(cle, oui) {
    const exclus = data.rotation.services.filter((x) => !x.coche).map((x) => x.cle).filter((c) => c !== cle);
    rotation({ exclus: oui ? exclus : [...exclus, cle] });
  }
  function deplacer(i, sens) {
    const ids = data.rotation.services.map((x) => x.cle);
    const j = i + sens;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    rotation({ ordre: ids });
  }
  async function majGratuites() {
    setMajG(true); setError("");
    try { setGratuites(await api("/api/cloud/gratuites/maj", { method: "POST" })); setMsg("Liste des IA gratuites mise à jour."); }
    catch (e) { setError(e.message); } finally { setMajG(false); }
  }
  function pickPreset(preset) {
    setForm((f) => ({ ...f, preset, id: f.has_key ? f.id : preset, base_url: presets[preset].base_url, models: presets[preset].example }));
  }
  async function save() {
    setError(""); setMsg("");
    try {
      await api(`/api/cloud/providers/${form.id}`, { method: "PUT", body: JSON.stringify({ ...form, models: form.models }) });
      setMsg("Enregistré. Le modèle apparaît dans le sélecteur de la conversation (nom « cloud:… »)."); setForm(null); load();
    } catch (e) { setError(e.message); }
  }
  async function test() {
    setError(""); setMsg(""); setFound([]);
    try {
      await api(`/api/cloud/providers/${form.id}`, { method: "PUT", body: JSON.stringify({ ...form }) });
      const r = await api(`/api/cloud/providers/${form.id}/test`, { method: "POST" });
      setFound(r.models || []); setMsg(r.note || `Clé valide — ${r.models.length} modèle(s) disponibles.`); load();
    } catch (e) { setError(e.message); }
  }
  async function remove(id) {
    if (!(await confirmer(`Supprimer « ${id} » et sa clé ?`))) return;
    await api(`/api/cloud/providers/${id}`, { method: "DELETE" }).catch((e) => setError(e.message)); load();
  }
  async function prefer(v) { await api("/api/cloud/prefs", { method: "PUT", body: JSON.stringify({ prefer_over_airllm: v }) }).catch((e) => setError(e.message)); load(); }

  const ids = Object.keys(data.providers);
  return (
    <section className="card" data-testid="cloud-card">
      <span className="card__label">IA du marché (facultatif)</span>
      <p className="page__sub">Connecte OpenAI, Claude, Gemini, Mistral, Groq, DeepSeek, OpenRouter ou tout service « compatible OpenAI ». <b>Attention :</b> avec un de ces modèles, tes messages partent sur Internet vers ce service ; EVA reste 100 % locale tant que tu n'en choisis pas.</p>
      {ids.length === 0 && <p className="page__sub">Aucun fournisseur.</p>}
      <ul className="pj-trash__list">
        {ids.map((id) => { const p = data.providers[id]; return (
          <li key={id}><span><b>{p.label}</b> <small>{p.gratuit ? "🆓 gratuit · " : ""}{p.has_key ? "clé enregistrée" : p.sans_cle ? "accès sans clé" : "sans clé"} · {(p.models || []).join(", ") || "aucun modèle"}{p.fallback ? " · repli si pas de serveur IA local" : ""}</small>
            {data.depenses?.fournisseurs?.[id] && (() => { const d = data.depenses.fournisseurs[id]; return (
              <small className={d.atteint ? "page__warn" : "page__sub"} style={{ display: "block" }}>
                Ce mois-ci : {d.eur.toFixed(2)} €{d.budget ? ` / ${Number(d.budget).toFixed(2)} €` : ""} · {d.appels} appel(s){d.atteint ? " — budget atteint : EVA utilise le modèle local" : ""}
              </small>); })()}</span>
            <span><button className="btn btn--ghost" onClick={() => edit(id)}>Modifier</button> <button className="btn btn--ghost" onClick={() => remove(id)}>Supprimer</button></span></li>
        ); })}
      </ul>
      {ids.some((i) => data.providers[i].fallback) && (
        <label className="checkrow"><input type="checkbox" checked={data.prefer_over_airllm} onChange={(e) => prefer(e.target.checked)} /> En repli, utiliser l'IA du marché avant AirLLM (bien plus rapide)</label>
      )}
      {!form && <div className="pj-row"><button className="btn" onClick={() => edit("")} data-testid="cloud-add">Ajouter un fournisseur</button></div>}
      {form && (
        <div className="routercard" data-testid="cloud-form">
          <label>Fournisseur <select value={form.preset} onChange={(e) => pickPreset(e.target.value)}>{Object.entries(presets).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
          <label>Identifiant <input value={form.id} onChange={(e) => set("id", e.target.value.toLowerCase())} disabled={form.has_key} /></label>
          {form.preset === "custom" && <label>Adresse (base compatible OpenAI) <input value={form.base_url} placeholder="https://…/v1" onChange={(e) => set("base_url", e.target.value)} /></label>}
          {form.compte_cloudflare && form.base_url.includes("{account_id}") && <p className="page__warn">Remplace {"{account_id}"} dans l'adresse par l'identifiant de ton compte Cloudflare.</p>}
          {form.page_cle && <p className="page__sub">Clé gratuite : <a href={form.page_cle} target="_blank" rel="noreferrer">obtenir ma clé chez {form.label}</a> (connexion à leur site), puis colle-la ci-dessous.</p>}
          <label>Clé d'API <input type="password" value={form.api_key} placeholder={form.has_key ? "(inchangée — saisis pour remplacer)" : form.sans_cle ? "(facultative)" : "sk-…"} onChange={(e) => set("api_key", e.target.value)} autoComplete="off" data-testid="cloud-key" /></label>
          {(form.cle_facultative || form.sans_cle) && <label className="checkrow"><input type="checkbox" checked={!!form.sans_cle} onChange={(e) => set("sans_cle", e.target.checked)} /> Utiliser sans clé (accès anonyme, limites plus basses)</label>}
          <label>Modèles (séparés par des virgules) <input value={form.models} onChange={(e) => set("models", e.target.value)} /></label>
          {found.length > 0 && <p className="page__sub">Disponibles : {found.slice(0, 30).map((m) => <button key={m} className="btn btn--ghost" onClick={() => set("models", m)}>{m}</button>)}</p>}
          <label className="checkrow"><input type="checkbox" checked={form.fallback} onChange={(e) => set("fallback", e.target.checked)} /> Utiliser en repli quand mon serveur IA local est indisponible</label>
          <div className="routergrid">
            <label>Prix € / million de jetons envoyés <input inputMode="decimal" value={form.prix_entree} placeholder="ex. 0,15" onChange={(e) => set("prix_entree", e.target.value)} /></label>
            <label>Prix € / million de jetons reçus <input inputMode="decimal" value={form.prix_sortie} placeholder="ex. 0,60" onChange={(e) => set("prix_sortie", e.target.value)} /></label>
            <label>Budget par mois (€, vide = sans limite) <input inputMode="decimal" value={form.budget_mois} placeholder="ex. 5" onChange={(e) => set("budget_mois", e.target.value)} data-testid="cloud-budget" /></label>
          </div>
          <p className="page__sub">Comme Jarvis : une fois le budget du mois atteint, EVA repasse toute seule sur le modèle local jusqu'au mois suivant (et te prévient).</p>
          <label className="checkrow"><input type="checkbox" checked={form.vision} onChange={(e) => set("vision", e.target.checked)} /> Ces modèles comprennent les images</label>
          <div className="pj-row"><button className="btn" onClick={save} data-testid="cloud-save">Enregistrer</button> <button className="btn btn--ghost" onClick={test} disabled={!form.api_key && !form.has_key && !form.sans_cle}>Tester la clé / lister les modèles</button> <button className="btn btn--ghost" onClick={() => setForm(null)}>Annuler</button></div>
        </div>
      )}
      {ids.some((i) => data.providers[i].gratuit) && data.rotation && (
        <div className="routercard rotation" data-testid="rotation">
          <b>🆓 IA gratuites automatiques</b>
          <p className="page__sub">Choisis « IA gratuites (automatique) » dans le sélecteur de modèle de la conversation : EVA essaie les services ci-dessous dans l'ordre et passe tout seul au suivant si l'un a atteint son quota, refuse la clé ou est en panne (il est mis de côté le temps qu'il faut : une minute, quelques heures ou jusqu'au lendemain).</p>
          <label className="checkrow"><input type="checkbox" checked={data.rotation.exclure_entrainement} onChange={(e) => rotation({ exclure_entrainement: e.target.checked })} data-testid="rotation-entrainement" /> Ne pas utiliser les services qui peuvent entraîner leurs modèles avec mes messages</label>
          <label className="checkrow"><input type="checkbox" checked={data.rotation.repli} onChange={(e) => rotation({ repli: e.target.checked })} data-testid="rotation-repli" /> Les utiliser aussi automatiquement quand mon serveur IA ne répond pas</label>
          {(() => {
            const actifs = data.rotation.services.filter((x) => x.coche && !x.bloque).length;
            const enAttente = data.rotation.services.filter((x) => x.bloque).length;
            return <p className="page__sub" data-testid="rotation-compte"><b>{actifs}</b> modèle(s) dans la rotation{enAttente ? ` · ${enAttente} en attente (clé manquante ou exclus)` : ""}. Plus il y en a, moins EVA tombe à court : ajoute d'autres services avec « IA gratuites » ci-dessous (la plupart demandent juste une clé gratuite).</p>;
          })()}
          {data.rotation.services.length === 0 ? <p className="page__warn">Aucune IA gratuite ajoutée.</p> : (
            <ol className="pj-trash__list rotation__liste">
              {data.rotation.services.map((x, i) => (
                <li key={x.cle} className={x.bloque || !x.coche ? "is-off" : ""}>
                  <label className="rotation__case"><input type="checkbox" checked={x.coche} disabled={!!x.bloque} onChange={(e) => cocher(x.cle, e.target.checked)} data-testid={`rot-${x.cle}`} />
                    <span><b>{libelle(`cloud:${x.id}/${x.modele}`)}</b> <small>{x.label}</small>
                      <small className={x.bloque || x.pause_jusqua ? "page__warn" : "page__sub"} style={{ display: "block" }}>
                        {x.bloque ? x.bloque
                          : x.pause_jusqua ? `⏸ en pause jusqu'à ${new Date(x.pause_jusqua * 1000).toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" })} — ${x.raison}`
                          : x.ok ? `✓ a répondu à ${new Date(x.ok * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` : x.coche ? "prêt" : "décoché"}
                      </small></span></label>
                  <span><button className="btn btn--ghost" onClick={() => deplacer(i, -1)} disabled={i === 0} aria-label="Monter">↑</button> <button className="btn btn--ghost" onClick={() => deplacer(i, 1)} disabled={i === data.rotation.services.length - 1} aria-label="Descendre">↓</button></span></li>
              ))}
            </ol>
          )}
        </div>
      )}
      <div className="pj-row"><button className="btn btn--ghost" onClick={() => setOuvertG((v) => !v)} data-testid="gratuites-ouvrir">{ouvertG ? "▾" : "▸"} IA gratuites (accès gratuit permanent)</button></div>
      {ouvertG && gratuites && (
        <div data-testid="gratuites">
          <p className="page__sub">Services qui offrent un accès gratuit et durable à de gros modèles, d'après la liste <a href={gratuites.source} target="_blank" rel="noreferrer">awesome-free-llm-apis</a> (mise à jour du {gratuites.maj}). « Ajouter » préremplit tout : il ne reste qu'à coller la clé gratuite. Comme toute IA du marché, tes messages partent alors chez ce service.</p>
          <div className="pj-row"><button className="btn btn--ghost" onClick={majGratuites} disabled={majG}>{majG ? "Mise à jour…" : "Mettre la liste à jour"}</button></div>
          <ul className="pj-trash__list">
            {gratuites.services.map((g) => (
              <li key={g.id}><span><b>{g.drapeau} {g.nom}</b> <small>{g.modeles.length} modèle(s){g.cle_facultative ? " · marche sans clé" : " · clé gratuite"}{data.providers[g.id] ? " · ✓ ajouté" : ""}</small>
                <small className="page__sub" style={{ display: "block" }}>{g.modeles.slice(0, 4).map((m) => m.nom).join(", ")}{g.modeles.length > 4 ? "…" : ""}{g.modeles[0]?.limite && g.modeles[0].limite !== "—" ? ` — ${g.modeles[0].limite}` : ""}</small>
                {g.entrainement === "oui" && <small className="page__warn" style={{ display: "block" }}>⚠️ Tes messages peuvent servir à entraîner leurs modèles.</small>}
                {g.entrainement === "hors_ue" && <small className="page__sub" style={{ display: "block" }}>En Europe, tes messages ne servent pas à entraîner leurs modèles.</small>}
                {g.conditions.length > 0 && <small className="page__sub" style={{ display: "block" }}>Conditions : {g.conditions.join(", ")}.</small>}</span>
                <span><button className="btn btn--ghost" onClick={() => ajouterGratuit(g)} data-testid={`gratuit-${g.id}`}>{data.providers[g.id] ? "Modifier" : "Ajouter"}</button></span></li>
            ))}
          </ul>
        </div>
      )}
      {msg && <p className="page__sub" data-testid="cloud-msg">{msg}</p>}
      {error && <p className="page__warn">{error}</p>}
    </section>
  );
}
