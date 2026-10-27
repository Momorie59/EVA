import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

const SORTS = [["downloads", "Plus téléchargés"], ["trending", "Tendance"], ["likes", "Plus aimés"], ["recent", "Récents"]];
const BADGE = { gpu: ["✅", "is-gpu"], mixed: ["⚠️", "is-mixed"], no: ["⛔", "is-no"] };
const fmtN = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${Math.round(n / 1e3)} k` : String(n || 0));

function Fit({ a }) {
  if (!a) return <span className="hf-fit">taille inconnue</span>;
  const [icon, cls] = BADGE[a.level];
  return <span className={`hf-fit ${cls}`} title={a.detail} data-level={a.level}>{icon} {a.label}</span>;
}

// Catalogue Hugging Face (GGUF) : recherche, tailles par quantification, et alerte selon la puissance du serveur IA.
export default function HFCatalog({ onPull }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("downloads");
  const [onlyFit, setOnlyFit] = useState(false);
  const [res, setRes] = useState(null);
  const [hw, setHw] = useState({ vram_gb: 6, ram_gb: 16 });
  const [hwDraft, setHwDraft] = useState({ vram_gb: "6", ram_gb: "16" });
  const [open, setOpen] = useState("");
  const [files, setFiles] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api("/api/models/hardware").then((h) => { setHw(h); setHwDraft({ vram_gb: String(h.vram_gb), ram_gb: String(h.ram_gb) }); }).catch(() => {}); }, []);

  async function search(e) {
    e?.preventDefault();
    setBusy(true); setError(""); setOpen("");
    try { const r = await api(`/api/models/hf/search?q=${encodeURIComponent(q)}&sort=${sort}`); setRes(r.results); setHw(r.hardware); }
    catch (err) { setError(err.message); setRes(null); }
    setBusy(false);
  }
  async function saveHw(e) {
    e.preventDefault();
    try {
      const h = await api("/api/models/hardware", { method: "PUT", body: JSON.stringify({ vram_gb: parseFloat(hwDraft.vram_gb), ram_gb: parseFloat(hwDraft.ram_gb) }) });
      setHw(h); setFiles({}); if (res) search();
    } catch (err) { setError(err.message); }
  }
  async function toggle(repo) {
    if (open === repo) { setOpen(""); return; }
    setOpen(repo); setError("");
    if (!files[repo]) {
      try { const f = await api(`/api/models/hf/files?repo=${encodeURIComponent(repo)}`); setFiles((s) => ({ ...s, [repo]: f.files })); }
      catch (err) { setError(err.message); setOpen(""); }
    }
  }
  async function download(f) {
    if (f.level === "no" && !(await confirmer(`${f.label}.\n${f.detail}\nTélécharger quand même ?`))) return;
    if (f.level === "mixed" && !(await confirmer(`${f.label}.\n${f.detail}\nTélécharger ?`))) return;
    onPull(f.ollama);
  }

  const shown = (res || []).filter((m) => !onlyFit || !m.q4_estimate || m.q4_estimate.level !== "no");
  return (
    <div className="hfcat" data-testid="hf-catalog">
      <span className="card__label">Catalogue Hugging Face</span>
      <form className="hf-hw" onSubmit={saveHw}>
        <span>Puissance du serveur IA :</span>
        <label>Mémoire vidéo <input type="number" min="0" step="0.5" value={hwDraft.vram_gb} onChange={(e) => setHwDraft({ ...hwDraft, vram_gb: e.target.value })} data-testid="hw-vram" /> Go</label>
        <label>RAM <input type="number" min="0" step="1" value={hwDraft.ram_gb} onChange={(e) => setHwDraft({ ...hwDraft, ram_gb: e.target.value })} data-testid="hw-ram" /> Go</label>
        <button className="btn" type="submit" data-testid="hw-save">Enregistrer</button>
      </form>
      <form className="schedrow" onSubmit={search}>
        <input className="skillinstall__input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Chercher un modèle (ex. qwen, llama, mistral, code…)" data-testid="hf-q" />
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Tri">{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <button className="btn btn--primary" type="submit" disabled={busy} data-testid="hf-search">{busy ? "…" : "Chercher"}</button>
      </form>
      <label className="hf-only"><input type="checkbox" checked={onlyFit} onChange={(e) => setOnlyFit(e.target.checked)} /> Masquer ceux qui sont trop gros pour mon serveur</label>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {res && shown.length === 0 && <p className="page__sub">Aucun résultat.</p>}
      <ul className="hf-list">
        {shown.map((m) => (
          <li key={m.repo} data-testid="hf-item">
            <button type="button" className="hf-row" onClick={() => toggle(m.repo)} aria-expanded={open === m.repo}>
              <span className="hf-name">{m.repo}</span>
              <span className="hf-meta">{m.params_b ? `${m.params_b} Md · ` : ""}⬇ {fmtN(m.downloads)} · ♥ {fmtN(m.likes)}</span>
              <Fit a={m.q4_estimate} />
            </button>
            {open === m.repo && (
              <div className="hf-files" data-testid="hf-files">
                {!files[m.repo] && <p className="page__sub">Chargement des versions…</p>}
                {files[m.repo]?.length === 0 && <p className="page__sub">Aucune version GGUF exploitable.</p>}
                {files[m.repo]?.map((f) => (
                  <div key={f.quant} className="hf-file" data-testid="hf-file">
                    <b>{f.quant}</b><span>{f.size_gb} Go</span><Fit a={f} />
                    <button type="button" className="btn" onClick={() => download(f)} data-testid="hf-download">Télécharger</button>
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="page__sub">Estimation pour {hw.vram_gb} Go de mémoire vidéo et {hw.ram_gb} Go de RAM. Les modèles viennent de Hugging Face (accès Internet requis) ; la conversation reste 100 % locale.</p>
    </div>
  );
}
