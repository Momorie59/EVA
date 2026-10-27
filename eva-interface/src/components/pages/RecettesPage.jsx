import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { CORE_URL } from "../../urls";
import { envoyerMedia } from "./WikiPage";
import { confirmer } from "../../confirmer";

const EMOJI = { "Apéritif": "🥂", "Entrée": "🥗", "Plat": "🍲", "Accompagnement": "🥔", "Dessert": "🍰", "Goûter": "🧁", "Boisson": "🍹", "Sauce": "🥫", "Autre": "🍽️" };
const media = (f) => (f ? `${CORE_URL}/api/public/medias/${f}` : "");
const duree = (m) => (!m ? "" : m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`);
const VIDE = { titre: "", resume: "", personnes: 4, prep_min: 0, cuisson_min: 0, repos_min: 0, difficulte: "Facile", categorie: "Plat", tags: "", ingredientsTexte: "", etapes: [{ texte: "", photo: "", minuteur_min: 0 }], photo: "", video: "", videoLien: "", notes: "", prive: false };

function Couverture({ r, grande }) {
  return r.photo
    ? <img className={grande ? "rec-hero" : "rec-card__img"} src={media(r.photo)} alt="" loading="lazy" />
    : <div className={`${grande ? "rec-hero" : "rec-card__img"} rec-vide`} aria-hidden="true">{EMOJI[r.categorie] || "🍽️"}</div>;
}

function Video({ v }) {
  if (!v) return null;
  if (v.startsWith("yt:")) return <div className="rec-video"><iframe src={`https://www.youtube-nocookie.com/embed/${v.slice(3)}`} title="Vidéo de la recette" allow="encrypted-media; picture-in-picture" allowFullScreen loading="lazy" /></div>;
  return <div className="rec-video"><video src={media(v)} controls preload="metadata" /></div>;
}

// Vue d'une recette (aussi utilisée pour l'impression du livre).
function VueRecette({ r, lignes, pour, onPour, actions }) {
  const temps = [["Préparation", r.prep_min], ["Cuisson", r.cuisson_min], ["Repos", r.repos_min]].filter(([, m]) => m);
  return (
    <article className="rec-vue">
      <Couverture r={r} grande />
      <h2 className="rec-titre">{r.titre}</h2>
      {r.resume && <p className="rec-resume">{r.resume}</p>}
      <div className="rec-chips">
        <span>{EMOJI[r.categorie]} {r.categorie}</span><span>{r.difficulte}</span>
        {temps.map(([l, m]) => <span key={l}>⏱ {l} {duree(m)}</span>)}
        {r.tags.map((t) => <span key={t}>#{t}</span>)}
        {r.prive && <span>🔒 privée</span>}
      </div>
      {actions}
      <div className="rec-grille">
        <section className="rec-ingredients">
          <h3>Ingrédients</h3>
          <div className="rec-portions">
            {onPour && <button type="button" onClick={() => onPour(Math.max(1, pour - 1))} aria-label="Moins de personnes">−</button>}
            <span>Pour <b>{pour}</b> personne{pour > 1 ? "s" : ""}</span>
            {onPour && <button type="button" onClick={() => onPour(Math.min(100, pour + 1))} aria-label="Plus de personnes">+</button>}
          </div>
          <ul>{lignes.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </section>
        <section className="rec-etapes">
          <h3>Préparation</h3>
          <ol>{r.etapes.map((e, i) => (
            <li key={i}>
              <p>{e.texte}</p>
              {e.photo && <img src={media(e.photo)} alt={`Étape ${i + 1}`} loading="lazy" />}
              {e.minuteur_min > 0 && <span className="rec-minuteur">⏱ {duree(e.minuteur_min)}</span>}
            </li>
          ))}</ol>
        </section>
      </div>
      <Video v={r.video} />
      {r.notes && <section className="rec-notes"><h3>Le petit plus</h3><p>{r.notes}</p></section>}
    </article>
  );
}

// Livre de recettes de la famille : photos, étapes, vidéos, partage, liste de courses en un clic.
export default function RecettesPage() {
  const [liste, setListe] = useState([]);
  const [meta, setMeta] = useState({ categories: [], difficultes: [], peut_ecrire: false });
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [rec, setRec] = useState(null);
  const [pour, setPour] = useState(4);
  const [edit, setEdit] = useState(null);
  const [livre, setLivre] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const couvRef = useRef(null);
  const videoRef = useRef(null);

  const charger = useCallback(() => api(`/api/recettes?q=${encodeURIComponent(q)}&categorie=${encodeURIComponent(cat)}`)
    .then((d) => { setListe(d.recettes || []); setMeta(d); }).catch((e) => setErr(e.message)), [q, cat]);
  useEffect(() => { const t = setTimeout(charger, 200); return () => clearTimeout(t); }, [charger]);

  const ouvrir = async (id, n) => {
    setErr(""); setMsg(""); setEdit(null);
    try { const r = await api(`/api/recettes/${id}${n ? `?personnes=${n}` : ""}`); setRec(r); setPour(r.pour); window.scrollTo?.(0, 0); } catch (e) { setErr(e.message); }
  };
  const changerPour = (n) => { setPour(n); ouvrir(rec.id, n); };
  const agir = async (fn) => { setBusy(true); setErr(""); setMsg(""); try { await fn(); } catch (e) { setErr(e.message); } setBusy(false); };

  const courses = (imprimer) => agir(async () => {
    const r = await api(`/api/recettes/${rec.id}/courses`, { method: "POST", body: JSON.stringify({ personnes: pour, imprimer }) });
    const parts = [];
    if (r.ajoutes.length) parts.push(`🛒 Ajouté à la liste « ${r.liste} » : ${r.ajoutes.join(", ")}.`);
    if (r.deja.length) parts.push(`Déjà sur la liste : ${r.deja.join(", ")}.`);
    if (imprimer) parts.push(r.impression_erreur ? `⚠️ Impression impossible : ${r.impression_erreur}` : "🖨️ Liste envoyée à l'imprimante.");
    setMsg(parts.join(" "));
  });
  const partager = (actif) => agir(async () => {
    const r = await api(`/api/recettes/${rec.id}/partage`, { method: "POST", body: JSON.stringify({ actif }) });
    setRec({ ...rec, partage: r.partage });
    if (actif) {
      const lien = `${window.location.origin}${r.url}`;
      try { await navigator.clipboard.writeText(lien); setMsg(`🔗 Lien copié : ${lien} — envoie-le à qui tu veux (lecture seule). Tes amis doivent pouvoir joindre EVA depuis Internet (voir ACCES-A-DISTANCE.md).`); }
      catch { setMsg(`🔗 Lien de partage : ${lien}`); }
    } else setMsg("Lien de partage retiré : l'ancien lien ne marche plus.");
  });
  const supprimer = async () => { if ((await confirmer(`Supprimer « ${rec.titre} » et ses photos ?`))) agir(async () => { await api(`/api/recettes/${rec.id}`, { method: "DELETE" }); setRec(null); charger(); }); };

  // Édition
  const commencer = (r) => {
    setRec(null); setErr(""); setMsg("");
    setEdit(r ? { ...r, tags: r.tags.join(", "), ingredientsTexte: r.lignes ? r.ingredients.map((i) => [i.quantite == null ? "" : String(Math.round(i.quantite * 100) / 100).replace(".", ","), i.unite, i.nom].filter((x) => x !== "").join(" ")).join("\n") : "",
      etapes: r.etapes.length ? r.etapes : [{ texte: "", photo: "", minuteur_min: 0 }], videoLien: r.video?.startsWith("yt:") ? `https://youtu.be/${r.video.slice(3)}` : "" } : { ...VIDE });
  };
  const champ = (k) => (e) => setEdit({ ...edit, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const etape = (i, patch) => setEdit({ ...edit, etapes: edit.etapes.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const envoyer = async (f, apres) => { if (!f) return; setBusy(true); setErr(""); try { const d = await envoyerMedia("recettes", f); apres(d.fichier); } catch (e) { setErr(e.message); } setBusy(false); };
  const enregistrer = () => agir(async () => {
    const corps = { ...edit, tags: edit.tags.split(",").map((x) => x.trim()).filter(Boolean),
      ingredients: edit.ingredientsTexte.split("\n").map((x) => x.trim()).filter(Boolean),
      etapes: edit.etapes.filter((e) => e.texte.trim() || e.photo),
      video: edit.videoLien.trim() ? edit.videoLien.trim() : (edit.video?.startsWith("yt:") ? "" : edit.video) };
    const r = edit.id ? await api(`/api/recettes/${edit.id}`, { method: "PUT", body: JSON.stringify(corps) })
      : await api("/api/recettes", { method: "POST", body: JSON.stringify(corps) });
    setEdit(null); charger(); ouvrir(r.id);
  });

  // Livre complet à imprimer (PDF) : toutes les recettes du filtre, une par page, avec sommaire.
  const imprimerLivre = () => agir(async () => {
    const tout = await Promise.all(liste.map((r) => api(`/api/recettes/${r.id}`)));
    setLivre(tout);
    setTimeout(() => { window.print(); }, 900);
  });
  useEffect(() => { const f = () => setLivre(null); window.addEventListener("afterprint", f); return () => window.removeEventListener("afterprint", f); }, []);

  if (livre) {
    return (
      <section className="page rec-livre" data-testid="rec-livre">
        <div className="rec-livre__couv"><h1>Le livre de recettes de la famille</h1><p>{livre.length} recettes</p></div>
        <ol className="rec-livre__sommaire">{livre.map((r) => <li key={r.id}>{r.titre} <small>({r.categorie})</small></li>)}</ol>
        {livre.map((r) => <div key={r.id} className="rec-livre__page"><VueRecette r={r} lignes={r.lignes} pour={r.pour} /></div>)}
        <button className="btn btn--ghost rec-livre__fermer" onClick={() => setLivre(null)}>Fermer l'aperçu</button>
      </section>
    );
  }

  return (
    <section className="page recettes" data-testid="recettes-page">
      <header className="page__header">
        <h1>Recettes</h1>
        <span className="page__sub">Le livre de recettes de la famille</span>
        <div className="page__action rec-head-actions">
          {meta.peut_ecrire && <button className="btn btn--primary" onClick={() => commencer(null)} data-testid="rec-new">+ Nouvelle recette</button>}
          {liste.length > 0 && <button className="btn btn--ghost" onClick={imprimerLivre} disabled={busy} title="Imprimer ou enregistrer en PDF tout le livre">📖 Livre en PDF</button>}
        </div>
      </header>
      <div className="page__body">
        {err && <p className="page__warn" role="alert">{err}</p>}
        {msg && <p className="rec-msg" role="status">{msg}</p>}

        {edit && (
          <div className="card rec-edit" data-testid="rec-editor">
            <span className="card__label">{edit.id ? "Modifier la recette" : "Nouvelle recette"}</span>
            <div className="rec-edit__couv">
              {edit.photo ? <img src={media(edit.photo)} alt="" /> : <div className="rec-vide">{EMOJI[edit.categorie]}</div>}
              <button type="button" className="btn btn--ghost" onClick={() => couvRef.current?.click()} disabled={busy}>📷 {edit.photo ? "Changer la photo" : "Ajouter une photo"}</button>
              <input ref={couvRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; envoyer(f, (x) => setEdit((d) => ({ ...d, photo: x }))); }} />
            </div>
            <input className="rec-edit__titre" value={edit.titre} onChange={champ("titre")} placeholder="Nom de la recette" maxLength={150} autoFocus data-testid="rec-titre" />
            <textarea value={edit.resume} onChange={champ("resume")} rows={2} placeholder="En une phrase : ce qui la rend spéciale" maxLength={1000} />
            <div className="rec-edit__ligne">
              <label>Personnes <input type="number" min="1" max="100" value={edit.personnes} onChange={champ("personnes")} /></label>
              <label>Préparation (min) <input type="number" min="0" value={edit.prep_min} onChange={champ("prep_min")} /></label>
              <label>Cuisson (min) <input type="number" min="0" value={edit.cuisson_min} onChange={champ("cuisson_min")} /></label>
              <label>Repos (min) <input type="number" min="0" value={edit.repos_min} onChange={champ("repos_min")} /></label>
              <label>Catégorie <select value={edit.categorie} onChange={champ("categorie")}>{meta.categories.map((c) => <option key={c}>{c}</option>)}</select></label>
              <label>Difficulté <select value={edit.difficulte} onChange={champ("difficulte")}>{meta.difficultes.map((c) => <option key={c}>{c}</option>)}</select></label>
            </div>
            <label className="rec-edit__bloc">Ingrédients <small className="card__hint">(un par ligne : « 200 g de farine », « 3 œufs », « 1 pincée de sel »)</small>
              <textarea value={edit.ingredientsTexte} onChange={champ("ingredientsTexte")} rows={7} placeholder={"250 g de farine\n4 œufs\n1/2 l de lait"} data-testid="rec-ingredients" />
            </label>
            <div className="rec-edit__bloc">Étapes
              {edit.etapes.map((e, i) => (
                <div key={i} className="rec-edit__etape">
                  <span className="rec-edit__num">{i + 1}</span>
                  <textarea value={e.texte} onChange={(ev) => etape(i, { texte: ev.target.value })} rows={2} placeholder="Ce qu'il faut faire" data-testid={`rec-etape-${i}`} />
                  <div className="rec-edit__etape-outils">
                    {e.photo && <img src={media(e.photo)} alt="" />}
                    <label className="btn btn--ghost">📷<input type="file" accept="image/*" hidden onChange={(ev) => { const f = ev.target.files?.[0]; ev.target.value = ""; envoyer(f, (x) => etape(i, { photo: x })); }} /></label>
                    <label title="Minuteur (minutes)">⏱<input type="number" min="0" value={e.minuteur_min || 0} onChange={(ev) => etape(i, { minuteur_min: Number(ev.target.value) })} /></label>
                    <button type="button" className="btn btn--ghost" onClick={() => setEdit({ ...edit, etapes: edit.etapes.filter((_, j) => j !== i) })} aria-label="Retirer l'étape">✕</button>
                  </div>
                </div>
              ))}
              <button type="button" className="btn btn--ghost" onClick={() => setEdit({ ...edit, etapes: [...edit.etapes, { texte: "", photo: "", minuteur_min: 0 }] })}>+ Étape</button>
            </div>
            <div className="rec-edit__bloc">Vidéo
              <div className="rec-edit__ligne">
                <input value={edit.videoLien} onChange={champ("videoLien")} placeholder="Lien YouTube (facultatif)" style={{ flex: 2 }} />
                <span className="card__hint">ou</span>
                <button type="button" className="btn btn--ghost" onClick={() => videoRef.current?.click()} disabled={busy}>🎬 {edit.video && !edit.video.startsWith("yt:") ? "Changer la vidéo" : "Envoyer une vidéo"}</button>
                <input ref={videoRef} type="file" accept="video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; envoyer(f, (x) => setEdit((d) => ({ ...d, video: x, videoLien: "" }))); }} />
                {edit.video && !edit.video.startsWith("yt:") && <span className="card__hint">✔ vidéo envoyée</span>}
              </div>
            </div>
            <textarea value={edit.notes} onChange={champ("notes")} rows={2} placeholder="Le petit plus, une astuce, une variante…" />
            <input value={edit.tags} onChange={champ("tags")} placeholder="Étiquettes : rapide, enfants, sans gluten…" />
            <label className="access__f"><input type="checkbox" checked={edit.prive} onChange={champ("prive")} /> Recette privée (visible par moi seul)</label>
            <div className="schedrow">
              <button className="btn btn--primary" onClick={enregistrer} disabled={busy || !edit.titre.trim()} data-testid="rec-save">{busy ? "…" : "Enregistrer"}</button>
              <button className="btn btn--ghost" onClick={() => setEdit(null)}>Annuler</button>
            </div>
          </div>
        )}

        {!edit && rec && (
          <>
            <button className="btn btn--ghost rec-retour" onClick={() => { setRec(null); setMsg(""); }}>← Toutes les recettes</button>
            <VueRecette r={rec} lignes={rec.lignes} pour={pour} onPour={changerPour} actions={(
              <div className="rec-actions" data-testid="rec-actions">
                <button className="btn btn--primary" onClick={() => courses(false)} disabled={busy} data-testid="rec-courses">🛒 Liste de courses</button>
                <button className="btn btn--ghost" onClick={() => courses(true)} disabled={busy}>🖨️ Liste + impression</button>
                <button className="btn btn--ghost" onClick={() => window.print()}>📄 PDF / Imprimer</button>
                {rec.peut_modifier && <button className="btn btn--ghost" onClick={() => partager(true)} disabled={busy} data-testid="rec-partager">🔗 {rec.partage ? "Copier le lien" : "Partager"}</button>}
                {rec.peut_modifier && rec.partage && <button className="btn btn--ghost" onClick={() => partager(false)} disabled={busy}>Retirer le lien</button>}
                {rec.peut_modifier && <button className="btn btn--ghost" onClick={() => commencer(rec)}>✏️ Modifier</button>}
                {rec.peut_modifier && <button className="btn btn--ghost" onClick={supprimer}>🗑️</button>}
              </div>
            )} />
          </>
        )}

        {!edit && !rec && (
          <>
            <div className="rec-filtres">
              <input className="convs__search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher : crêpes, poulet, rapide…" aria-label="Rechercher une recette" />
              <div className="rec-cats">
                <button className={cat === "" ? "is-on" : ""} onClick={() => setCat("")}>Toutes</button>
                {meta.categories.map((c) => <button key={c} className={cat === c ? "is-on" : ""} onClick={() => setCat(c)}>{EMOJI[c]} {c}</button>)}
              </div>
            </div>
            {liste.length === 0 && (
              <div className="wiki__vide">
                <p>🍲 {q || cat ? "Aucune recette ne correspond." : "Le livre est encore vide."}</p>
                {meta.peut_ecrire && !q && !cat && <p className="card__hint">Ajoute ta première recette, ou demande à EVA : « garde cette recette dans le livre ».</p>}
              </div>
            )}
            <div className="rec-grid">
              {liste.map((r) => (
                <button key={r.id} className="rec-card" onClick={() => ouvrir(r.id)} data-testid="rec-card">
                  <Couverture r={r} />
                  <span className="rec-card__corps">
                    <b>{r.titre}</b>
                    <small>{EMOJI[r.categorie]} {r.categorie} · {r.personnes} pers.{r.prep_min + r.cuisson_min ? ` · ${duree(r.prep_min + r.cuisson_min)}` : ""}{r.prive ? " · 🔒" : ""}</small>
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
