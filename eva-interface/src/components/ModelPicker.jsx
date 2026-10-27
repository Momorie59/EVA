import { useEffect, useMemo, useRef, useState } from "react";
import { AUTO_GRATUIT, badges, decrire, grouper, libelle } from "../models/catalogue";

const CLE_FAVORIS = "eva.modeles.favoris";
const CLE_RECENTS = "eva.modeles.recents";
const lire = (k) => { try { return JSON.parse(window.localStorage.getItem(k) || "[]"); } catch { return []; } };
const ecrire = (k, v) => { try { window.localStorage.setItem(k, JSON.stringify(v)); } catch { /* stockage indisponible */ } };

const FILTRES = [
  ["tous", "Tous"],
  ["local", "🖥️ Chez moi"],
  ["gratuit", "🆓 Gratuits"],
  ["marche", "☁️ Payants"],
  ["images", "👁 Images"],
];

const icone = (d) => (d.auto ? "🔁" : d.groupe === "local" ? "🖥️" : d.groupe === "airllm" ? "🐢" : d.groupe === "gratuit" ? "🆓" : "☁️");

// Choix du modèle de la conversation : raccourcis et favoris en haut, services repliés, filtres et recherche.
export default function ModelPicker({ modeles, valeur, onChange, dernier }) {
  const [ouvert, setOuvert] = useState(false);
  const [q, setQ] = useState("");
  const [filtre, setFiltre] = useState("tous");
  const [deplies, setDeplies] = useState(() => new Set());
  const [favoris, setFavoris] = useState(() => lire(CLE_FAVORIS));
  const [recents, setRecents] = useState(() => lire(CLE_RECENTS));
  const boite = useRef(null);
  useEffect(() => {
    if (!ouvert) return undefined;
    const fermer = (e) => { if (boite.current && !boite.current.contains(e.target)) setOuvert(false); };
    const echap = (e) => { if (e.key === "Escape") setOuvert(false); };
    document.addEventListener("mousedown", fermer);
    document.addEventListener("keydown", echap);
    return () => { document.removeEventListener("mousedown", fermer); document.removeEventListener("keydown", echap); };
  }, [ouvert]);

  const tous = useMemo(() => grouper(modeles).flatMap((g) => g.modeles), [modeles]);
  const parNom = useMemo(() => Object.fromEntries(tous.map((d) => [d.name, d])), [tous]);
  const autoGratuit = parNom[AUTO_GRATUIT];

  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return tous.filter((d) => {
      if (d.auto) return false;                                   // déjà en raccourci
      if (filtre === "images" && !d.vision) return false;
      if (!["tous", "images"].includes(filtre) && d.groupe !== filtre) return false;
      return !t || `${d.name} ${d.titre} ${d.variante} ${d.source}`.toLowerCase().includes(t);
    });
  }, [tous, q, filtre]);

  // Rangement : mon serveur à plat ; services en ligne regroupés par fournisseur (repliés) ; AirLLM à la fin.
  const sections = useMemo(() => {
    const out = [];
    const locaux = visibles.filter((d) => d.groupe === "local");
    if (locaux.length) out.push({ cle: "local", titre: "🖥️ Mon serveur IA", aide: "rien ne sort de la maison", modeles: locaux, plat: true });
    for (const g of ["gratuit", "marche"]) {
      const parService = {};
      visibles.filter((d) => d.groupe === g).forEach((d) => { (parService[d.source] = parService[d.source] || []).push(d); });
      Object.entries(parService).sort(([a], [b]) => a.localeCompare(b)).forEach(([service, liste]) => {
        out.push({ cle: `${g}:${service}`, titre: `${g === "gratuit" ? "🆓" : "☁️"} ${service}`, aide: g === "gratuit" ? "gratuit, en ligne" : "payant, en ligne", modeles: liste });
      });
    }
    const air = visibles.filter((d) => d.groupe === "airllm");
    if (air.length) out.push({ cle: "airllm", titre: "🐢 AirLLM", aide: "très lent", modeles: air, plat: true });
    return out;
  }, [visibles]);

  const choisi = valeur ? (parNom[valeur] || decrire({ name: valeur })) : null;
  const cherche = q.trim().length > 0;

  function choisir(n) {
    onChange(n);
    setOuvert(false);
    setQ("");
    if (n) {
      const r = [n, ...recents.filter((x) => x !== n)].slice(0, 4);
      setRecents(r);
      ecrire(CLE_RECENTS, r);
    }
  }
  function basculerFavori(e, n) {
    e.stopPropagation();
    const f = favoris.includes(n) ? favoris.filter((x) => x !== n) : [...favoris, n];
    setFavoris(f);
    ecrire(CLE_FAVORIS, f);
  }
  function deplier(cle) {
    setDeplies((s) => { const n = new Set(s); if (n.has(cle)) n.delete(cle); else n.add(cle); return n; });
  }

  const ligne = (d) => (
    <button type="button" role="option" aria-selected={valeur === d.name} key={d.name} className={`mp__item ${valeur === d.name ? "is-on" : ""}`}
      onClick={() => choisir(d.name)} title={d.name} data-testid={`mp-${d.name}`}>
      <span className="mp__titre">{d.titre}{d.variante && <em> {d.variante}</em>}</span>
      <span className="mp__icones">
        {badges(d).filter((b) => b.k !== "faible").map((b) => <i key={b.t} title={`${b.t.replace(/^\S+\s/, "")} — ${b.aide}`} className={b.k ? `is-${b.k}` : ""}>{b.t.split(" ")[0]}</i>)}
        <span role="button" tabIndex={-1} className={`mp__etoile ${favoris.includes(d.name) ? "is-on" : ""}`} onClick={(e) => basculerFavori(e, d.name)}
          title={favoris.includes(d.name) ? "Retirer des favoris" : "Mettre en favori (toujours en haut)"} data-testid={`fav-${d.name}`}>★</span>
      </span>
    </button>
  );

  const favorisVisibles = favoris.map((n) => parNom[n]).filter(Boolean);
  const recentsVisibles = recents.map((n) => parNom[n]).filter((d) => d && !favoris.includes(d.name) && !d.auto).slice(0, 3);

  return (
    <div className="mp" ref={boite}>
      <button type="button" className={`mp__bouton ${valeur ? "is-force" : ""}`} onClick={() => setOuvert((v) => !v)} aria-haspopup="listbox" aria-expanded={ouvert}
        title={dernier ? `Dernière réponse : ${libelle(dernier.model, modeles)} — ${dernier.reason}` : "Modèle pour cette conversation"} data-testid="model-picker">
        <span className="mp__icone">{choisi ? icone(choisi) : "✨"}</span>
        <span className="mp__nom">{choisi ? `${choisi.titre}${choisi.variante ? ` ${choisi.variante}` : ""}` : "Automatique"}</span>
        {!valeur && dernier && <span className="mp__dernier">· {libelle(dernier.model, modeles)}</span>}
        <span aria-hidden="true" className="mp__fleche">▾</span>
      </button>
      {ouvert && (
        <div className="mp__panneau" role="listbox" data-testid="model-panel">
          <div className="mp__raccourcis">
            <button type="button" className={`mp__carte ${!valeur ? "is-on" : ""}`} onClick={() => choisir("")} data-testid="mp-auto">
              <b>✨ Automatique</b><small>EVA choisit selon la demande</small>
            </button>
            {autoGratuit && (
              <button type="button" className={`mp__carte ${valeur === AUTO_GRATUIT ? "is-on" : ""}`} onClick={() => choisir(AUTO_GRATUIT)} data-testid={`mp-${AUTO_GRATUIT}`}>
                <b>🔁 IA gratuites</b><small>passe de l'une à l'autre toute seule</small>
              </button>
            )}
          </div>

          <input className="mp__recherche" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Chercher parmi ${tous.length} modèles…`} autoFocus data-testid="mp-recherche" />
          <div className="mp__filtres" role="tablist">
            {FILTRES.filter(([id]) => id === "tous" || id === "images" || tous.some((d) => d.groupe === id)).map(([id, l]) => (
              <button key={id} type="button" className={filtre === id ? "is-on" : ""} onClick={() => setFiltre(id)} data-testid={`mp-filtre-${id}`}>{l}</button>
            ))}
          </div>

          {!cherche && filtre === "tous" && favorisVisibles.length > 0 && (
            <div className="mp__groupe"><div className="mp__entete"><span>★ Favoris</span></div>{favorisVisibles.map(ligne)}</div>
          )}
          {!cherche && filtre === "tous" && recentsVisibles.length > 0 && (
            <div className="mp__groupe"><div className="mp__entete"><span>🕘 Récents</span></div>{recentsVisibles.map(ligne)}</div>
          )}

          {sections.map((s) => {
            const ouverte = s.plat || cherche || filtre !== "tous" || deplies.has(s.cle) || s.modeles.some((d) => d.name === valeur);
            return (
              <div key={s.cle} className="mp__groupe">
                {s.plat ? (
                  <div className="mp__entete"><span>{s.titre}</span><small>{s.aide}</small></div>
                ) : (
                  <button type="button" className="mp__entete mp__entete--repli" onClick={() => deplier(s.cle)} aria-expanded={ouverte} data-testid={`mp-service-${s.cle}`}>
                    <span>{ouverte ? "▾" : "▸"} {s.titre}</span><small>{s.modeles.length} modèle{s.modeles.length > 1 ? "s" : ""} · {s.aide}</small>
                  </button>
                )}
                {ouverte && s.modeles.map(ligne)}
              </div>
            );
          })}
          {sections.length === 0 && <p className="mp__vide">Aucun modèle ne correspond.</p>}
          <p className="mp__legende">⚡ en mémoire · 🛠 outils · 👁 images · 🌐 en ligne · ⚠️ entraînement · ★ favori</p>
        </div>
      )}
    </div>
  );
}
