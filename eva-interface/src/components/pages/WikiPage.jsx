import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { CORE_URL, authHeaders } from "../../urls";
import { useAuth } from "../AuthGate";
import MessageText from "../MessageText";
import { confirmer } from "../../confirmer";

const quand = (iso) => { try { return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };

// Envoi d'une photo ou d'une vidéo : renvoie le Markdown à insérer dans la page.
export async function envoyerMedia(module, fichier) {
  const r = await fetch(`${CORE_URL}/api/medias?module=${module}&nom=${encodeURIComponent(fichier.name)}`, { method: "POST", headers: authHeaders(), body: fichier });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Erreur ${r.status}`);
  return d;
}

// Wiki : pages de la famille (partagées, historique) et pages personnelles (privées).
export default function WikiPage() {
  const auth = useAuth();
  const invite = auth.required && auth.role === "guest";
  const [espace, setEspace] = useState("famille");
  const [q, setQ] = useState("");
  const [pages, setPages] = useState([]);
  const [page, setPage] = useState(null);
  const [edit, setEdit] = useState(null);           // {titre, contenu, tags, espace, id?, base?}
  const [histo, setHisto] = useState(null);         // liste des versions, ou null
  const [apercu, setApercu] = useState(null);       // version affichée
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const zone = useRef(null);
  const fichierRef = useRef(null);

  const charger = useCallback(() => api(`/api/wiki?espace=${espace}&q=${encodeURIComponent(q)}`).then((d) => setPages(d.pages || [])).catch((e) => setErr(e.message)), [espace, q]);
  useEffect(() => { const t = setTimeout(charger, 200); return () => clearTimeout(t); }, [charger]);
  const ouvrir = useCallback(async (id) => { setErr(""); setEdit(null); setHisto(null); setApercu(null); try { setPage(await api(`/api/wiki/${id}`)); } catch (e) { setErr(e.message); } }, []);

  // [[Titre]] dans une page ou une réponse d'EVA : ouvre la page, ou propose de la créer.
  useEffect(() => {
    const f = async (e) => {
      const titre = e.detail?.titre;
      if (!titre) return;
      try { const p = await api(`/api/wiki/titre?t=${encodeURIComponent(titre)}`); setEspace(p.espace); ouvrir(p.id); }
      catch { if (!invite && (await confirmer(`La page « ${titre} » n'existe pas encore. La créer ?`))) { setPage(null); setEdit({ titre, contenu: "", tags: "", espace }); } }
    };
    window.addEventListener("eva:wiki-ouvrir", f);
    return () => window.removeEventListener("eva:wiki-ouvrir", f);
  }, [ouvrir, espace, invite]);

  const enregistrer = async () => {
    setBusy(true); setErr("");
    const corps = { titre: edit.titre, contenu: edit.contenu, tags: edit.tags.split(",").map((x) => x.trim()).filter(Boolean) };
    try {
      const p = edit.id ? await api(`/api/wiki/${edit.id}`, { method: "PUT", body: JSON.stringify({ ...corps, base: edit.base }) })
        : await api("/api/wiki", { method: "POST", body: JSON.stringify({ ...corps, espace: edit.espace }) });
      setEdit(null); setPage(p); setEspace(p.espace); charger();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const supprimer = async () => {
    if (!(await confirmer(`Supprimer la page « ${page.titre} » et tout son historique ?`))) return;
    try { await api(`/api/wiki/${page.id}`, { method: "DELETE" }); setPage(null); charger(); } catch (e) { setErr(e.message); }
  };
  const voirHisto = async () => { try { setHisto((await api(`/api/wiki/${page.id}/versions`)).versions); setApercu(null); } catch (e) { setErr(e.message); } };
  const restaurer = async (v) => {
    if (!(await confirmer(`Revenir à la version du ${quand(v.le)} ? (la version actuelle reste dans l'historique)`))) return;
    try { setPage(await api(`/api/wiki/${page.id}/versions/${v.id}/restaurer`, { method: "POST" })); setHisto(null); setApercu(null); charger(); } catch (e) { setErr(e.message); }
  };

  // Barre d'outils de l'éditeur : entoure la sélection ou insère au curseur.
  const inserer = (avant, apres = "", defaut = "") => {
    const el = zone.current; if (!el) return;
    const { selectionStart: a, selectionEnd: b, value } = el;
    const sel = value.slice(a, b) || defaut;
    const texte = value.slice(0, a) + avant + sel + apres + value.slice(b);
    setEdit((x) => ({ ...x, contenu: texte }));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = a + avant.length; el.selectionEnd = a + avant.length + sel.length; });
  };
  const envoyer = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setBusy(true); setErr("");
    try { const d = await envoyerMedia("wiki", f); inserer(`\n![${f.name.replace(/\.[^.]+$/, "")}](${d.url})\n`); } catch (er) { setErr(er.message); }
    setBusy(false);
  };

  return (
    <section className="page wiki" data-testid="wiki-page">
      <header className="page__header">
        <h1>Wiki</h1>
        <span className="page__sub">{espace === "famille" ? "Pages de la famille : tout le monde les lit et les complète, chaque version est gardée" : "Tes pages personnelles : personne d'autre ne les voit"}</span>
      </header>
      <div className="page__body wiki__body">
        <aside className="wiki__nav">
          <div className="wiki__tabs" role="tablist">
            {["famille", "perso"].map((e) => (
              <button key={e} role="tab" aria-selected={espace === e} className={espace === e ? "is-on" : ""} onClick={() => { setEspace(e); setPage(null); setEdit(null); }} data-testid={`wiki-tab-${e}`}>
                {e === "famille" ? "👪 Famille" : "🔒 Personnel"}
              </button>
            ))}
          </div>
          <input className="convs__search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher dans le wiki…" aria-label="Rechercher dans le wiki" />
          {!invite && <button className="btn btn--primary" onClick={() => { setPage(null); setEdit({ titre: "", contenu: "", tags: "", espace }); }} data-testid="wiki-new">+ Nouvelle page</button>}
          <ul className="wiki__list">
            {pages.length === 0 && <li className="card__hint">{q ? "Aucune page trouvée." : "Aucune page pour l'instant."}</li>}
            {pages.map((p) => (
              <li key={p.id}>
                <button className={page?.id === p.id ? "is-on" : ""} onClick={() => ouvrir(p.id)}>
                  <b>{p.titre}</b>
                  <small>{p.extrait || "Page vide"}</small>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <article className="wiki__main">
          {err && <p className="page__warn" role="alert">{err}</p>}
          {edit && (
            <div className="wiki__edit" data-testid="wiki-editor">
              <input className="wiki__titre-in" value={edit.titre} onChange={(e) => setEdit({ ...edit, titre: e.target.value })} placeholder="Titre de la page" maxLength={120} autoFocus data-testid="wiki-titre" />
              <input value={edit.tags} onChange={(e) => setEdit({ ...edit, tags: e.target.value })} placeholder="Étiquettes, séparées par des virgules (ex. maison, chauffage)" />
              <div className="wiki__tools" role="toolbar" aria-label="Mise en forme">
                <button type="button" onClick={() => inserer("**", "**", "gras")} title="Gras"><b>G</b></button>
                <button type="button" onClick={() => inserer("*", "*", "italique")} title="Italique"><i>I</i></button>
                <button type="button" onClick={() => inserer("\n## ", "", "Titre")} title="Titre">T</button>
                <button type="button" onClick={() => inserer("\n- ", "", "élément")} title="Liste">•</button>
                <button type="button" onClick={() => inserer("[[", "]]", "Autre page")} title="Lien vers une autre page du wiki">[[ ]]</button>
                <button type="button" onClick={() => fichierRef.current?.click()} disabled={busy} title="Ajouter une photo ou une vidéo">📷 Photo / vidéo</button>
                <input ref={fichierRef} type="file" accept="image/*,video/*,application/pdf" hidden onChange={envoyer} />
              </div>
              <div className="wiki__split">
                <textarea ref={zone} value={edit.contenu} onChange={(e) => setEdit({ ...edit, contenu: e.target.value })} placeholder={"Écris ici. **gras**, *italique*, ## Titre, - liste, [[Autre page]]…"} data-testid="wiki-contenu" />
                <div className="wiki__preview md-page"><MessageText text={edit.contenu || "*Aperçu*"} /></div>
              </div>
              <div className="schedrow">
                <button className="btn btn--primary" onClick={enregistrer} disabled={busy || !edit.titre.trim()} data-testid="wiki-save">Enregistrer</button>
                <button className="btn btn--ghost" onClick={() => setEdit(null)}>Annuler</button>
              </div>
            </div>
          )}
          {!edit && page && (
            <>
              <div className="wiki__head">
                <h2>{page.titre}</h2>
                <div className="wiki__meta">
                  {page.tags.map((t) => <span key={t} className="chip">{t}</span>)}
                  <small className="card__hint">Modifiée par {page.updated_by || "EVA"} le {quand(page.updated_at)}{page.versions ? ` · ${page.versions} version(s) précédente(s)` : ""}</small>
                </div>
                <div className="schedrow">
                  {!invite && <button className="btn btn--primary" onClick={() => setEdit({ id: page.id, titre: page.titre, contenu: page.contenu, tags: page.tags.join(", "), base: page.updated_at, espace: page.espace })} data-testid="wiki-modifier">Modifier</button>}
                  {page.versions > 0 && <button className="btn btn--ghost" onClick={voirHisto} data-testid="wiki-histo">Historique</button>}
                  <button className="btn btn--ghost" onClick={() => window.print()}>Imprimer</button>
                  {!invite && <button className="btn btn--ghost" onClick={supprimer}>Supprimer</button>}
                </div>
              </div>
              {histo && (
                <div className="card wiki__histo">
                  <span className="card__label">Historique</span>
                  {histo.map((v) => (
                    <div key={v.id} className="schedrow">
                      <span style={{ flex: 1 }}>{quand(v.le)} — {v.auteur || "EVA"} ({v.taille} car.)</span>
                      <button className="btn btn--ghost" onClick={async () => setApercu(await api(`/api/wiki/${page.id}/versions/${v.id}`))}>Voir</button>
                      {!invite && <button className="btn btn--ghost" onClick={() => restaurer(v)}>Restaurer</button>}
                    </div>
                  ))}
                  {apercu && <div className="wiki__apercu md-page"><b>Version du {quand(apercu.le)}</b><MessageText text={apercu.contenu || "*Page vide*"} /></div>}
                </div>
              )}
              <div className="md-page wiki__content" data-testid="wiki-content"><MessageText text={page.contenu || "*Page vide : clique sur Modifier pour l'écrire.*"} /></div>
            </>
          )}
          {!edit && !page && (
            <div className="wiki__vide">
              <p>📚 Choisis une page à gauche{invite ? "" : ", ou crée-en une"}.</p>
              <p className="card__hint">Idées : codes wifi des invités, mode d'emploi de la chaudière, contacts des artisans, ce qu'il faut faire en partant en vacances… EVA lit le wiki pour te répondre (« comment on relance la chaudière ? »).</p>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
