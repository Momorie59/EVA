import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { confirmer } from "../../confirmer";

const NEW_TEMPLATE = `---
name: mon-skill
description: Quand utiliser ce skill, en une phrase
---
# Étapes
1. Première étape
2. Deuxième étape
`;

function SkillEditor({ name, initialRaw, isNew, onClose, onSaved }) {
  const [raw, setRaw] = useState(initialRaw);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setError("");
    const m = /^name:\s*(.+)$/im.exec(raw);
    const target = isNew ? (m ? m[1].trim().replace(/["']/g, "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^[-_]+|[-_]+$/g, "") : "") : name;
    if (!target) return setError("Ajoute une ligne « name: ... » dans l'en-tête.");
    setBusy(true);
    try {
      await api(`/api/skills/${encodeURIComponent(target)}`, { method: "PUT", body: JSON.stringify({ raw }) });
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card skilleditor">
      <span className="card__label">{isNew ? "Nouveau skill" : `Modifier « ${name} »`}</span>
      <textarea className="skilleditor__text" rows={16} value={raw} onChange={(e) => setRaw(e.target.value)} spellCheck={false} />
      {error && <p className="page__warn">{error}</p>}
      <div className="agentform__actions">
        <button className="btn" onClick={onClose}>Annuler</button>
        <button className="btn btn--primary" onClick={save} disabled={busy}>Enregistrer</button>
      </div>
    </div>
  );
}

function RepoBrowser({ onDone }) {
  const [src, setSrc] = useState("");
  const [cat, setCat] = useState(null);
  const [sel, setSel] = useState({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function load(e) {
    e?.preventDefault();
    setBusy(true); setError(""); setResult(null); setCat(null);
    try {
      const c = await api("/api/skills/catalog", { method: "POST", body: JSON.stringify({ source: src }) });
      setCat(c); setSel({});
    } catch (err) { setError(err.message); }
    setBusy(false);
  }
  const items = (cat?.items || []).filter((i) => !q.trim() || `${i.name || ""} ${i.folder} ${i.category} ${i.description || ""}`.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = {};
  items.forEach((i) => { (groups[i.category || "(racine)"] ||= []).push(i); });
  const selectable = items.filter((i) => i.ok && !i.installed);
  const chosen = Object.keys(sel).filter((k) => sel[k]);
  const setMany = (list, v) => setSel((s) => { const n = { ...s }; list.forEach((i) => { n[i.path] = v; }); return n; });

  async function install() {
    setBusy(true); setError("");
    try {
      const r = await api("/api/skills/install-many", { method: "POST", body: JSON.stringify({ source: cat.source, paths: chosen }) });
      setResult(r); setSel({});
      const c = await api("/api/skills/catalog", { method: "POST", body: JSON.stringify({ source: src }) });
      setCat(c); onDone();
    } catch (err) { setError(err.message); }
    setBusy(false);
  }

  return (
    <div className="card skillinstall" data-testid="repo-browser">
      <span className="card__label">Parcourir un dépôt GitHub</span>
      <form className="schedrow" onSubmit={load}>
        <input className="skillinstall__input" value={src} onChange={(e) => setSrc(e.target.value)} placeholder="ex. orchestra-research/AI-research-SKILLs" data-testid="repo-src" />
        <button className="btn btn--primary" type="submit" disabled={busy || !src.trim()} data-testid="repo-list">{busy && !cat ? "Lecture…" : "Lister les skills"}</button>
      </form>
      <p className="page__sub">EVA lit tout le dépôt et liste chaque skill ; coche ceux que tu veux installer. Un skill guide le comportement d'EVA : installe seulement des sources de confiance.</p>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {cat && (
        <>
          <p className="page__sub" data-testid="repo-count">{cat.total} skill(s) dans {cat.source}{cat.limited ? ` (les ${cat.items.length} premiers affichés)` : ""} — {cat.items.filter((i) => i.installed).length} déjà installé(s).</p>
          <div className="schedrow">
            <input className="skillinstall__input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrer (nom, catégorie, description)…" />
            <button className="btn" type="button" onClick={() => setMany(selectable, true)} data-testid="repo-all">Tout cocher ({selectable.length})</button>
            <button className="btn btn--ghost" type="button" onClick={() => setSel({})}>Tout décocher</button>
          </div>
          <div className="repo-list">
            {Object.entries(groups).map(([g, list]) => {
              const sub = list.filter((i) => i.ok && !i.installed);
              return (
                <div key={g}>
                  <div className="repo-cat">
                    <input type="checkbox" disabled={!sub.length} checked={!!sub.length && sub.every((i) => sel[i.path])} onChange={(e) => setMany(sub, e.target.checked)} aria-label={`Cocher la catégorie ${g}`} />
                    {g} <small className="page__sub">({list.length})</small>
                  </div>
                  {list.map((i) => (
                    <label key={i.path} className={`repo-item ${i.ok && !i.installed ? "" : "is-off"}`} data-testid="repo-item">
                      <input type="checkbox" disabled={!i.ok || i.installed} checked={!!sel[i.path]} onChange={(e) => setSel({ ...sel, [i.path]: e.target.checked })} />
                      <span><b>{i.name || i.folder}</b>{i.installed ? " — déjà installé" : ""}{!i.ok ? ` — illisible (${i.error})` : ""}</span>
                      {i.description && <small>{i.description}</small>}
                    </label>
                  ))}
                </div>
              );
            })}
          </div>
          <div className="agentform__actions">
            <button className="btn btn--primary" onClick={install} disabled={busy || !chosen.length} data-testid="repo-install">{busy ? "Installation…" : `Installer la sélection (${chosen.length})`}</button>
          </div>
        </>
      )}
      {result && (
        <p className="page__sub" data-testid="repo-result">
          {result.installed.length} installé(s){result.skipped.length ? `, ${result.skipped.length} déjà présent(s)` : ""}{result.failed.length ? `, ${result.failed.length} en échec (${result.failed.map((f) => f.error).slice(0, 3).join(" ; ")})` : ""}.
        </p>
      )}
    </div>
  );
}

export default function SkillsPage() {
  const [skills, setSkills] = useState(null);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState(null); // {name, raw, isNew}
  const [source, setSource] = useState("");
  const [installing, setInstalling] = useState(false);
  const [notice, setNotice] = useState("");
  const [proposal, setProposal] = useState(null); // {name, current, proposed, justification, model, examples, unchanged}
  const [optimizing, setOptimizing] = useState("");
  const [tab, setTab] = useState("skill");        // skill | agent
  const [q, setQ] = useState("");

  async function lot(names, action) {
    if (action === "supprimer" && !(await confirmer(`Supprimer ${names.length} élément(s) ?`))) return;
    try { await api("/api/skills/lot", { method: "POST", body: JSON.stringify({ names, action }) }); refresh(); } catch (e) { setError(e.message); }
  }
  const norm = (t) => (t || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const all = skills || [];
  const count = (k) => all.filter((s) => (s.kind || "skill") === k).length;
  const shown = all.filter((s) => (s.kind || "skill") === tab && (!q.trim() || norm(`${s.name} ${s.description} ${s.source}`).includes(norm(q.trim()))));
  const groups = Object.entries(shown.reduce((m, s) => { (m[s.source] = m[s.source] || []).push(s); return m; }, {})).sort(([a], [b]) => a.localeCompare(b));
  const actifs = all.filter((s) => (s.kind || "skill") === "skill" && s.actif !== false).length;

  const refresh = useCallback(() => {
    api("/api/skills")
      .then((d) => { setSkills(d.skills || []); setError(""); })
      .catch((e) => { setSkills((s) => s || []); setError(e.message); });
  }, []);
  useEffect(refresh, [refresh]);

  async function edit(name) {
    try {
      const s = await api(`/api/skills/${encodeURIComponent(name)}`);
      setEditor({ name, raw: s.raw, isNew: false });
    } catch (e) { setError(e.message); }
  }

  async function remove(name) {
    if (!(await confirmer(`Supprimer le skill « ${name} » ?`))) return;
    try {
      await api(`/api/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
      refresh();
    } catch (e) { setError(e.message); }
  }

  async function optimize(name) {
    setOptimizing(name); setError(""); setNotice("");
    try {
      const r = await api(`/api/skills/${encodeURIComponent(name)}/optimize`, { method: "POST" });
      setProposal({ ...r, edited: r.proposed });
    } catch (e) { setError(e.message); }
    finally { setOptimizing(""); }
  }

  async function applyProposal() {
    try {
      await api(`/api/skills/${encodeURIComponent(proposal.name)}`, { method: "PUT", body: JSON.stringify({ raw: proposal.edited }) });
      setNotice(`Skill « ${proposal.name} » mis à jour.`);
      setProposal(null);
      refresh();
    } catch (e) { setError(e.message); }
  }

  async function install(e) {
    e.preventDefault();
    setInstalling(true); setError(""); setNotice("");
    try {
      const r = await api("/api/skills/install", { method: "POST", body: JSON.stringify({ source }) });
      setNotice(`Skill « ${r.name} » installé depuis ${r.source}.`);
      setSource("");
      refresh();
    } catch (err) { setError(err.message); }
    finally { setInstalling(false); }
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1>Skills</h1>
        <span className="page__sub">Des savoir-faire en Markdown qu'EVA charge quand ta demande y correspond</span>
        <button className="btn btn--primary page__action" onClick={() => setEditor({ name: "", raw: NEW_TEMPLATE, isNew: true })}>
          + Nouveau skill
        </button>
      </header>
      <div className="page__body">
        {error && <p className="page__warn">{error}</p>}
        {notice && <p className="page__sub">{notice}</p>}
        {editor && (
          <SkillEditor
            key={editor.name || "new"}
            name={editor.name}
            initialRaw={editor.raw}
            isNew={editor.isNew}
            onClose={() => setEditor(null)}
            onSaved={() => { setEditor(null); refresh(); }}
          />
        )}
        {proposal && (
          <div className="card skilleditor">
            <span className="card__label">Amélioration proposée pour « {proposal.name} »</span>
            <p className="page__sub">
              Générée par {proposal.model} à partir de {proposal.examples} utilisations récentes.
              {proposal.unchanged ? " Le modèle n'a rien changé." : ""} {proposal.justification && `Justification : ${proposal.justification}`}
            </p>
            <div className="skilldiff">
              <div><strong>Actuel</strong><pre>{proposal.current}</pre></div>
              <div><strong>Proposé (modifiable)</strong>
                <textarea className="skilleditor__text" rows={14} value={proposal.edited} onChange={(e) => setProposal({ ...proposal, edited: e.target.value })} spellCheck={false} />
              </div>
            </div>
            <div className="agentform__actions">
              <button className="btn" onClick={() => setProposal(null)}>Ignorer</button>
              <button className="btn btn--primary" onClick={applyProposal} disabled={proposal.unchanged}>Appliquer</button>
            </div>
          </div>
        )}
        <RepoBrowser onDone={refresh} />
        <form className="card skillinstall" onSubmit={install}>
          <span className="card__label">Installer depuis GitHub</span>
          <div className="schedrow">
            <input
              className="skillinstall__input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="owner/repo  ou  owner/repo/dossier/skill  ou URL github.com"
              required
            />
            <button className="btn btn--primary" type="submit" disabled={installing || !source.trim()}>Installer</button>
          </div>
          <p className="page__sub">Le dépôt doit contenir un fichier SKILL.md. Relis-le avant de t'en servir : un skill guide le comportement d'EVA.</p>
        </form>
        <div className="card" data-testid="skills-rangement">
          <div className="schedrow">
            <button className={`btn ${tab === "skill" ? "btn--primary" : ""}`} onClick={() => setTab("skill")} data-testid="tab-skills">Skills ({count("skill")})</button>
            <button className={`btn ${tab === "agent" ? "btn--primary" : ""}`} onClick={() => setTab("agent")} data-testid="tab-agents">Agents ({count("agent")})</button>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Chercher un nom ou un mot…" style={{ flex: 1 }} data-testid="skills-search" />
          </div>
          <p className="page__sub">
            {tab === "skill"
              ? `${actifs} skill(s) actif(s) sur ${count("skill")}. EVA n'en présente que 30 au modèle : désactive ceux dont tu ne te sers pas (ils restent installés).`
              : "Des rôles spécialisés (relecteur, sécurité…) qu'EVA fait travailler seuls, en lecture seule : « fais relire ce fichier par le security-reviewer ». Désactivé = EVA ne l'appelle plus."}
          </p>
        </div>
        {skills && shown.length === 0 && <p className="dash-empty">{q.trim() ? "Rien ne correspond." : tab === "skill" ? "Aucun skill pour l'instant." : "Aucun agent installé : Parcourir un dépôt GitHub › agents."}</p>}
        {groups.map(([src, list]) => (
          <details key={src} className="card" open={groups.length === 1 || !!q.trim()} data-testid="skills-groupe">
            <summary style={{ cursor: "pointer" }}><strong>{src}</strong> <span className="skilltag">{list.length}</span></summary>
            <div className="schedrow" style={{ margin: "8px 0" }}>
              <button className="btn" onClick={() => lot(list.map((s) => s.name), "activer")}>Tout activer</button>
              <button className="btn" onClick={() => lot(list.map((s) => s.name), "desactiver")}>Tout désactiver</button>
              <button className="btn btn--danger" onClick={() => lot(list.map((s) => s.name), "supprimer")}>Tout supprimer</button>
            </div>
            {list.map((s) => (
              <div key={s.name} className="acard" style={{ opacity: s.actif === false ? 0.5 : 1 }} data-testid="skill-ligne">
                <div className="acard__head">
                  <div className="acard__title">
                    {s.valid && <input type="checkbox" checked={s.actif !== false} onChange={() => lot([s.name], s.actif === false ? "activer" : "desactiver")} title="Actif : EVA peut s'en servir" aria-label={`Activer ${s.name}`} />}
                    <strong>{s.name}</strong>
                  </div>
                  <div className="acard__actions">
                    {s.valid && tab === "skill" && (
                      <button className="btn" onClick={() => optimize(s.name)} disabled={optimizing === s.name} title="Propose une version améliorée à partir de l'historique d'utilisation">
                        {optimizing === s.name ? "Analyse…" : "Améliorer"}
                      </button>
                    )}
                    <button className="btn" onClick={() => edit(s.name)}>{s.valid ? "Modifier" : "Réparer"}</button>
                    <button className="btn btn--danger" onClick={() => remove(s.name)}>×</button>
                  </div>
                </div>
                <p className="acard__instruction">{(s.description || "").slice(0, 220)}</p>
              </div>
            ))}
          </details>
        ))}
      </div>
    </section>
  );
}
