import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../AuthGate";
import { api } from "../../api";
import MessageText from "../MessageText";
import { confirmer } from "../../confirmer";

// Carnets partagés, façon OneNote : carnets → sections → pages. Partage par personne, groupe ou tout le monde (lecture ou modification).
const ICONS = ["📓", "📒", "📔", "📕", "📗", "📘", "🏝️", "🏠", "🍳", "💼", "🎓", "🎮", "💡", "🧾"];
const TONES = { jaune: "#ffcb52", rose: "#ff8fb1", bleu: "#7aa2ff", vert: "#6fd6a4", orange: "#ff9f6a", violet: "#b58cff" };
const ago = (ts) => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? "à l'instant" : s < 3600 ? `il y a ${Math.floor(s / 60)} min` : s < 86400 ? `il y a ${Math.floor(s / 3600)} h` : `il y a ${Math.floor(s / 86400)} j`; };
const lsGet = (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignoré */ } };

function SharePanel({ nb, onClose, onSaved }) {
  const [people, setPeople] = useState({ users: [], groups: [] });
  const [shares, setShares] = useState(nb.shares || []);
  const [target, setTarget] = useState("");
  const [edit, setEdit] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/notebooks/people").then(setPeople).catch(() => {}); }, []);
  const label = (s) => (s.kind === "all" ? "Tout le monde" : s.kind === "group" ? `Groupe ${people.groups.find((g) => g.id === s.name)?.label || s.name}` : s.name);
  function add() {
    if (!target) return;
    const [kind, name] = target.split(":");
    setShares((a) => [...a.filter((x) => !(x.kind === kind && x.name === (name || ""))), { kind, name: name || "", edit }]);
    setTarget("");
  }
  async function save() {
    setErr("");
    try { const d = await api(`/api/notebooks/${nb.id}/shares`, { method: "PUT", body: JSON.stringify({ shares }) }); onSaved(d.shares); onClose(); }
    catch (e) { setErr(e.message); }
  }
  return (
    <div className="nbshare card" data-testid="nb-share" role="dialog" aria-label="Partager le carnet">
      <span className="card__label">Partager « {nb.title} »</span>
      <p className="card__hint">Les personnes choisies voient ce carnet dans leur liste. En lecture seule elles ne peuvent rien changer ; en modification elles écrivent dans les pages comme toi.</p>
      <ul className="nbshare__list">
        {shares.length === 0 && <li className="card__hint">Privé : toi seul(e) (et l'administrateur).</li>}
        {shares.map((s, i) => (
          <li key={`${s.kind}-${s.name}`}>
            <span>{s.kind === "all" ? "🌍" : s.kind === "group" ? "👪" : "👤"} {label(s)}</span>
            <select value={s.edit ? "edit" : "read"} onChange={(e) => setShares(shares.map((x, j) => (j === i ? { ...x, edit: e.target.value === "edit" } : x)))} data-testid={`share-perm-${i}`}>
              <option value="read">Lecture seule</option><option value="edit">Peut modifier</option>
            </select>
            <button className="btn btn--ghost" onClick={() => setShares(shares.filter((_, j) => j !== i))} aria-label="Retirer">✕</button>
          </li>
        ))}
      </ul>
      <div className="schedrow">
        <select value={target} onChange={(e) => setTarget(e.target.value)} data-testid="share-target">
          <option value="">Ajouter une personne ou un groupe…</option>
          <option value="all">🌍 Tout le monde</option>
          {people.users.map((u) => <option key={u} value={`user:${u}`}>👤 {u}</option>)}
          {people.groups.map((g) => <option key={g.id} value={`group:${g.id}`}>👪 Groupe {g.label}</option>)}
        </select>
        <select value={edit ? "edit" : "read"} onChange={(e) => setEdit(e.target.value === "edit")} data-testid="share-newperm"><option value="read">Lecture seule</option><option value="edit">Peut modifier</option></select>
        <button className="btn" onClick={add} disabled={!target} data-testid="share-add">Ajouter</button>
      </div>
      {err && <p className="page__warn">{err}</p>}
      <div className="agentform__actions">
        <button className="btn btn--primary" onClick={save} data-testid="share-save">Enregistrer le partage</button>
        <button className="btn btn--ghost" onClick={onClose}>Annuler</button>
      </div>
    </div>
  );
}

function Editor({ nb, page, canEdit, me, onSaved }) {
  const [title, setTitle] = useState(page.title);
  const [text, setText] = useState(page.text);
  const [preview, setPreview] = useState(!canEdit);
  const [state, setState] = useState("saved");     // saved | dirty | saving | conflict
  const [conflict, setConflict] = useState(null);
  useEffect(() => { if (!canEdit) setPreview(true); }, [canEdit]);       // droit retiré pendant qu'on regarde : retour en lecture seule
  const base = useRef(page.updated);
  const dirty = useRef(false);
  const timer = useRef(null);
  const latest = useRef({ title, text });
  latest.current = { title, text };

  // une autre personne a modifié la page pendant qu'on la regarde sans rien écrire : on affiche sa version
  useEffect(() => {
    if (!dirty.current && page.updated !== base.current) { setTitle(page.title); setText(page.text); base.current = page.updated; }
  }, [page.updated]); // eslint-disable-line

  const save = useCallback(async (force = false) => {
    setState("saving");
    try {
      const p = await api(`/api/notebooks/${nb.id}/pages/${page.id}`, { method: "PUT", body: JSON.stringify({ title: latest.current.title, text: latest.current.text, base: force ? undefined : base.current }) });
      base.current = p.updated; dirty.current = false; setConflict(null); setState("saved"); onSaved(p);
    } catch (e) {
      if (e.status === 409 && e.data?.page) { setConflict(e.data.page); setState("conflict"); } else setState("dirty");
    }
  }, [nb.id, page.id, onSaved]);

  function touch(setter) {
    return (v) => { setter(v); dirty.current = true; setState("dirty"); clearTimeout(timer.current); timer.current = setTimeout(() => save(), 900); };
  }
  useEffect(() => () => { clearTimeout(timer.current); if (dirty.current) save(); }, []); // eslint-disable-line

  return (
    <div className="nbed" data-testid="nb-editor">
      <input className="nbed__title" value={title} onChange={(e) => touch(setTitle)(e.target.value)} disabled={!canEdit} placeholder="Titre de la page" data-testid="nb-title" />
      <div className="nbed__bar">
        <span className="nbed__meta">{page.by === me ? "Toi" : page.by} · {ago(page.updated)}</span>
        <span className={`nbed__state is-${state}`} data-testid="nb-state">{!canEdit ? "👁 Lecture seule" : state === "saved" ? "✓ Enregistré" : state === "saving" ? "Enregistrement…" : state === "conflict" ? "⚠ Conflit" : "Modifié…"}</span>
        {canEdit && <button className="btn btn--ghost" onClick={() => setPreview((v) => !v)} data-testid="nb-preview">{preview ? "✎ Écrire" : "👁 Aperçu"}</button>}
      </div>
      {conflict && (
        <div className="salon__notice" role="alert" data-testid="nb-conflict">
          <span>{conflict.by} vient de modifier cette page.</span>
          <span><button className="btn" onClick={() => { setTitle(conflict.title); setText(conflict.text); base.current = conflict.updated; dirty.current = false; setConflict(null); setState("saved"); onSaved(conflict); }}>Voir sa version</button>{" "}
            <button className="btn btn--ghost" onClick={() => save(true)}>Garder la mienne</button></span>
        </div>
      )}
      {preview
        ? <div className="nbed__preview" data-testid="nb-render">{text.trim() ? <MessageText text={text} tag="div" /> : <p className="card__hint">Page vide.</p>}</div>
        : <textarea className="nbed__text" value={text} onChange={(e) => touch(setText)(e.target.value)} placeholder="Écris ici… (Markdown : # titre, - liste, **gras**, ``` code ```)" data-testid="nb-text" />}
    </div>
  );
}

export default function NotebooksPage() {
  const auth = useAuth();
  const me = auth.user || "";
  const admin = !auth.required || auth.role === "admin";
  const [list, setList] = useState(null);
  const [nbId, setNbId] = useState(() => lsGet("eva.nb.nb"));
  const [nb, setNb] = useState(null);
  const [secId, setSecId] = useState(() => lsGet("eva.nb.sec"));
  const [pageId, setPageId] = useState(() => lsGet("eva.nb.page"));
  const [share, setShare] = useState(false);
  const [err, setErr] = useState("");
  const [renaming, setRenaming] = useState("");
  const [draft, setDraft] = useState("");

  const refreshList = useCallback(() => api("/api/notebooks").then((d) => setList(d.notebooks)).catch((e) => setErr(e.message)), []);
  const refreshNb = useCallback((id) => api(`/api/notebooks/${id}`).then(setNb).catch(() => { setNb(null); setNbId(""); }), []);
  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => { if (nbId) { lsSet("eva.nb.nb", nbId); refreshNb(nbId); } else setNb(null); }, [nbId, refreshNb]);
  // travail à plusieurs : on rafraîchit régulièrement (sans toucher à ce que tu es en train d'écrire)
  useEffect(() => { const t = setInterval(() => { if (document.visibilityState === "visible") { refreshList(); if (nbId) refreshNb(nbId); } }, 6000); return () => clearInterval(t); }, [nbId, refreshList, refreshNb]);

  const sections = nb?.tree || [];
  const sec = sections.find((s) => s.id === secId) || sections[0];
  const page = sec?.pages.find((p) => p.id === pageId) || sec?.pages[0];
  useEffect(() => { if (sec) lsSet("eva.nb.sec", sec.id); if (page) lsSet("eva.nb.page", page.id); }, [sec?.id, page?.id]); // eslint-disable-line
  const canEdit = nb && (nb.perm === "owner" || nb.perm === "edit");
  const isOwner = nb && nb.perm === "owner";

  async function act(fn) { setErr(""); try { return await fn(); } catch (e) { setErr(e.message); return null; } }
  const newNb = () => act(async () => { const n = await api("/api/notebooks", { method: "POST", body: JSON.stringify({ title: "Nouveau carnet", icon: ICONS[Math.floor(Math.random() * ICONS.length)], color: Object.keys(TONES)[Math.floor(Math.random() * 6)] }) }); await refreshList(); setNbId(n.id); setNb(n); setSecId(""); setPageId(""); setRenaming("nb"); setDraft(n.title); });
  const delNb = () => confirmer(`Supprimer le carnet « ${nb.title} » et toutes ses pages, pour tout le monde ?`).then((ok) => ok && (act(async () => { await api(`/api/notebooks/${nb.id}`, { method: "DELETE" }); setNbId(""); setNb(null); lsSet("eva.nb.nb", ""); refreshList(); })));
  const newSec = () => act(async () => { const s = await api(`/api/notebooks/${nb.id}/sections`, { method: "POST", body: JSON.stringify({ title: "" }) }); await refreshNb(nb.id); setSecId(s.id); setPageId(s.pages[0].id); });
  const newPage = () => act(async () => { const p = await api(`/api/notebooks/${nb.id}/sections/${sec.id}/pages`, { method: "POST", body: JSON.stringify({ title: "" }) }); await refreshNb(nb.id); setPageId(p.id); });
  const delPage = () => confirmer(`Supprimer la page « ${page.title} » ?`).then((ok) => ok && (act(async () => { await api(`/api/notebooks/${nb.id}/pages/${page.id}`, { method: "DELETE" }); setPageId(""); refreshNb(nb.id); })));
  const delSec = () => confirmer(`Supprimer la section « ${sec.title} » et ses pages ?`).then((ok) => ok && (act(async () => { await api(`/api/notebooks/${nb.id}/sections/${sec.id}`, { method: "DELETE" }); setSecId(""); setPageId(""); refreshNb(nb.id); })));
  async function commitRename() {
    const which = renaming; setRenaming("");
    if (!draft.trim()) return;
    if (which === "nb") await act(async () => { await api(`/api/notebooks/${nb.id}`, { method: "PUT", body: JSON.stringify({ title: draft }) }); await refreshNb(nb.id); refreshList(); });
    else if (which === "sec") await act(async () => { await api(`/api/notebooks/${nb.id}/sections/${sec.id}`, { method: "PUT", body: JSON.stringify({ title: draft }) }); refreshNb(nb.id); });
  }
  const onSaved = useCallback((p) => setNb((cur) => cur && { ...cur, tree: cur.tree.map((s) => ({ ...s, pages: s.pages.map((x) => (x.id === p.id ? { ...x, ...p } : x)) })) }), []);

  // listes : mes carnets / partagés avec moi / (administrateur) ceux de chaque personne en dossiers
  const groups = useMemo(() => {
    const l = list || [];
    const mine = l.filter((n) => n.owner.toLowerCase() === (me || "admin").toLowerCase() || (!auth.required));
    const others = l.filter((n) => !mine.includes(n));
    const out = [{ key: "mine", title: "Mes carnets", items: mine }];
    if (admin) [...new Set(others.map((n) => n.owner))].sort().forEach((o) => out.push({ key: `o-${o}`, title: `📁 ${o}`, items: others.filter((n) => n.owner === o), folder: true }));
    else if (others.length) out.push({ key: "shared", title: "Partagés avec moi", items: others });
    return out;
  }, [list, me, admin, auth.required]);

  return (
    <section className="page nbpage" data-testid="notebooks-page">
      <header className="page__header"><h1>Carnets</h1><span className="page__sub">tes notes en sections et pages, à partager avec les autres</span></header>
      <div className="page__body">
        {err && <p className="page__warn" role="alert" data-testid="nb-error">{err}</p>}
        <div className="nb">
          <aside className="nb__books card" data-testid="nb-list">
            <button className="btn btn--primary nb__new" onClick={newNb} data-testid="nb-new">＋ Nouveau carnet</button>
            {list && list.length === 0 && <p className="card__hint">Aucun carnet pour l'instant. Crée le premier : voyages, recettes, devoirs, idées…</p>}
            {groups.filter((g) => g.items.length).map((g) => (
              <div key={g.key} className={`nb__group ${g.folder ? "is-folder" : ""}`}>
                <span className="card__label">{g.title}</span>
                {g.items.map((n) => (
                  <button key={n.id} className={`nb__book ${n.id === nbId ? "is-on" : ""}`} onClick={() => { setNbId(n.id); setSecId(""); setPageId(""); setShare(false); }} data-testid={`nb-book-${n.id}`}>
                    <span className="nb__icon" style={{ background: TONES[n.color] || TONES.jaune }} aria-hidden="true">{n.icon}</span>
                    <span className="nb__bookname"><b>{n.title}</b><small>{n.pages} page{n.pages > 1 ? "s" : ""}{n.owner.toLowerCase() !== (me || "admin").toLowerCase() && auth.required ? ` · de ${n.owner}` : ""}{n.shared && n.perm === "owner" ? " · 🔗 partagé" : ""}{n.perm === "read" ? " · 👁" : ""}</small></span>
                  </button>
                ))}
              </div>
            ))}
          </aside>

          {!nb ? (
            <div className="nb__empty card"><span style={{ fontSize: "2.4rem" }} aria-hidden="true">📓</span><p className="card__hint">Choisis un carnet à gauche, ou crée-en un.</p></div>
          ) : (
            <>
              <div className="nb__tree card" data-testid="nb-tree">
                <div className="nb__nbhead">
                  <span className="nb__icon" style={{ background: TONES[nb.color] || TONES.jaune }} aria-hidden="true">{nb.icon}</span>
                  {renaming === "nb" ? <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commitRename} onKeyDown={(e) => e.key === "Enter" && commitRename()} data-testid="nb-rename" />
                    : <b onDoubleClick={() => isOwner && (setRenaming("nb"), setDraft(nb.title))} title={isOwner ? "Double-clic pour renommer" : ""}>{nb.title}</b>}
                </div>
                <div className="nb__actions">
                  {isOwner && <button className="btn" onClick={() => setShare((v) => !v)} data-testid="nb-share-btn">🔗 Partager</button>}
                  {isOwner && <button className="btn btn--ghost" onClick={delNb} data-testid="nb-delete">Supprimer</button>}
                </div>
                {nb.perm !== "owner" && <p className="card__hint">Carnet de {nb.owner} · {nb.perm === "edit" ? "tu peux le modifier" : "lecture seule"}.</p>}
                <span className="card__label">Sections</span>
                <div className="nb__secs">
                  {sections.map((s, i) => (
                    <button key={s.id} className={`nb__sec ${s.id === sec?.id ? "is-on" : ""}`} style={{ "--tone": Object.values(TONES)[i % 6] }} onClick={() => { setSecId(s.id); setPageId(""); }}
                      onDoubleClick={() => canEdit && (setRenaming("sec"), setDraft(s.title))} data-testid={`nb-sec-${i}`}>
                      {renaming === "sec" && s.id === sec?.id ? <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commitRename} onKeyDown={(e) => e.key === "Enter" && commitRename()} onClick={(e) => e.stopPropagation()} /> : s.title}
                    </button>
                  ))}
                  {canEdit && <button className="nb__sec nb__sec--add" onClick={newSec} data-testid="nb-add-section" aria-label="Ajouter une section">＋</button>}
                </div>
                <span className="card__label">Pages</span>
                <div className="nb__pages" data-testid="nb-pages">
                  {sec?.pages.map((p) => (
                    <button key={p.id} className={`nb__page ${p.id === page?.id ? "is-on" : ""}`} onClick={() => setPageId(p.id)} data-testid={`nb-page-${p.id}`}>
                      <b>{p.title}</b><small>{p.by === me ? "toi" : p.by} · {ago(p.updated)}</small>
                    </button>
                  ))}
                  {canEdit && <button className="btn btn--ghost" onClick={newPage} data-testid="nb-add-page">＋ Page</button>}
                </div>
                {canEdit && sec && <div className="nb__actions"><button className="btn btn--ghost" onClick={delSec} disabled={sections.length < 2}>Supprimer la section</button><button className="btn btn--ghost" onClick={delPage} data-testid="nb-del-page">Supprimer la page</button></div>}
              </div>
              <div className="nb__main card">
                {share && isOwner && <SharePanel nb={nb} onClose={() => setShare(false)} onSaved={(s) => { setNb({ ...nb, shares: s, shared: s.length > 0 }); refreshList(); }} />}
                {page ? <Editor key={page.id} nb={nb} page={page} canEdit={canEdit} me={me} onSaved={onSaved} /> : <p className="card__hint">Cette section n'a pas de page.</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
