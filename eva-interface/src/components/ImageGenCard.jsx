import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "./AuthGate";

// Génération d'images : serveur eva-imagegen (Stable Diffusion) sur le serveur IA. Réglages, essai, création directe et galerie.
export default function ImageGenCard() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const [cfg, setCfg] = useState(null); const [st, setSt] = useState(null);
  const [msg, setMsg] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const loadStatus = useCallback(() => api("/api/images/status").then(setSt).catch(() => setSt(null)), []);
  useEffect(() => { api("/api/images/config").then(setCfg).catch((e) => setError(e.message)); loadStatus(); }, [loadStatus]);
  // Après une mise à jour du serveur d'images (autre carte) : l'état se rafraîchit tout seul.
  useEffect(() => { window.addEventListener("eva:imagecfg", loadStatus); return () => window.removeEventListener("eva:imagecfg", loadStatus); }, [loadStatus]);
  if (!cfg) return <div className="card routercard"><span className="card__label">Génération d'images</span>{error && <p className="page__warn">{error}</p>}</div>;
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  async function save(e) {
    e?.preventDefault(); setError(""); setMsg("");
    try { setCfg(await api("/api/images/config", { method: "PUT", body: JSON.stringify({ ...cfg, steps: +cfg.steps || 0, size: +cfg.size || 0 }) })); setMsg("Enregistré."); loadStatus(); window.dispatchEvent(new Event("eva:imagecfg")); return true; }
    catch (err) { setError(err.message); return false; }
  }
  async function detect() {
    setError(""); setMsg(""); setBusy(true);
    try { const f = await api("/api/images/detect", { method: "POST" }); setMsg(`Serveur trouvé : ${f.url}`); setCfg(await api("/api/images/config")); loadStatus(); window.dispatchEvent(new Event("eva:imagecfg")); }
    catch (err) { setError(err.message); }
    setBusy(false);
  }
  async function test() {
    if (!(await save())) return;
    setBusy(true); setMsg("Test en cours (la première image charge le modèle : jusqu'à une minute)…");
    try { const r = await api("/api/images/test", { method: "POST" }); setMsg(`Le serveur d'images répond (image de ${Math.round(r.bytes / 1024)} Ko).`); loadStatus(); }
    catch (err) { setError(err.message); setMsg(""); }
    setBusy(false);
  }
  const models = st?.own ? st.models : null;
  return (
    <div className="card routercard" data-testid="imagegen-card">
      <span className="card__label">Génération d'images</span>
      <p className="page__sub">« EVA, crée une image d'un chien » : la demande part vers le serveur d'images (eva-imagegen, sur ton serveur IA). EVA traduit et enrichit ta description en anglais avant, car les modèles d'images la comprennent mieux ainsi. Le modèle « vision » sert seulement à comprendre tes photos.</p>
      <p className="page__sub" data-testid="img-status">
        {!st || !st.configured ? "Aucun serveur configuré." : st.up
          ? `✔ Serveur joignable${st.own ? ` · ${st.device === "cuda" ? `carte ${st.gpu?.name || "graphique"}${st.gpu?.vram_total_mb ? ` (${Math.round(st.gpu.vram_total_mb / 1024)} Go)` : ""}` : "processeur (lent)"} · modèle ${String(st.model).split("/").pop()} ${st.loaded ? "chargé" : "au repos"}${st.defaults?.turbo ? " · mode rapide (Turbo)" : ""}` : " (Stable Diffusion WebUI / Forge)"}`
          : `✘ Serveur injoignable. ${st.error || ""}`}
      </p>
      {admin && (
        <form className="agentform" onSubmit={save}>
          <div className="agentform__actions">
            <button className="btn btn--primary" type="button" onClick={detect} disabled={busy} data-testid="img-detect">Détecter le serveur</button>
          </div>
          <label className="field"><span>Adresse du serveur</span>
            <input value={cfg.url} onChange={(e) => set("url", e.target.value)} placeholder="http://192.168.1.20:7860" data-testid="img-url" /></label>
          <label className="field"><span>Type d'API</span>
            <select value={cfg.kind} onChange={(e) => set("kind", e.target.value)} data-testid="img-kind">
              <option value="a1111">eva-imagegen / Stable Diffusion WebUI / Forge</option>
              <option value="openai">Compatible OpenAI (/v1/images/generations)</option>
            </select></label>
          <label className="field"><span>Modèle (liste du serveur, ou nom « auteur/modèle » du hub Hugging Face : téléchargé au 1er dessin)</span>
            <input list="img-models" value={cfg.model} onChange={(e) => set("model", e.target.value)} data-testid="img-model"
              placeholder={models ? "modèle actif du serveur (ou tape un nom du hub, ex. SG161222/Realistic_Vision_V5.1_noVAE)" : "laisser vide = modèle actif du serveur"} />
            {models && <datalist id="img-models">{models.map((m) => <option key={m} value={m} />)}</datalist>}</label>
          <label className="field"><span>Étapes (0 = automatique selon le modèle)</span><input type="number" min="0" max="80" value={cfg.steps} onChange={(e) => set("steps", e.target.value)} /></label>
          <label className="field"><span>Taille</span>
            <select value={cfg.size} onChange={(e) => set("size", e.target.value)}><option value={0}>automatique</option>{[256, 384, 512, 640, 768, 1024].map((s) => <option key={s} value={s}>{s} px</option>)}</select></label>
          <label className="field"><span>À éviter (anglais)</span><input value={cfg.negative || ""} onChange={(e) => set("negative", e.target.value)} /></label>
          <label className="field"><span>Jeton du serveur (si IMAGEGEN_TOKEN est défini)</span><input type="password" value={cfg.token || ""} onChange={(e) => set("token", e.target.value)} autoComplete="off" /></label>
          <label><input type="checkbox" checked={!!cfg.enhance} onChange={(e) => set("enhance", e.target.checked)} data-testid="img-enhance" /> Traduire et enrichir ma description en anglais avant de dessiner</label>
          <div className="agentform__actions">
            <button className="btn btn--primary" type="submit" data-testid="img-save">Enregistrer</button>
            <button className="btn" type="button" onClick={test} disabled={busy || !cfg.url} data-testid="img-test">Tester</button>
          </div>
        </form>
      )}
      {error && <p className="page__warn" role="alert" data-testid="img-error">{error}</p>}
      {msg && <p className="page__sub" data-testid="img-msg">{msg}</p>}
      <p className="page__sub">Créer, retoucher et retrouver tes images : onglet <strong>Images</strong>. Choisir le modèle : carte « Modèles d'images » juste en dessous.</p>
    </div>
  );
}
