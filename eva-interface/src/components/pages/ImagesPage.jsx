import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../AuthGate";
import { confirmer } from "../../confirmer";

const readFile = (f) => new Promise((ok, ko) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => ko(new Error("Fichier illisible.")); r.readAsDataURL(f); });
const save = (src, name) => { const a = document.createElement("a"); a.href = src; a.download = name || "image-eva.png"; document.body.appendChild(a); a.click(); a.remove(); };
const ago = (t) => { const d = Date.now() / 1000 - t; return d < 3600 ? `${Math.max(1, Math.round(d / 60))} min` : d < 86400 ? `${Math.round(d / 3600)} h` : `${Math.round(d / 86400)} j`; };

// Onglet Images : créer, retoucher et retrouver les images d'EVA. Les images non gardées sont purgées automatiquement.
function Thumb({ g, onOpen, choix, onChoix }) {
  const coche = choix && choix.has(g.name);
  return (
    <figure className={`imgthumb${choix ? " imgthumb--choix" : ""}${coche ? " is-coche" : ""}`}>
      {choix && <input type="checkbox" className="imgthumb__case" checked={coche} onChange={() => onChoix(g.name)} aria-label="Sélectionner l'image" data-testid={`images-coche-${g.name}`} />}
      <img src={g.thumb} alt={g.prompt || g.name} title={g.prompt} onClick={() => (choix ? onChoix(g.name) : onOpen(g))} data-testid={`images-thumb-${g.name}`} />
      <figcaption>{g.pinned ? "📌 " : ""}{g.kind === "edit" ? "modifiée" : "créée"} · {ago(g.at)}</figcaption>
    </figure>
  );
}

export default function ImagesPage() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const [items, setItems] = useState([]); const [filter, setFilter] = useState("all");
  const [prompt, setPrompt] = useState(""); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [msg, setMsg] = useState("");
  const [shown, setShown] = useState(null);             // image ouverte : {name, image, prompt, pinned, kind}
  const [source, setSource] = useState(null);           // image à retoucher : {name} (galerie) ou {data, preview} (photo envoyée)
  const [instr, setInstr] = useState("");
  const [gcfg, setGcfg] = useState(null); const [models, setModels] = useState(null);
  const fileRef = useRef(null);
  const [choix, setChoix] = useState(null);             // mode sélection : Set des noms cochés (null = mode normal)
  const basculer = (n) => setChoix((c) => { const x = new Set(c); if (x.has(n)) x.delete(n); else x.add(n); return x; });

  const load = useCallback(() => api("/api/images/gallery").then((g) => setItems(g.items)).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
    if (admin) {
      api("/api/images/gallery-config").then(setGcfg).catch(() => {});
      api("/api/images/models").then(setModels).catch(() => {});
    }
  }, [load, admin]);

  async function run(fn, wait) {
    setError(""); setMsg(wait || ""); setBusy(true);
    try { return await fn(); } catch (e) { setError(e.message); setMsg(""); return null; } finally { setBusy(false); }
  }
  async function create(e) {
    e.preventDefault(); if (!prompt.trim()) return;
    const r = await run(() => api("/api/images/generate", { method: "POST", body: JSON.stringify({ prompt }) }), "Création en cours (la première image charge le modèle : jusqu'à une minute)…");
    if (r) { setMsg(""); setShown({ ...r, kind: "create", pinned: false }); setPrompt(""); load(); }
  }
  async function edit(e) {
    e.preventDefault(); if (!instr.trim() || !source) return;
    const body = source.data ? { instruction: instr, data: source.data } : { instruction: instr, image: source.name };
    const r = await run(() => api("/api/images/edit", { method: "POST", body: JSON.stringify(body) }), "Modification en cours…");
    if (r) { setMsg(r.summary ? `Fait : ${r.summary}.` : ""); setShown({ ...r, prompt: instr, kind: "edit", pinned: false }); setSource({ name: r.name }); setInstr(""); load(); }
  }
  async function pick(e) {
    const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
    if (!f.type.startsWith("image/")) return setError("Choisis un fichier image (png, jpg…).");
    try { const data = await readFile(f); setSource({ data, preview: data, label: f.name }); setMsg(""); setError(""); } catch (err) { setError(err.message); }
  }
  async function open(it) {
    const r = await run(() => api(`/api/images/item/${it.name}`));
    if (r) setShown({ name: it.name, image: r.image, prompt: it.prompt, final: it.final, kind: it.kind, pinned: it.pinned });
  }
  async function pin(v) {
    const r = await run(() => api(`/api/images/item/${shown.name}/pin`, { method: "POST", body: JSON.stringify({ pinned: v }) }));
    if (r) { setShown((s) => ({ ...s, pinned: v })); load(); }
  }
  async function remove() {
    if (!(await confirmer("Supprimer cette image ?"))) return;
    const r = await run(() => api(`/api/images/item/${shown.name}`, { method: "DELETE" }));
    if (r) { if (source?.name === shown.name) setSource(null); setShown(null); load(); }
  }
  // Actions sur plusieurs images à la fois
  async function enLot(fn, fait) {
    const noms = [...(choix || [])]; if (!noms.length) return;
    setError(""); setBusy(true); let ok = 0;
    for (const n of noms) { try { await fn(n); ok += 1; } catch (e) { setError(e.message); } }
    setBusy(false); setMsg(fait(ok)); load();
    return ok;
  }
  async function supprimerChoix() {
    const n = choix?.size || 0;
    if (!n || !(await confirmer(`Supprimer ${n} image${n > 1 ? "s" : ""} ? C'est définitif.`))) return;
    await enLot((x) => api(`/api/images/item/${x}`, { method: "DELETE" }), (k) => `${k} image${k > 1 ? "s" : ""} supprimée${k > 1 ? "s" : ""}.`);
    if (shown && choix.has(shown.name)) setShown(null);
    if (source?.name && choix.has(source.name)) setSource(null);
    setChoix(new Set());
  }
  const garderChoix = (v) => enLot((x) => api(`/api/images/item/${x}/pin`, { method: "POST", body: JSON.stringify({ pinned: v }) }),
    (k) => `${k} image${k > 1 ? "s" : ""} ${v ? "gardée" : "plus gardée"}${k > 1 ? "s" : ""}.`);
  const telechargerChoix = () => enLot(async (x) => { const r = await api(`/api/images/item/${x}`); save(r.image, x); await new Promise((t) => setTimeout(t, 400)); },
    (k) => `${k} image${k > 1 ? "s" : ""} enregistrée${k > 1 ? "s" : ""} (si le navigateur le demande, autorise les téléchargements multiples).`);

  async function saveGcfg(e) {
    e.preventDefault();
    const r = await run(() => api("/api/images/gallery-config", { method: "PUT", body: JSON.stringify({ keep_days: +gcfg.keep_days || 0, max_items: +gcfg.max_items || 0 }) }));
    if (r) { setGcfg(r); setMsg("Réglage de purge enregistré."); }
  }
  async function purgeNow() {
    const r = await run(() => api("/api/images/purge", { method: "POST" }));
    if (r) { setMsg(`${r.removed ?? 0} image(s) purgée(s).`); load(); }
  }
  async function useModel(id) {
    const r = await run(() => api("/api/images/models/use", { method: "POST", body: JSON.stringify({ id }) }));
    if (r) { setModels((m) => ({ ...m, active: id })); setMsg("Modèle changé."); }
  }
  const shownList = items.filter((i) => filter === "all" || (filter === "kept" ? i.pinned : filter === "edit" ? i.kind === "edit" : i.kind !== "edit"));
  // administrateur : une image de chaque personne, rangée dans le dossier de son auteur (les utilisateurs ne voient que les leurs)
  const auth0 = auth;
  const folders = auth0.required && auth0.role === "admin" && shownList.some((g) => g.owner) ? [...new Set(shownList.map((g) => g.owner || ""))]
    .sort((x, y) => (x === "" ? -1 : y === "" ? 1 : x.localeCompare(y)))
    .map((o) => ({ owner: o, mine: o === "", label: o === "" ? `${auth0.user || "admin"} (toi)` : o, items: shownList.filter((g) => (g.owner || "") === o) })) : null;
  const installed = (models?.items || []).filter((m) => m.installed);
  const src = source ? (source.preview || null) : null;

  return (
    <section className="page" data-testid="images-page">
      <header className="page__header"><h1>Images</h1><span className="page__sub">Crée, retouche et retrouve tes images. Celles que tu ne gardes pas sont supprimées automatiquement.</span></header>
      <div className="page__body">
        <div className="card">
          <form className="agentform" onSubmit={create}>
            <label className="field"><span>Créer une image</span>
              <input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="ex. un renard roux dans la neige, style aquarelle" data-testid="images-prompt" /></label>
            {admin && installed.length > 1 && (
              <label className="field"><span>Modèle</span>
                <select value={models.active || ""} onChange={(e) => useModel(e.target.value)} data-testid="images-model">
                  {!installed.some((m) => m.id === models.active) && <option value={models.active || ""}>{models.active || "modèle par défaut"}</option>}
                  {installed.map((m) => <option key={m.id} value={m.id}>{m.title || m.id}</option>)}
                </select></label>
            )}
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={busy || !prompt.trim()} data-testid="images-create">Créer</button></div>
          </form>
        </div>

        <div className="card" data-testid="images-edit-card">
          <span className="card__label">Modifier une image</span>
          <p className="page__sub">Envoie une photo ou ouvre une image de la galerie, puis dis ce que tu veux : « mets en noir et blanc », « recadre en carré », « enlève le poteau », « mets la voiture en rouge », « transforme en aquarelle »…</p>
          <div className="agentform__actions">
            <button className="btn" type="button" onClick={() => fileRef.current?.click()} data-testid="images-import">Envoyer une photo…</button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={pick} data-testid="images-file" />
            {source && <button className="btn btn--ghost" type="button" onClick={() => setSource(null)}>Retirer</button>}
          </div>
          {source && (
            <form className="agentform" onSubmit={edit}>
              {src ? <img src={src} alt="Image à modifier" style={{ maxWidth: 220, borderRadius: 8 }} /> : <p className="page__sub" data-testid="images-source">Image de la galerie : {source.name}</p>}
              <label className="field"><span>Que faut-il changer ?</span>
                <input value={instr} onChange={(e) => setInstr(e.target.value)} placeholder="ex. enlève le poteau à gauche" data-testid="images-instr" /></label>
              <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={busy || !instr.trim()} data-testid="images-edit">Modifier</button></div>
            </form>
          )}
        </div>

        {error && <p className="page__warn" role="alert" data-testid="images-error">{error}</p>}
        {msg && <p className="page__sub" data-testid="images-msg">{msg}</p>}

        {shown && (
          <div className="card" data-testid="images-viewer">
            <img src={shown.image} alt={shown.prompt} style={{ maxWidth: "100%", maxHeight: "60vh", objectFit: "contain", borderRadius: 10 }} />
            <p className="page__sub">{shown.prompt}</p>
            <div className="agentform__actions">
              <button className="btn" onClick={() => save(shown.image, shown.name)} data-testid="images-save">Enregistrer</button>
              <button className="btn" onClick={() => { setSource({ name: shown.name }); setMsg("Image prête à modifier : dis ce qu'il faut changer."); window.scrollTo?.({ top: 0, behavior: "smooth" }); }} data-testid="images-modify">Modifier</button>
              <button className="btn" onClick={() => pin(!shown.pinned)} data-testid="images-pin">{shown.pinned ? "Ne plus garder" : "Garder (jamais purgée)"}</button>
              <button className="btn btn--ghost" onClick={remove} data-testid="images-delete">Supprimer</button>
              <button className="btn btn--ghost" onClick={() => setShown(null)}>Fermer</button>
            </div>
          </div>
        )}

        <div className="card">
          <span className="card__label">Galerie ({shownList.length})</span>
          <div className="pj-row imgchoix" data-testid="images-choix-barre">
            {!choix ? (
              shownList.length > 0 && <button className="btn btn--ghost" onClick={() => setChoix(new Set())} data-testid="images-selectionner">☑ Sélectionner</button>
            ) : (
              <>
                <b>{choix.size} sélectionnée{choix.size > 1 ? "s" : ""}</b>
                <button className="btn btn--ghost" onClick={() => setChoix(choix.size === shownList.length ? new Set() : new Set(shownList.map((g) => g.name)))} data-testid="images-tout">{choix.size === shownList.length ? "Tout désélectionner" : "Tout sélectionner"}</button>
                <button className="btn btn--danger" disabled={busy || !choix.size} onClick={supprimerChoix} data-testid="images-suppr-choix">🗑️ Supprimer</button>
                <button className="btn" disabled={busy || !choix.size} onClick={() => garderChoix(true)} data-testid="images-garder-choix">📌 Garder</button>
                <button className="btn btn--ghost" disabled={busy || !choix.size} onClick={() => garderChoix(false)}>Ne plus garder</button>
                <button className="btn btn--ghost" disabled={busy || !choix.size} onClick={telechargerChoix} data-testid="images-dl-choix">⬇️ Enregistrer</button>
                <button className="btn btn--ghost" onClick={() => setChoix(null)} data-testid="images-choix-fin">Terminer</button>
              </>
            )}
          </div>
          <div className="pj-sbx__tabs" data-testid="images-filters">
            {[["all", "Toutes"], ["create", "Créées"], ["edit", "Modifiées"], ["kept", "Gardées"]].map(([k, l]) => <button key={k} className={filter === k ? "is-on" : ""} onClick={() => setFilter(k)}>{l}</button>)}
          </div>
          {!shownList.length && <p className="page__sub">Aucune image pour l'instant.</p>}
          {folders ? (
            <div className="imgfolders" data-testid="images-gallery">
              {folders.map((f) => (
                <details key={f.owner} className="imgfolder" open={f.mine || folders.length < 3} data-testid={`imgfolder-${f.owner || "me"}`}>
                  <summary><span aria-hidden="true">📁</span> <b>{f.label}</b> <span className="convs__count">{f.items.length}</span></summary>
                  <div className="imggrid">{f.items.map((g) => <Thumb key={g.name} g={g} onOpen={open} choix={choix} onChoix={basculer} />)}</div>
                </details>
              ))}
            </div>
          ) : (
            <div className="imggrid" data-testid="images-gallery">{shownList.map((g) => <Thumb key={g.name} g={g} onOpen={open} choix={choix} onChoix={basculer} />)}</div>
          )}
        </div>

        {admin && gcfg && (
          <form className="card agentform" onSubmit={saveGcfg} data-testid="images-purge">
            <span className="card__label">Purge automatique</span>
            <p className="page__sub">Les images non gardées sont supprimées après ce délai, et au-delà de ce nombre (les plus anciennes d'abord). 0 = pas de limite.</p>
            <label className="field"><span>Garder les images (jours)</span><input type="number" min="0" max="3650" value={gcfg.keep_days} onChange={(e) => setGcfg({ ...gcfg, keep_days: e.target.value })} data-testid="purge-days" /></label>
            <label className="field"><span>Nombre maximum d'images</span><input type="number" min="0" max="5000" value={gcfg.max_items} onChange={(e) => setGcfg({ ...gcfg, max_items: e.target.value })} data-testid="purge-max" /></label>
            <div className="agentform__actions">
              <button className="btn btn--primary" type="submit" data-testid="purge-save">Enregistrer</button>
              <button className="btn" type="button" onClick={purgeNow} data-testid="purge-now">Purger maintenant</button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
