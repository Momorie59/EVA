const ICONS = {
  home: <><circle cx="12" cy="12" r="3.2" /><circle cx="12" cy="12" r="8.5" /></>,
  chat: <path d="M4 5h16v11H9l-5 4V5Z" />,
  overview: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  projects: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  memory: <><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
  agents: <><rect x="5" y="8" width="14" height="11" rx="2" /><path d="M12 4v4M9 13h.01M15 13h.01M9 16h6" /></>,
  skills: <path d="M12 3l2.5 5.5L20 9.3l-4 4 1 5.7-5-2.8L7 19l1-5.7-4-4 5.5-.8L12 3Z" />,
  sources: <path d="M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7" />,
  traces: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  learning: <path d="M4 19V9l8-5 8 5v10M9 19v-6h6v6" />,
  evolution: <path d="M12 3v6M12 15v6M5 8l4 4-4 4M19 8l-4 4 4 4" />,
  maison: <path d="M4 11l8-7 8 7v9H4zM10 20v-6h4v6" />,
  salon: <><circle cx="9" cy="9" r="3" /><circle cx="17" cy="10" r="2.4" /><path d="M3 19c0-3.3 2.7-5 6-5s6 1.7 6 5M15 14.4c3 0 6 1.2 6 4.6" /></>,
  carnets: <path d="M6 3h11a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6zM6 3v18M10 8h5M10 12h5" />,
  images: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M21 16l-5-5-8 9" /></>,
  lists: <path d="M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2" />,
  wiki: <><path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M8 7h6M8 11h6" /></>,
  contenus: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m10 9 5 3-5 3z" /></>,
  finances: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M7 15h4" /></>,
  inventaire: <><path d="M3 8l9-5 9 5v10l-9 5-9-5z" /><path d="M3 8l9 5 9-5M12 13v10" /></>,
  recettes: <><path d="M6 13h12l-1 7H7z" /><path d="M8 13c0-3 1-5 4-5s4 2 4 5" /><path d="M12 8V4M9 5l1 2M15 5l-1 2" /></>,
  papiers: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M10 12h5M10 16h5" /><path d="M4 6v15h11" /></>,
  logs: <path d="M5 4h14v16H5zM9 9h6M9 13h6M9 17h3" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></>,
};

export const NAV_ITEMS = [
  { id: "home", label: "EVA" },
  { id: "chat", label: "Conversation" },
  { id: "overview", label: "Tableau de bord" },
  { id: "agents", label: "Agents" },
  { id: "skills", label: "Skills" },
  { id: "sources", label: "Sources" },
  { id: "traces", label: "Traces" },
  { id: "learning", label: "Apprentissage" },
  { id: "evolution", label: "Évolution" },
  { id: "projects", label: "Projets" },
  { id: "maison", label: "Maison" },
  { id: "salon", label: "Salon" },
  { id: "carnets", label: "Carnets" },
  { id: "images", label: "Images" },
  { id: "lists", label: "Listes" },
  { id: "papiers", label: "Papiers" },
  { id: "wiki", label: "Wiki" },
  { id: "recettes", label: "Recettes" },
  { id: "inventaire", label: "Inventaire" },
  { id: "finances", label: "Finances" },
  { id: "contenus", label: "Contenus" },
  { id: "memory", label: "Mémoire" },
  { id: "logs", label: "Journal" },
  { id: "settings", label: "Paramètres" },
];

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "./AuthGate";
import { api } from "../api";
import { useModules } from "../hooks/useModules";
import { confirmer, avertir } from "../confirmer";

// Le menu est rangé par usage : l'essentiel en haut, le suivi technique replié.
export const NAV_GROUPS = [
  { key: "main", ids: ["home", "chat", "overview"] },
  { key: "daily", title: "Au quotidien", ids: ["salon", "carnets", "maison", "images", "lists", "recettes", "inventaire", "wiki", "finances", "contenus", "papiers", "projects", "memory"] },
  { key: "work", title: "Atelier d'EVA", collapsible: true, ids: ["agents", "skills", "sources"] },
  { key: "adv", title: "Suivi & avancé", collapsible: true, ids: ["traces", "learning", "evolution", "logs"] },
  { key: "cfg", ids: ["settings"] },
];

function timeAgo(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h`;
  return `${Math.floor(diff / 86400)} j`;
}


// Corbeille des conversations : récupérer ou effacer pour de bon (sinon effacées toutes seules au bout de 30 jours).
function CorbeilleConvs({ onFermer, onRestaure }) {
  const [liste, setListe] = useState(null);
  const charger = useCallback(() => api("/api/sessions/corbeille").then((d) => setListe(d.conversations || [])).catch(() => setListe([])), []);
  useEffect(() => { charger(); }, [charger]);
  const restaurer = async (ids) => { await api("/api/sessions/corbeille/restaurer", { method: "POST", body: JSON.stringify({ ids }) }); charger(); onRestaure(); };
  const effacer = async (body, quoi) => {
    if (!(await confirmer(`Effacer ${quoi} pour de bon ? Impossible de revenir en arrière.`))) return;
    await api("/api/sessions/corbeille/vider", { method: "POST", body: JSON.stringify(body) }); charger();
  };
  const jours = (iso) => Math.max(0, Math.ceil((new Date(iso) - Date.now()) / 86400000));
  if (!liste) return <p className="convs__empty">Chargement…</p>;
  return (
    <div className="convs__corbeille" data-testid="corbeille">
      <div className="convs__selbar">
        <span>🗑 Corbeille · {liste.length}</span>
        <div className="convs__selactions">
          {liste.length > 0 && <button className="convs__act" onClick={() => restaurer(liste.map((x) => x.id))}>Tout récupérer</button>}
          {liste.length > 0 && <button className="convs__act convs__act--danger" onClick={() => effacer({ tout: true }, "toute la corbeille")}>Vider</button>}
          <button className="convs__act" onClick={onFermer}>Fermer</button>
        </div>
      </div>
      <ul className="convs__list">
        {liste.map((x) => (
          <li key={x.id} className="convs__item convs__item--corbeille">
            <span className="convs__title" title={`${x.message_count} messages${x.owner ? ` · ${x.owner}` : ""}`}>{x.title}</span>
            <span className="convs__time">{jours(x.efface_le)} j</span>
            <button className="convs__act" onClick={() => restaurer([x.id])} title="Récupérer" data-testid={`restaurer-${x.id}`}>↩</button>
            <button className="convs__del" onClick={() => effacer({ ids: [x.id] }, `« ${x.title} »`)} title="Effacer pour de bon">×</button>
          </li>
        ))}
        {liste.length === 0 && <li className="convs__empty">La corbeille est vide. Une conversation supprimée y reste 30 jours.</li>}
      </ul>
    </div>
  );
}

export default function Sidebar({
  view,
  onSelect,
  connected,
  transport,
  offlineReason,
  pendingConfirms,
  badges = {},
  conversations,
  mobileOpen,
}) {
  const auth = useAuth();
  const mods = useModules();
  // Module facultatif coupé, ou pas permis à cette personne : pas dans le menu.
  const cache = (id) => ["wiki", "recettes", "inventaire", "finances", "contenus"].includes(id)
    && (!mods[id] || (auth.required && auth.role !== "admin" && Array.isArray(auth.features) && !auth.features.includes(id)));
  const [query, setQuery] = useState("");
  const [convOpen, setConvOpen] = useState(false);
  // Groupes repliables (Atelier, Suivi & avancé) : chacun garde son état ouvert/fermé dans le navigateur.
  const [grpOpen, setGrpOpen] = useState(() => {
    const o = {};
    for (const g of NAV_GROUPS) if (g.collapsible) { try { o[g.key] = localStorage.getItem(`eva.nav.${g.key}`) === "1"; } catch { o[g.key] = false; } }
    return o;
  });
  const toggleGroup = (key) => setGrpOpen((o) => { const n = !o[key]; try { localStorage.setItem(`eva.nav.${key}`, n ? "1" : "0"); } catch { /* ignoré */ } return { ...o, [key]: n }; });
  const [renaming, setRenaming] = useState(null);
  const [draftTitle, setDraftTitle] = useState("");
  const c = conversations;
  // Menu plus haut que sa zone (petit écran) : un fondu et une flèche indiquent qu'il reste des entrées en dessous.
  const menuRef = useRef(null);
  const [menuMore, setMenuMore] = useState(false);
  const checkMore = useCallback(() => {
    const el = menuRef.current;
    if (el) setMenuMore(el.scrollHeight - el.scrollTop - el.clientHeight > 4);
  }, []);
  useEffect(() => {
    checkMore();
    window.addEventListener("resize", checkMore);
    return () => window.removeEventListener("resize", checkMore);
  }, [checkMore, grpOpen, view]);
  const brute = c && query.trim() && c.results ? c.results : c?.sessions || [];
  // Projets : filtre de la liste, étiquette sur chaque conversation, rattachement en lot.
  const [projets, setProjets] = useState([]);
  const [filtreProjet, setFiltreProjet] = useState(() => { try { return sessionStorage.getItem("eva.convs.projet") || ""; } catch { return ""; } });
  const choisirFiltre = (v) => { setFiltreProjet(v); try { sessionStorage.setItem("eva.convs.projet", v); } catch { /* ignoré */ } };
  const chargerProjets = useCallback(() => api("/api/projects").then((d) => setProjets(d.projects || [])).catch(() => setProjets([])), []);
  useEffect(() => { chargerProjets(); }, [chargerProjets]);
  const nomProjet = (slug) => (projets.find((p) => p.slug === slug) || {}).name || slug;
  const list = filtreProjet === "" ? brute : brute.filter((x) => (filtreProjet === "_aucun" ? !x.project : x.project === filtreProjet));
  // Mode sélection : cocher plusieurs conversations pour les supprimer ou les rattacher à un projet.
  const [selMode, setSelMode] = useState(false);
  const [corbeille, setCorbeille] = useState(false);
  const [sel, setSel] = useState(() => new Set());
  const [occupe, setOccupe] = useState(false);
  const basculer = (id) => setSel((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const quitterSel = () => { setSelMode(false); setSel(new Set()); };
  const toutCoche = list.length > 0 && list.every((x) => sel.has(x.id));
  async function supprimerSel() {
    const ids = [...sel];
    if (!ids.length) return;
    const autres = list.filter((x) => sel.has(x.id) && x.owner).length;
    const msg = `Mettre ${ids.length} conversation${ids.length > 1 ? "s" : ""} à la corbeille ? (récupérable 30 jours)` + (autres ? `\n\nDont ${autres} d'autres personnes.` : "");
    if (!(await confirmer(msg))) return;
    setOccupe(true);
    try { await c.onDeleteMany({ ids }, ids); quitterSel(); } finally { setOccupe(false); }
  }
  async function rattacherSel(slug) {
    const ids = [...sel];
    if (!ids.length) return;
    setOccupe(true);
    try { await c.attach(ids, slug === "_aucun" ? "" : slug); quitterSel(); } catch (e) { avertir(e.message); } finally { setOccupe(false); }
  }
  // Dossiers ouverts/fermés (administrateur) : gardés pour la session du navigateur, même si le menu se recharge.
  const [openFolders, setOpenFoldersRaw] = useState(() => { try { return JSON.parse(sessionStorage.getItem("eva.convs.folders") || "{}"); } catch { return {}; } });
  const setOpenFolders = (fn) => setOpenFoldersRaw((o) => { const n = fn(o); try { sessionStorage.setItem("eva.convs.folders", JSON.stringify(n)); } catch { /* ignoré */ } return n; });
  // administrateur : les conversations de chaque personne sont rangées dans son dossier (les utilisateurs ne voient que les leurs, sans dossiers)
  const adminView = auth.required && auth.role === "admin";
  const owners = [...new Set(list.map((x) => x.owner || ""))];
  const groups = adminView && owners.some((o) => o) ? [...owners].sort((x, y) => (x === "" ? -1 : y === "" ? 1 : x.localeCompare(y))).map((o) => ({
    owner: o, mine: o === "", label: o === "" ? `${auth.user || "admin"} (toi)` : o, items: list.filter((x) => (x.owner || "") === o),
  })) : null;

  function onSearch(value) {
    setQuery(value);
    c?.search(value);
  }

  async function commitRename(id) {
    if (draftTitle.trim()) await c.rename(id, draftTitle);
    setRenaming(null);
  }

  const renderItem = (s) => selMode ? (
    <li key={s.id} className={`convs__item ${sel.has(s.id) ? "is-selected" : ""}`}>
      <label className="convs__check">
        <input type="checkbox" checked={sel.has(s.id)} onChange={() => basculer(s.id)} aria-label={`Sélectionner ${s.title}`} />
        <span className="convs__title">{s.title}</span>
        {s.project && filtreProjet === "" && <span className="convs__tag" title={`Projet : ${nomProjet(s.project)}`} aria-label={`Projet ${nomProjet(s.project)}`}>📁</span>}
      </label>
    </li>
  ) : (
    <li key={s.id} className={`convs__item ${s.id === c.activeId ? "is-active" : ""}`}>
                  {renaming === s.id ? (
                    <input
                      className="convs__rename"
                      autoFocus
                      value={draftTitle}
                      onChange={(e) => setDraftTitle(e.target.value)}
                      onBlur={() => commitRename(s.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename(s.id);
                        if (e.key === "Escape") setRenaming(null);
                      }}
                    />
                  ) : (
                    <button
                      className="convs__open"
                      onClick={() => { c.onOpen(s.id); setConvOpen(false); }}
                      onDoubleClick={() => {
                        setRenaming(s.id);
                        setDraftTitle(s.title);
                      }}
                      title={`${s.title}${s.updated_at ? ` · ${timeAgo(s.updated_at)}` : ""}${s.snippet || s.preview ? `\n${s.snippet || s.preview}` : ""}`}
                    >
                      <span className="convs__title">{s.title}</span>
                      {s.project && filtreProjet === "" && <span className="convs__tag" title={`Projet : ${nomProjet(s.project)}`} aria-label={`Projet ${nomProjet(s.project)}`}>📁</span>}
                      <span className="convs__time">{s.updated_at ? timeAgo(s.updated_at) : ""}</span>
                    </button>
                  )}
                  <button
                    className="convs__del"
                    onClick={() => confirmer(`Mettre « ${s.title} » à la corbeille ? Tu pourras la récupérer pendant 30 jours.`).then((ok) => ok && (c.onDelete(s.id)))}
                    aria-label={`Supprimer la conversation ${s.title}`}
                    title="Supprimer"
                  >
                    ×
                  </button>
                </li>
  );

  // Menu « icônes » ou « en haut » : l'historique s'ouvre en fenêtre au-dessus de la page (rendue hors de la barre,
  // sinon l'effet de verre de la barre l'enfermait et la coupait : la fenêtre restait invisible ou hors de l'écran).
  const navMode = typeof document !== "undefined" ? document.documentElement.dataset.nav : "left";
  const popup = navMode === "rail" || navMode === "top";
  const convsPanel = c ? (
        <div className={`convs ${convOpen ? "is-pop-open" : ""}`}>
          <div className="convs__head">
            <span>Conversations</span>
            <span className="convs__headbtns">
              <button className={`convs__new ${selMode ? "is-on" : ""}`} onClick={() => (selMode ? quitterSel() : setSelMode(true))} title="Sélectionner plusieurs conversations (supprimer, rattacher à un projet)" aria-label="Sélectionner" aria-pressed={selMode} data-testid="convs-select">☑</button>
              <button className={`convs__new ${corbeille ? "is-on" : ""}`} onClick={() => setCorbeille((v) => !v)} title="Corbeille (conversations supprimées, 30 jours)" aria-label="Corbeille" aria-pressed={corbeille} data-testid="convs-corbeille">🗑</button>
              <button className="convs__new" onClick={c.onNew} title="Nouvelle conversation" aria-label="Nouvelle conversation">+</button>
            </span>
          </div>
          {corbeille ? <CorbeilleConvs onFermer={() => setCorbeille(false)} onRestaure={() => c.refresh()} /> : <>
          {selMode && (
            <div className="convs__selbar" data-testid="convs-selbar">
              <label className="convs__check convs__check--all">
                <input type="checkbox" checked={toutCoche} onChange={() => setSel(toutCoche ? new Set() : new Set(list.map((x) => x.id)))} data-testid="convs-all" />
                <span>{sel.size ? `${sel.size} sélectionnée${sel.size > 1 ? "s" : ""}` : "Tout sélectionner"}</span>
              </label>
              <div className="convs__selactions">
                <button className="convs__act convs__act--danger" onClick={supprimerSel} disabled={!sel.size || occupe} data-testid="convs-delete-sel">Supprimer</button>
                {projets.length > 0 && (
                  <select className="convs__act" value="" onChange={(e) => e.target.value && rattacherSel(e.target.value)} disabled={!sel.size || occupe} aria-label="Rattacher à un projet" data-testid="convs-attach">
                    <option value="">Projet…</option>
                    {projets.map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
                    <option value="_aucun">Aucun projet</option>
                  </select>
                )}
                <button className="convs__act" onClick={quitterSel}>Fermer</button>
              </div>
            </div>
          )}
          <div className="convs__tools">
          <input
            className="convs__search"
            value={query}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Rechercher…"
            aria-label="Rechercher dans les conversations"
          />
          {projets.length > 0 && (
            <select className="convs__filter" value={filtreProjet} onChange={(e) => choisirFiltre(e.target.value)} aria-label="Filtrer par projet" data-testid="convs-filter">
              <option value="">📁 Tous</option>
              {projets.map((p) => <option key={p.slug} value={p.slug}>📁 {p.name}</option>)}
              <option value="_aucun">Sans projet</option>
            </select>
          )}
          </div>
          <ul className="convs__list">
            {groups
              ? groups.map((g) => {
                  // Le choix de la personne (clic) l'emporte ; sinon ouvert si c'est son dossier ou s'il contient la conversation en cours.
                  const open = query.trim() ? true : (openFolders[g.owner] ?? (g.mine || g.items.some((x) => x.id === c.activeId)));
                  return (
                    <li key={`folder-${g.owner}`} className="convs__folder" data-testid={`folder-${g.owner || "me"}`}>
                      <button className="convs__foldhead" onClick={() => setOpenFolders((o) => ({ ...o, [g.owner]: !open }))} aria-expanded={open}>
                        <span className="convs__chev" aria-hidden="true">{open ? "▾" : "▸"}</span>
                        <span aria-hidden="true">{open ? "📂" : "📁"}</span>
                        <span className="convs__foldname">{g.label}</span>
                        <span className="convs__count">{g.items.length}</span>
                      </button>
                      {open && <ul className="convs__sub">{g.items.map((s) => renderItem(s))}</ul>}
                    </li>
                  );
                })
              : list.map((s) => renderItem(s))}
            {list.length === 0 && <li className="convs__empty">{query ? "Aucun résultat" : "Aucune conversation"}</li>}
          </ul>
          </>}
        </div>
  ) : null;

  return (
    <nav className={`sidebar ${mobileOpen ? "is-mobile-open" : ""}`} aria-label="Navigation">
      <div className="sidebar__brand">
        <img src="/eva-logo.svg" alt="" className="sidebar__logo" />
        <span className="sidebar__name">EVA</span>
        <span className={`sidebar__dot ${connected ? "is-connected" : ""}`} title={connected ? "EVA CORE connecté" : `EVA CORE déconnecté — ${offlineReason || ""}`} />
      </div>
      <ul className={`sidebar__list ${menuMore ? "has-more" : ""}`} ref={menuRef} onScroll={checkMore}>
        {NAV_GROUPS.map((g) => {
          const isOpen = !g.collapsible || grpOpen[g.key] || g.ids.includes(view);
          return (
            <li key={g.key} className="sidebar__group" data-testid={`nav-group-${g.key}`}>
              {g.title && (g.collapsible
                ? <button className="sidebar__heading sidebar__heading--btn" onClick={() => toggleGroup(g.key)} aria-expanded={isOpen} data-testid={g.key === "adv" ? "nav-adv-toggle" : `nav-toggle-${g.key}`}><span>{g.title}</span><span aria-hidden="true">{isOpen ? "−" : "+"}</span></button>
                : <div className="sidebar__heading">{g.title}</div>)}
              {isOpen && (
                <ul className="sidebar__sub">
                  {g.ids.filter((id) => !cache(id)).map((id) => {
                    const item = NAV_ITEMS.find((n) => n.id === id);
                    return (
                      <li key={id}>
                        <button className={`sidebar__item ${view === id ? "is-active" : ""}`} onClick={() => onSelect(id)}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">{ICONS[id]}</svg>
                          <span>{item.label}</span>
                          {id === "chat" && pendingConfirms > 0 && <span className="sidebar__badge">{pendingConfirms}</span>}
                          {badges[id] > 0 && <span className="sidebar__badge" data-testid={`badge-${id}`}>{badges[id]}</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
        <li className="sidebar__convs-li">
          <button className={`sidebar__item sidebar__convs-toggle ${convOpen ? "is-active" : ""}`} onClick={() => setConvOpen((v) => !v)} aria-expanded={convOpen} data-testid="convs-toggle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
            <span>Historique</span>
          </button>
        </li>
      </ul>
      {c && (popup && convOpen ? createPortal(convsPanel, document.body) : convsPanel)}
      {!connected && offlineReason && <p className="sidebar__foot" data-testid="offline-reason" style={{ whiteSpace: "normal" }}>⚠ {offlineReason}</p>}
      <p className="sidebar__foot">{connected ? (transport === "http" ? <span title="Ce réseau bloque les WebSocket : EVA passe par du HTTP ordinaire (un peu plus lent, tout marche)">En ligne (mode compatible)</span> : "En ligne") : "Hors ligne"} · local-first · <a href="https://github.com/Momorie59/EVA" target="_blank" rel="noreferrer" title="EVA est un logiciel libre (AGPL-3.0) : son code source est ici">code source</a></p>
      {auth.required && <button className="sidebar__logout" onClick={auth.logout} data-testid="logout">Se déconnecter{auth.user ? ` (${auth.user})` : ""}</button>}
    </nav>
  );
}
