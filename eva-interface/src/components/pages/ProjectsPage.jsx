import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { CORE_URL, authHeaders } from "../../urls";

const kb = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} Mo` : n >= 1024 ? `${Math.round(n / 1024)} Ko` : `${n} o`);
const when = (t) => new Date(t * 1000).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const P = (slug, tail = "") => `/api/projects/${encodeURIComponent(slug)}${tail}`;

// ---------------------------------------------------------------- partage réseau
function randomPassword() {
  const c = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const a = new Uint32Array(12); crypto.getRandomValues(a);
  return [...a].map((n) => c[n % c.length]).join("");
}

function ShareCard() {
  const [st, setSt] = useState(null);
  const [pw, setPw] = useState("");
  const [port, setPort] = useState(445);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const host = window.location.hostname;
  const load = useCallback(() => api("/api/projects/share").then((d) => { setSt(d); setPw((p) => p || d.password || randomPassword()); setPort(d.port); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function apply(enabled) {
    setBusy(true); setError("");
    try { const d = await api("/api/projects/share", { method: "PUT", body: JSON.stringify({ enabled, password: pw, port: +port }) }); setSt(d); }
    catch (e) { setError(e.message); load(); }
    setBusy(false);
  }
  if (!st) return null;
  const on = st.enabled && st.running;
  return (
    <div className="card pj-share-card" data-testid="share-card">
      <div className="pj-row">
        <strong>Partage réseau</strong>
        <span className={`pj-pill${on ? " is-on" : ""}`} data-testid="share-state">{on ? "actif" : st.enabled ? "démarrage…" : "éteint"}</span>
        <span className="pj-sbx__info">Ouvre tes projets comme un dossier Windows, Mac ou Linux : ce que tu enregistres arrive chez EVA, et inversement.</span>
      </div>
      {st.error && !on && <p className="page__warn">{st.error}</p>}
      <div className="pj-row">
        <label className="pj-check">Utilisateur <b>{st.user}</b></label>
        <label className="pj-check">Mot de passe
          <input type={show ? "text" : "password"} value={pw} onChange={(e) => setPw(e.target.value)} data-testid="share-pw" autoComplete="new-password" />
        </label>
        <label className="pj-check"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Afficher</label>
        <label className="pj-check">Port <input type="number" min="1" max="65535" value={port} onChange={(e) => setPort(e.target.value)} className="pj-port" data-testid="share-port" /></label>
        {on
          ? <>
              <button className="btn" onClick={() => apply(true)} disabled={busy} data-testid="share-update">Appliquer</button>
              <button className="btn btn--ghost" onClick={() => apply(false)} disabled={busy} data-testid="share-off">Désactiver</button>
            </>
          : <button className="btn btn--primary" onClick={() => apply(true)} disabled={busy} data-testid="share-on">{busy ? "Activation…" : "Activer le partage"}</button>}
      </div>
      {busy && <p className="page__sub">Le premier démarrage télécharge le serveur de partage (une minute environ).</p>}
      {error && <p className="page__warn" role="alert" data-testid="share-error">{error}</p>}
      {on && (
        <ul className="pj-howto" data-testid="share-howto">
          <li><b>Windows</b> : Explorateur → barre d'adresse → <code>{`\\\\${host}\\${st.share}`}</code>{st.port !== 445 && <> ou <code>{`net use P: \\\\${host}\\${st.share} /user:${st.user} /TCPPORT:${st.port}`}</code></>}</li>
          <li><b>Mac / Linux</b> : <code>{`smb://${host}${st.port !== 445 ? `:${st.port}` : ""}/${st.share}`}</code></li>
          <li>Identifiants : <code>{st.user}</code> et le mot de passe ci-dessus. Seul ton réseau local y accède.</li>
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- corbeille
function TrashCard({ tick, onRestored }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [ask, setAsk] = useState("");
  const load = useCallback(() => api("/api/projects/trash").then((d) => setItems(d.items)).catch(() => {}), []);
  useEffect(() => { load(); }, [load, tick]);
  if (!items.length) return null;
  async function act(fn) { setError(""); try { await fn(); setAsk(""); load(); onRestored(); } catch (e) { setError(e.message); } }
  return (
    <div className="card pj-trash" data-testid="trash-card">
      <button className="pj-link" onClick={() => setOpen((o) => !o)} data-testid="trash-toggle">{open ? "▾" : "▸"} Corbeille ({items.length})</button>
      {open && (
        <ul className="pj-trash__list">
          {items.map((i) => (
            <li key={i.id}>
              <span><b>{i.slug}</b> · supprimé le {when(i.deleted_at)} · {i.files} fichier{i.files > 1 ? "s" : ""} · {i.days_left} j restants</span>
              <button className="btn" onClick={() => act(() => api(`/api/projects/trash/${i.id}/restore`, { method: "POST" }))} data-testid={`trash-restore-${i.slug}`}>Restaurer</button>
              {ask === i.id
                ? <button className="btn btn--danger" onClick={() => act(() => api(`/api/projects/trash/${i.id}`, { method: "DELETE" }))}>Supprimer pour de bon ?</button>
                : <button className="btn btn--ghost" onClick={() => setAsk(i.id)}>Supprimer définitivement</button>}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="page__warn" role="alert">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- partage entre personnes
function PeopleShare({ project, onChanged }) {
  const [open, setOpen] = useState(false);
  const [people, setPeople] = useState([]);
  const [err, setErr] = useState("");
  const shared = project.shared || [];
  async function toggleOpen() {
    if (!open) { try { setPeople((await api("/api/projects/people")).users || []); } catch { setPeople([]); } }
    setOpen((v) => !v);
  }
  async function save(next) {
    setErr("");
    try { await api(P(project.slug, "/shares"), { method: "PUT", body: JSON.stringify({ shared: next }) }); onChanged(); } catch (e) { setErr(e.message); }
  }
  const all = shared.includes("*");
  return (
    <div className="pj-people">
      <button className="btn btn--ghost" onClick={toggleOpen} aria-expanded={open} data-testid={`pj-share-${project.slug}`}>
        👥 {shared.length ? (all ? "Partagé avec tous" : `Partagé (${shared.length})`) : "Partager"}
      </button>
      {open && (
        <div className="pj-people__pop" data-testid={`pj-share-pop-${project.slug}`}>
          <label><input type="checkbox" checked={all} onChange={() => save(all ? [] : ["*"])} /> Tout le monde</label>
          {people.length === 0 && <small>Aucune autre personne.</small>}
          {people.map((u) => (
            <label key={u}><input type="checkbox" checked={all || shared.includes(u)} disabled={all} onChange={() => save(shared.includes(u) ? shared.filter((x) => x !== u) : [...shared, u])} data-testid={`pj-share-${project.slug}-${u}`} /> {u}</label>
          ))}
          <small>Les personnes choisies peuvent ouvrir et modifier les fichiers. Seul toi peux supprimer le projet.</small>
          {err && <p className="te-error" role="alert">{err}</p>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- liste
function ProjectList({ onOpen }) {
  const [projects, setProjects] = useState(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState("");
  const [trashTick, setTrashTick] = useState(0);
  const load = useCallback(() => api("/api/projects").then((d) => setProjects(d.projects)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);

  async function create(e) {
    e.preventDefault(); setError("");
    try { const r = await api("/api/projects", { method: "POST", body: JSON.stringify({ name, description: desc }) }); setName(""); setDesc(""); onOpen(r.slug); }
    catch (err) { setError(err.message); }
  }
  async function remove(slug) {
    setError("");
    try { await api(P(slug), { method: "DELETE" }); setConfirm(""); load(); setTrashTick((t) => t + 1); } catch (err) { setError(err.message); }
  }
  return (
    <section className="page" data-testid="projects-page">
      <header className="page__header">
        <h1>Projets</h1>
        <span className="page__sub">Tes projets et ceux d'EVA : dépose des fichiers, modifie-les, EVA travaille dans les mêmes dossiers</span>
      </header>
      <div className="page__body">
        <form className="card pj-new" onSubmit={create}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom du nouveau projet" data-testid="pj-name" maxLength={60} />
          <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (facultatif)" data-testid="pj-desc" />
          <button className="btn btn--primary" type="submit" disabled={!name.trim()} data-testid="pj-create">Créer le projet</button>
        </form>
        {error && <p className="page__warn" role="alert">{error}</p>}
        <ShareCard />
        {projects === null && <p className="page__sub">Chargement…</p>}
        {projects?.length === 0 && <p className="page__sub">Aucun projet pour l'instant. Crée-en un ci-dessus ou demande à EVA d'en créer un.</p>}
        <div className="pj-grid">
          {projects?.map((p) => (
            <div key={p.slug} className="card pj-card" data-testid={`pj-card-${p.slug}`}>
              <button className="pj-card__main" onClick={() => onOpen(p.slug)}>
                <strong>{p.name}</strong>
                <span className="pj-card__slug">{p.slug}</span>
                {p.description && <span className="pj-card__desc">{p.description}</span>}
                {p.mine === false && <span className="pj-card__desc" data-testid={`pj-owner-${p.slug}`}>👤 Partagé par {p.owner}</span>}
                <span className="pj-card__meta">{p.files} fichier{p.files > 1 ? "s" : ""} · {kb(p.size)} · {when(p.mtime)}{p.deps ? " · paquets installés" : ""}</span>
              </button>
              {p.mine !== false && <PeopleShare project={p} onChanged={load} />}
              {p.mine === false ? null : confirm === p.slug ? (
                <div className="pj-confirm">
                  <span>Mettre « {p.slug} » à la corbeille ? (récupérable 30 jours ; sa base de test est supprimée)</span>
                  <button className="btn btn--danger" onClick={() => remove(p.slug)} data-testid={`pj-confirm-${p.slug}`}>Oui, supprimer</button>
                  <button className="btn" onClick={() => setConfirm("")}>Annuler</button>
                </div>
              ) : (
                <button className="btn btn--ghost" onClick={() => setConfirm(p.slug)} data-testid={`pj-del-${p.slug}`}>Supprimer</button>
              )}
            </div>
          ))}
        </div>
        <TrashCard tick={trashTick} onRestored={load} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- arbre
function useTree(slug) {
  const [tree, setTree] = useState({ rev: "", items: [] });
  const rev = useRef("");
  const refresh = useCallback(async () => {
    try {
      const t = await api(P(slug, `/tree?rev=${rev.current}`));
      if (t.changed) { rev.current = t.rev; setTree({ rev: t.rev, items: t.items }); return true; }
    } catch { /* projet supprimé ou serveur injoignable : on réessaie au prochain tour */ }
    return false;
  }, [slug]);
  return [tree, refresh];
}

function TreeView({ items, collapsed, setCollapsed, current, onOpen, target, setTarget, onDelete, delAsk, setDelAsk }) {
  const visible = items.filter((it) => {
    const parts = it.path.split("/");
    return !parts.slice(0, -1).some((_, i) => collapsed.has(parts.slice(0, i + 1).join("/")));
  });
  return (
    <ul className="pj-tree" data-testid="pj-tree">
      {visible.map((it) => {
        const depth = it.path.split("/").length - 1;
        const base = it.path.split("/").pop();
        return (
          <li key={it.path} className={`pj-tree__row${current === it.path ? " is-on" : ""}${target === it.path ? " is-target" : ""}`} style={{ paddingLeft: 8 + depth * 14 }}>
            <button className="pj-tree__name" data-testid={`pj-item-${it.path}`}
              onClick={() => {
                if (it.dir) { setTarget(it.path); setCollapsed((c) => { const n = new Set(c); n.has(it.path) ? n.delete(it.path) : n.add(it.path); return n; }); }
                else onOpen(it.path);
              }}>
              {it.dir ? (collapsed.has(it.path) ? "▸ 📁 " : "▾ 📂 ") : "📄 "}{base}
              {!it.dir && <small> {kb(it.size)}</small>}
            </button>
            {delAsk === it.path
              ? <button className="btn btn--danger pj-tree__x" onClick={() => onDelete(it)} data-testid="pj-del-confirm">Sûr ?</button>
              : <button className="pj-tree__x" title="Supprimer" onClick={() => setDelAsk(it.path)}>✕</button>}
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------- historique
function DiffView({ text }) {
  return (
    <pre className="pj-diff" data-testid="hist-diff">
      {text.split("\n").map((l, i) => <span key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "d-add" : l.startsWith("-") && !l.startsWith("---") ? "d-del" : l.startsWith("@@") ? "d-hunk" : ""}>{l}{"\n"}</span>)}
    </pre>
  );
}

function HistoryTab({ slug, rev, onChanged }) {
  const [items, setItems] = useState([]);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [ask, setAsk] = useState("");
  const load = useCallback(() => api(P(slug, "/history")).then((d) => setItems(d.items)).catch((e) => setError(e.message)), [slug]);
  useEffect(() => { load(); }, [load, rev]);
  async function open(sha) {
    setSel(sha); setDetail(null);
    try { setDetail(await api(P(slug, `/history/${sha}`))); } catch (e) { setError(e.message); }
  }
  async function act(fn, done) {
    setError(""); setNote("");
    try { await fn(); setNote(done); setAsk(""); setSel(null); setDetail(null); await load(); onChanged(); } catch (e) { setError(e.message); }
  }
  const hasEva = items.some((i) => i.author === "EVA");
  return (
    <div data-testid="hist-tab">
      <div className="pj-row">
        <input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Nom de la version (facultatif)" data-testid="hist-msg" />
        <button className="btn" onClick={() => act(async () => { const r = await api(P(slug, "/history/snapshot"), { method: "POST", body: JSON.stringify({ message: msg || "Version enregistrée" }) }); if (r.unchanged) throw new Error("Rien n'a changé depuis la dernière version."); setMsg(""); }, "Version enregistrée.")} data-testid="hist-save">Enregistrer une version</button>
        <button className="btn btn--primary" disabled={!hasEva} onClick={() => act(() => api(P(slug, "/history/undo-eva"), { method: "POST" }), "La dernière modification d'EVA est annulée (elle reste dans l'historique).")} data-testid="hist-undo">Annuler la dernière modification d'EVA</button>
      </div>
      {error && <p className="page__warn" role="alert" data-testid="hist-error">{error}</p>}
      {note && <p className="page__sub" data-testid="hist-note">{note}</p>}
      {items.length === 0 && <p className="page__sub">Pas encore de version : elles sont créées à chaque enregistrement et avant/après chaque intervention d'EVA.</p>}
      <ul className="pj-hist">
        {items.map((i) => (
          <li key={i.sha} className={sel === i.sha ? "is-on" : ""}>
            <button className="pj-hist__row" onClick={() => open(i.sha)} data-testid={`hist-item-${i.short}`}>
              <span className={`pj-who${i.author === "EVA" ? " is-eva" : ""}`}>{i.author}</span>
              <span className="pj-hist__msg">{i.message}</span>
              <small>{when(i.time)}</small>
            </button>
          </li>
        ))}
      </ul>
      {detail && (
        <div className="pj-hist__detail" data-testid="hist-detail">
          <div className="pj-row">
            <strong>{detail.files.length} fichier{detail.files.length > 1 ? "s" : ""} : </strong>
            <span className="pj-sbx__info">{detail.files.map((f) => `${f.status} ${f.path}`).join(" · ")}</span>
          </div>
          <DiffView text={detail.diff || "(aucune différence)"} />
          {ask === sel
            ? <button className="btn btn--danger" onClick={() => act(() => api(P(slug, "/history/restore"), { method: "POST", body: JSON.stringify({ sha: sel }) }), "Version restaurée (l'état d'avant est conservé dans l'historique).")} data-testid="hist-restore-ok">Oui, revenir à cette version</button>
            : <button className="btn" onClick={() => setAsk(sel)} data-testid="hist-restore">Revenir à cette version</button>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- aperçu
function PreviewTab({ slug, rev }) {
  const [info, setInfo] = useState(null);
  const [page, setPage] = useState("");
  const [auto, setAuto] = useState(true);
  const [tick, setTick] = useState(0);
  const [error, setError] = useState("");
  const open = useCallback(() => api(P(slug, "/preview"), { method: "POST" }).then((d) => { setInfo(d); setPage((p) => (d.pages.includes(p) ? p : d.pages.includes("index.html") ? "index.html" : d.pages[0] || "")); }).catch((e) => setError(e.message)), [slug]);
  useEffect(() => { open(); const t = setInterval(open, 50 * 60 * 1000); return () => clearInterval(t); }, [open]);
  useEffect(() => { if (auto) setTick((t) => t + 1); }, [rev, auto]);
  if (!info) return error ? <p className="page__warn">{error}</p> : <p className="page__sub">Ouverture de l'aperçu…</p>;
  if (!info.pages.length) return <p className="page__sub" data-testid="prev-empty">Aucune page HTML dans ce projet pour l'instant. Crée un fichier <code>index.html</code> (ou demande-le à EVA) : l'aperçu apparaîtra ici et se rafraîchira tout seul.</p>;
  const url = `${CORE_URL}${info.base}${page}`;
  return (
    <div data-testid="prev-tab">
      <div className="pj-row">
        <select value={page} onChange={(e) => setPage(e.target.value)} data-testid="prev-page">{info.pages.map((p) => <option key={p} value={p}>{p}</option>)}</select>
        <label className="pj-check"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Rafraîchir automatiquement</label>
        <button className="btn" onClick={() => setTick((t) => t + 1)}>Recharger</button>
        <a className="btn btn--ghost" href={url} target="_blank" rel="noreferrer">Ouvrir dans un onglet</a>
      </div>
      <iframe key={`${page}-${tick}`} title="Aperçu du projet" className="pj-frame" src={url} sandbox="allow-scripts allow-forms allow-popups allow-modals" data-testid="prev-frame" />
      <p className="pj-hint">Pages statiques (HTML, CSS, JavaScript). L'aperçu est isolé : il ne peut pas accéder à EVA. Le PHP n'est pas exécuté ici.</p>
    </div>
  );
}

// ---------------------------------------------------------------- bac à sable
function SandboxPanel({ slug, onFilesChanged, rev }) {
  const [tab, setTab] = useState("console");
  const [status, setStatus] = useState(null);
  const [cmd, setCmd] = useState("python -V");
  const [internet, setInternet] = useState(false);
  const [pkgs, setPkgs] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const [sql, setSql] = useState("SELECT now();");
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const loadStatus = useCallback(() => api(P(slug, "/sandbox")).then(setStatus).catch(() => {}), [slug]);
  useEffect(() => { loadStatus(); }, [loadStatus]);

  async function call(fn) {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(false); loadStatus(); onFilesChanged();
  }
  const run = () => call(async () => {
    setOut("Exécution…");
    const r = await api(P(slug, "/sandbox/run"), { method: "POST", body: JSON.stringify({ command: cmd, internet }) });
    setOut(r.error && !r.output ? `⚠ ${r.error}` : `${r.output || ""}\n— code de sortie ${r.exit_code} (réseau : ${r.network})${r.error ? `\n⚠ ${r.error}` : ""}`);
  });
  const install = () => call(async () => {
    setOut("Installation (Internet)…");
    const r = await api(P(slug, "/sandbox/install"), { method: "POST", body: JSON.stringify({ packages: pkgs.split(/[\s,]+/).filter(Boolean) }) });
    setOut(r.error && !r.output ? `⚠ ${r.error}` : `${r.output || ""}\n— code de sortie ${r.exit_code}`);
  });
  const dbAct = (tail) => call(async () => { await api(P(slug, `/sandbox/db${tail}`), { method: "POST" }); setRes(null); });
  const dbQuery = () => call(async () => setRes(await api(P(slug, "/sandbox/db/query"), { method: "POST", body: JSON.stringify({ sql }) })));

  return (
    <div className="card pj-sbx" data-testid="pj-sandbox">
      <div className="pj-sbx__tabs">
        <button className={tab === "console" ? "is-on" : ""} onClick={() => setTab("console")} data-testid="sbx-tab-console">Console de test</button>
        <button className={tab === "db" ? "is-on" : ""} onClick={() => setTab("db")} data-testid="sbx-tab-db">Base de test {status?.db ? "●" : "○"}</button>
        <button className={tab === "history" ? "is-on" : ""} onClick={() => setTab("history")} data-testid="sbx-tab-history">Historique</button>
        <button className={tab === "preview" ? "is-on" : ""} onClick={() => setTab("preview")} data-testid="sbx-tab-preview">Aperçu</button>
        <span className="pj-sbx__info">{status?.packages?.length ? `${status.packages.length} paquet(s) installé(s)` : "aucun paquet installé"}</span>
      </div>
      {tab === "history" && <HistoryTab slug={slug} rev={rev} onChanged={onFilesChanged} />}
      {tab === "preview" && <PreviewTab slug={slug} rev={rev} />}
      {tab === "console" && (
        <>
          <div className="pj-row">
            <input value={cmd} onChange={(e) => setCmd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} placeholder="python main.py   ou   python -m pytest -q" data-testid="sbx-cmd" />
            <label className="pj-check"><input type="checkbox" checked={internet} onChange={(e) => setInternet(e.target.checked)} /> Internet</label>
            <button className="btn btn--primary" onClick={run} disabled={busy || !cmd.trim()} data-testid="sbx-run">Lancer</button>
          </div>
          <div className="pj-row">
            <input value={pkgs} onChange={(e) => setPkgs(e.target.value)} placeholder="Installer des paquets pip : requests pytest" data-testid="sbx-pkgs" />
            <button className="btn" onClick={install} disabled={busy || !pkgs.trim()} data-testid="sbx-install">Installer</button>
          </div>
          {out && <pre className="pj-out" data-testid="sbx-out">{out}</pre>}
        </>
      )}
      {tab === "db" && (
        <>
          <div className="pj-row">
            <button className="btn" onClick={() => dbAct("")} disabled={busy} data-testid="sbx-db-create">{status?.db ? "Base prête" : "Créer la base de test"}</button>
            <button className="btn" onClick={() => dbAct("/reset")} disabled={busy || !status?.db} data-testid="sbx-db-reset">Tout effacer</button>
            <span className="pj-sbx__info">Dans tes scripts : variable DATABASE_URL</span>
          </div>
          <textarea className="pj-sql" value={sql} onChange={(e) => setSql(e.target.value)} rows={3} spellCheck={false} data-testid="sbx-sql" />
          <div className="pj-row"><button className="btn btn--primary" onClick={dbQuery} disabled={busy || !sql.trim()} data-testid="sbx-db-run">Exécuter le SQL</button></div>
          {res?.error && <p className="page__warn">{res.error}</p>}
          {res?.status && <p className="page__sub">{res.status}</p>}
          {res?.columns && (
            <div className="pj-table"><table data-testid="sbx-db-table"><thead><tr>{res.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{res.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v === null ? "∅" : String(v)}</td>)}</tr>)}</tbody></table>
              {res.truncated && <p className="page__sub">Résultat tronqué ({res.row_count} lignes).</p>}</div>
          )}
        </>
      )}
      {error && <p className="page__warn" role="alert">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- projet
function ProjectView({ slug, onBack, onOpenSession, onNewInProject }) {
  const [tree, refreshTree] = useTree(slug);
  const [collapsed, setCollapsed] = useState(new Set());
  const [file, setFile] = useState(null);          // { path, content, orig, mtime_ns, binary }
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState(null);
  const [target, setTarget] = useState("");
  const [delAsk, setDelAsk] = useState("");
  const [unzip, setUnzip] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  const fileState = useRef(null);
  fileState.current = file;
  const dirty = file && !file.binary && file.content !== file.orig;

  const openFile = useCallback(async (path) => {
    setError(""); setConflict(false); setNotice("");
    try { const f = await api(P(slug, `/file?path=${encodeURIComponent(path)}`)); setFile({ ...f, orig: f.content ?? "" , content: f.content ?? "" }); }
    catch (e) { setError(e.message); }
  }, [slug]);

  // Mise à jour en direct : modifications faites par EVA, par le partage réseau ou depuis un autre appareil.
  const syncOpenFile = useCallback(async () => {
    const f = fileState.current;
    if (!f || f.binary) return;
    try {
      const fresh = await api(P(slug, `/file?path=${encodeURIComponent(f.path)}`));
      if (fresh.mtime_ns === f.mtime_ns) return;
      if (f.content === f.orig) { setFile({ ...fresh, orig: fresh.content ?? "", content: fresh.content ?? "" }); setNotice("Fichier mis à jour en direct (modifié ailleurs)."); }
      else setConflict(true);
    } catch { setFile(null); setNotice("Ce fichier n'existe plus."); }
  }, [slug]);

  useEffect(() => {
    let alive = true;
    const tick = async () => { if (!alive) return; if (await refreshTree()) await syncOpenFile(); };
    tick();
    const t = setInterval(tick, 2500);
    return () => { alive = false; clearInterval(t); };
  }, [refreshTree, syncOpenFile]);

  async function save() {
    if (!file || file.binary) return;
    setError("");
    try {
      const r = await api(P(slug, "/file"), { method: "PUT", body: JSON.stringify({ path: file.path, content: file.content, base_mtime_ns: file.mtime_ns }) });
      setFile((f) => ({ ...f, orig: f.content, mtime_ns: r.mtime_ns })); setNotice("Enregistré."); setConflict(false); refreshTree();
    } catch (e) {
      if (/modifié ailleurs/.test(e.message)) setConflict(true); else setError(e.message);
    }
  }
  async function overwrite() {
    try {
      const cur = await api(P(slug, `/file?path=${encodeURIComponent(file.path)}`));
      const r = await api(P(slug, "/file"), { method: "PUT", body: JSON.stringify({ path: file.path, content: file.content, base_mtime_ns: cur.mtime_ns }) });
      setFile((f) => ({ ...f, orig: f.content, mtime_ns: r.mtime_ns })); setConflict(false); setNotice("Ta version a remplacé l'autre."); refreshTree();
    } catch (e) { setError(e.message); }
  }
  async function createEntry(kind) {
    const p = (target && !newName.includes("/") ? `${target}/` : "") + newName.trim().replace(/^\/+/, "");
    if (!newName.trim()) return;
    setError("");
    try {
      if (kind === "dir") await api(P(slug, "/mkdir"), { method: "POST", body: JSON.stringify({ path: p }) });
      else { await api(P(slug, "/file"), { method: "PUT", body: JSON.stringify({ path: p, content: "" }) }); }
      setNewName(""); await refreshTree(); if (kind === "file") openFile(p);
    } catch (e) { setError(e.message); }
  }
  async function remove(it) {
    try {
      await api(P(slug, `/file?path=${encodeURIComponent(it.path)}`), { method: "DELETE" });
      setDelAsk(""); if (file && (file.path === it.path || file.path.startsWith(`${it.path}/`))) setFile(null);
      refreshTree();
    } catch (e) { setError(e.message); }
  }
  async function rename() {
    try {
      await api(P(slug, "/move"), { method: "POST", body: JSON.stringify({ src: file.path, dst: renaming }) });
      const np = renaming; setRenaming(null); await refreshTree(); openFile(np);
    } catch (e) { setError(e.message); }
  }
  async function upload(fileList) {
    const files = [...fileList]; if (!files.length) return;
    setUploading(true); setError("");
    let done = 0;
    for (const f of files) {
      try {
        const q = `name=${encodeURIComponent(f.name)}&dir=${encodeURIComponent(target)}&extract=${unzip && f.name.toLowerCase().endsWith(".zip")}`;
        const res = await fetch(`${CORE_URL}${P(slug, `/upload?${q}`)}`, { method: "POST", headers: authHeaders(), body: f });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Erreur ${res.status}`); }
        done += 1;
      } catch (e) { setError(`${f.name} : ${e.message}`); }
    }
    setUploading(false); if (done) setNotice(`${done} fichier${done > 1 ? "s" : ""} déposé${done > 1 ? "s" : ""}.`); refreshTree();
  }
  const download = (path) => {
    fetch(`${CORE_URL}${P(slug, `/download${path ? `?path=${encodeURIComponent(path)}` : ""}`)}`, { headers: authHeaders() })
      .then((r) => r.blob()).then((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = path ? path.split("/").pop() : `${slug}.zip`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); });
  };
  const count = useMemo(() => tree.items.filter((i) => !i.dir).length, [tree]);

  return (
    <section className="page" data-testid="project-view">
      <header className="page__header">
        <button className="btn btn--ghost" onClick={onBack} data-testid="pj-back">← Projets</button>
        <h1>{slug}</h1>
        <span className="page__sub">{count} fichier{count > 1 ? "s" : ""} · mise à jour en direct</span>
        <button className="btn page__action" onClick={() => download("")} data-testid="pj-zip">Télécharger en ZIP</button>
      </header>
      <div className="page__body pj-layout">
        <aside className={`card pj-side${dragging ? " is-drag" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files); }} data-testid="pj-drop">
          <div className="pj-row">
            <button className="btn btn--primary" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="pj-upload-btn">{uploading ? "Envoi…" : "Déposer des fichiers"}</button>
            <input ref={fileRef} type="file" multiple hidden onChange={(e) => { upload(e.target.files); e.target.value = ""; }} data-testid="pj-upload" />
          </div>
          <label className="pj-check"><input type="checkbox" checked={unzip} onChange={(e) => setUnzip(e.target.checked)} /> Décompresser les .zip</label>
          <p className="pj-hint">Dépôt dans : <b>/{target}</b>{target && <button className="pj-link" onClick={() => setTarget("")}> (racine)</button>}<br />Glisse tes fichiers ici.</p>
          <div className="pj-row">
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="nouveau : src/app.py" onKeyDown={(e) => e.key === "Enter" && createEntry("file")} data-testid="pj-newname" />
          </div>
          <div className="pj-row">
            <button className="btn" onClick={() => createEntry("file")} disabled={!newName.trim()} data-testid="pj-newfile">+ Fichier</button>
            <button className="btn" onClick={() => createEntry("dir")} disabled={!newName.trim()} data-testid="pj-newdir">+ Dossier</button>
          </div>
          <TreeView items={tree.items} collapsed={collapsed} setCollapsed={setCollapsed} current={file?.path} onOpen={openFile}
            target={target} setTarget={setTarget} onDelete={remove} delAsk={delAsk} setDelAsk={setDelAsk} />
        </aside>
        <div className="pj-main">
          {error && <p className="page__warn" role="alert" data-testid="pj-error">{error}</p>}
          {notice && <p className="page__sub" data-testid="pj-notice">{notice}</p>}
          {file ? (
            <div className="card pj-editor" data-testid="pj-editor">
              <div className="pj-editor__bar">
                {renaming === null
                  ? <strong>{file.path}{dirty ? " ●" : ""}</strong>
                  : <input value={renaming} onChange={(e) => setRenaming(e.target.value)} onKeyDown={(e) => e.key === "Enter" && rename()} data-testid="pj-rename-input" />}
                <span className="pj-editor__acts">
                  {renaming === null ? <button className="btn btn--ghost" onClick={() => setRenaming(file.path)}>Renommer</button> : <button className="btn" onClick={rename}>OK</button>}
                  <button className="btn btn--ghost" onClick={() => download(file.path)}>Télécharger</button>
                  {!file.binary && <button className="btn btn--primary" onClick={save} disabled={!dirty} data-testid="pj-save">Enregistrer</button>}
                </span>
              </div>
              {conflict && (
                <div className="pj-conflict" role="alert" data-testid="pj-conflict">
                  Ce fichier a été modifié ailleurs (EVA, partage réseau…) pendant que tu le modifiais.
                  <button className="btn" onClick={() => { openFile(file.path); }} data-testid="pj-reload">Recharger la version à jour</button>
                  <button className="btn" onClick={overwrite} data-testid="pj-overwrite">Garder la mienne</button>
                </div>
              )}
              {file.binary
                ? <p className="page__sub">Fichier non modifiable ici ({file.reason}, {kb(file.size)}). Tu peux le télécharger.</p>
                : <textarea className="pj-text" value={file.content} spellCheck={false} data-testid="pj-text"
                    onChange={(e) => setFile((f) => ({ ...f, content: e.target.value }))}
                    onKeyDown={(e) => {
                      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
                      if (e.key === "Tab") { e.preventDefault(); const t = e.target, s = t.selectionStart; const v = t.value; setFile((f) => ({ ...f, content: `${v.slice(0, s)}  ${v.slice(t.selectionEnd)}` })); requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = s + 2; }); }
                    }} />}
            </div>
          ) : <div className="card pj-empty"><p className="page__sub">Choisis un fichier à gauche pour le modifier, ou dépose-en dans le projet. Les modifications d'EVA apparaissent ici toutes seules.</p></div>}
          <ProjectConvs slug={slug} onOpenSession={onOpenSession} onNewInProject={onNewInProject} />
          <SandboxPanel slug={slug} onFilesChanged={refreshTree} rev={tree.rev} />
        </div>
      </div>
    </section>
  );
}

// Conversations rattachées au projet : en reprendre une, ou en commencer une nouvelle dans ce projet.
function ProjectConvs({ slug, onOpenSession, onNewInProject }) {
  const [convs, setConvs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    let off = false;
    api("/api/sessions").then((d) => { if (!off) setConvs((d.sessions || []).filter((x) => x.project === slug)); }).catch(() => { if (!off) setConvs([]); });
    return () => { off = true; };
  }, [slug]);
  async function nouvelle() {
    setBusy(true); setErr("");
    try { await onNewInProject(slug); } catch (e) { setErr(e.message || "Impossible de créer la conversation."); } finally { setBusy(false); }
  }
  if (!onOpenSession) return null;
  return (
    <div className="card" data-testid="pj-convs">
      <div className="pj-row">
        <strong>Conversations du projet</strong>
        <button className="btn btn--primary page__action" onClick={nouvelle} disabled={busy} data-testid="pj-newconv">+ Nouvelle conversation dans ce projet</button>
      </div>
      {err && <p className="page__warn" role="alert">{err}</p>}
      {convs === null && <p className="page__sub">Chargement…</p>}
      {convs?.length === 0 && <p className="page__sub">Aucune conversation dans ce projet pour l'instant. EVA y travaillera dès qu'une conversation y est rattachée (aussi possible depuis l'en-tête d'une conversation).</p>}
      {convs?.map((c) => (
        <div className="pj-row" key={c.id}>
          <span>{c.title || "Sans titre"} <span className="page__sub">· {c.message_count || 0} message{(c.message_count || 0) > 1 ? "s" : ""}</span></span>
          <button className="btn" onClick={() => onOpenSession(c.id)} data-testid={`pj-resume-${c.id}`}>Reprendre</button>
        </div>
      ))}
    </div>
  );
}

export default function ProjectsPage({ onOpenSession, onNewInProject }) {
  const [open, setOpen] = useState(null);
  return open ? <ProjectView slug={open} onBack={() => setOpen(null)} onOpenSession={onOpenSession} onNewInProject={onNewInProject} /> : <ProjectList onOpen={setOpen} />;
}
