import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { CORE_URL, authHeaders } from "../../urls";
import { useAuth } from "../AuthGate";
import { confirmer } from "../../confirmer";

// Papiers : EVA lit les papiers de la famille (via Paperless pour l'OCR), suit les échéances et prévient à temps.
const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const fdate = (s) => { if (!s) return ""; const [a, m, j] = s.split("-"); return `${+j} ${MOIS[+m - 1]} ${a}`; };
const fdelai = (n) => (n < 0 ? `retard ${-n} j` : n === 0 ? "aujourd'hui" : n === 1 ? "demain" : `dans ${n} j`);
const SECONDES_PAR_ANALYSE = 45;   // ordre de grandeur sur une GTX 1060, pour l'estimation affichée

async function envoyerFichier(file) {
  const res = await fetch(`${CORE_URL}/api/papiers/deposer?nom=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { ...authHeaders(), "Content-Type": "application/octet-stream" }, body: file,
  });
  if (!res.ok) {
    let d = null; try { d = (await res.json())?.detail; } catch { /* vide */ }
    throw new Error(typeof d === "string" ? d : `Erreur ${res.status}`);
  }
  return res.json();
}

export default function PapiersPage() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const [tab, setTab] = useState("avenir");
  const [etat, setEtat] = useState(null);
  const [ech, setEch] = useState([]);
  const [verif, setVerif] = useState([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const charger = useCallback(async () => {
    try {
      const e = await api("/api/papiers/etat");
      setEtat(e);
      if (e.actif) {
        const [a, b] = await Promise.all([api("/api/papiers/echeances?jours=365&statut=active"), api("/api/papiers/a-verifier")]);
        setEch(a); setVerif(b);
      }
      setError("");
    } catch (err) { setError(err.message); }
  }, []);
  useEffect(() => { charger(); const t = setInterval(charger, 10000); return () => clearInterval(t); }, [charger]);
  useEffect(() => { if (etat && !etat.actif && admin) setTab("reglages"); }, [etat?.actif, admin]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn, done) {
    setError(""); setMsg("");
    try { const r = await fn(); if (done) setMsg(typeof done === "function" ? done(r) : done); await charger(); } catch (e) { setError(e.message); }
  }
  const marquer = (id, action) => act(() => api(`/api/papiers/echeances/${id}/${action}`, { method: "POST" }));

  const tabs = [["avenir", `À venir${ech.length ? ` (${ech.length})` : ""}`], ["verif", `À vérifier${verif.length ? ` (${verif.length})` : ""}`], ["deposer", "Déposer"]];
  if (admin) tabs.push(["reglages", "Réglages"]);

  return (
    <section className="page" data-testid="papiers-page">
      <header className="page__header"><h1>Papiers</h1><span className="page__sub">Contrats, assurances, impôts, garanties : EVA lit tes papiers et te prévient avant qu'il soit trop tard. Elle ne résilie et ne paie jamais rien.</span></header>
      <div className="page__body">
        {etat && <Progression etat={etat} onSonder={() => act(() => api("/api/papiers/sonder", { method: "POST" }), "Passage lancé.")} />}
        <div className="pj-sbx__tabs" data-testid="papiers-tabs">
          {tabs.map(([id, label]) => <button key={id} className={tab === id ? "is-on" : ""} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        {etat && !etat.actif && tab !== "reglages" && (
          <div className="card"><p>Les papiers ne sont pas encore configurés : {admin ? "renseigne l'adresse et le jeton de Paperless dans l'onglet Réglages." : "demande à l'administrateur de les configurer."}</p></div>
        )}
        {etat?.actif && tab === "avenir" && <Echeances ech={ech} onMarquer={marquer} />}
        {etat?.actif && tab === "verif" && <AVerifier docs={verif} act={act} />}
        {tab === "deposer" && <Deposer actif={!!etat?.actif} onFini={charger} />}
        {tab === "reglages" && admin && <Reglages onSaved={charger} setMsg={setMsg} setError={setError} />}
        {error && <p className="page__warn" role="alert" data-testid="papiers-error">{error}</p>}
        {msg && <p className="page__sub">{msg}</p>}
      </div>
    </section>
  );
}

function Progression({ etat, onSonder }) {
  const p = etat.progression || {};
  const total = p.dans_paperless ?? 0;
  const faits = (p.analyses ?? 0) + (p.analyses_en_erreur ?? 0);
  const pct = total ? Math.round((faits / total) * 100) : 0;
  const restant = (p.a_analyser ?? 0);
  const enCours = restant > 0 || p.dans_les_dossiers > 0;
  const parPassage = Math.max(1, +etat.reglages?.analyses_par_passage || 3);
  const eta = restant * SECONDES_PAR_ANALYSE + Math.ceil(restant / parPassage) * 60;   // analyses + pause d'une minute entre deux passages
  const etaTxt = eta > 3600 ? `≈ ${Math.round(eta / 3600)} h` : eta > 60 ? `≈ ${Math.round(eta / 60)} min` : "moins d'une minute";
  return (
    <div className="card pap-prog" data-testid="papiers-progression">
      <div className="pap-prog__steps">
        <div><b>{p.dans_les_dossiers ?? 0}</b><span>dans tes dossiers</span></div>
        <div><b>{total}</b><span>lus par Paperless</span></div>
        <div><b>{p.analyses ?? 0}</b><span>analysés</span></div>
        <div><b>{etat.stats?.echeances_actives ?? 0}</b><span>échéances suivies</span></div>
      </div>
      {total > 0 && <div className="pap-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${pct}%` }} /></div>}
      <div className="pj-row pap-prog__info">
        <span className="page__sub">
          {enCours ? `En cours : ${restant} document(s) à analyser${restant ? `, fin estimée ${etaTxt}` : ""}${p.dans_les_dossiers ? `, ${p.dans_les_dossiers} fichier(s) en attente d'envoi` : ""}.` : etat.actif ? "Tout est à jour." : ""}
          {p.analyses_en_erreur ? ` ${p.analyses_en_erreur} document(s) illisible(s) (onglet À vérifier).` : ""}
        </span>
        {etat.actif && <button className="btn btn--ghost" onClick={onSonder}>Vérifier maintenant</button>}
      </div>
      {p.derniere_erreur && <p className="page__warn">Dernier passage : {p.derniere_erreur}</p>}
      {(p.problemes_dossiers || []).map((x) => <p key={x} className="page__warn">Dossier : {x}</p>)}
      {(p.imports_en_erreur || []).length > 0 && (
        <details><summary>{p.imports_en_erreur.length} fichier(s) non envoyé(s)</summary>
          <ul className="pj-trash__list">{p.imports_en_erreur.map((i) => <li key={i.chemin}><span>{i.chemin.split("/").pop()} : {i.erreur}</span></li>)}</ul>
        </details>
      )}
    </div>
  );
}

function Echeances({ ech, onMarquer }) {
  if (!ech.length) return <div className="card"><p className="page__sub">Aucune échéance dans l'année. Dépose des papiers (onglet Déposer ou dossier surveillé).</p></div>;
  return (
    <div className="card" data-testid="papiers-echeances">
      <ul className="pap-list">
        {ech.map((e) => {
          const n = e.jours_restants;
          return (
            <li key={e.id}>
              <span className={`pap-delai ${n <= 7 ? "is-urgent" : n <= 30 ? "is-bientot" : ""}`}>{fdelai(n)}</span>
              <span className="pap-list__txt">
                {e.description}
                <small className="pap-meta">
                  {e.preavis_jours ? ` agir avant le ${fdate(e.date_action)} · échéance ${fdate(e.date_echeance)} (préavis ${e.preavis_jours} j)` : ` ${fdate(e.date_echeance)}`}
                  {e.pays && e.pays !== "autre" ? ` · ${e.pays}` : ""} · <a href={e.lien_document} target="_blank" rel="noreferrer">{e.titre || "document"}</a>
                </small>
              </span>
              <button className="btn btn--ghost" onClick={() => onMarquer(e.id, "faite")}>C'est fait</button>
              <button className="btn btn--ghost" onClick={() => onMarquer(e.id, "ignorer")}>Ignorer</button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AVerifier({ docs, act }) {
  if (!docs.length) return <div className="card"><p className="page__sub">Rien à vérifier : tout ce qu'EVA a lu est clair.</p></div>;
  return docs.map((d) => <DocAVerifier key={d.paperless_id} d={d} act={act} />);
}

function DocAVerifier({ d, act }) {
  const enAttente = (d.echeances || []).filter((e) => e.statut === "a_valider");
  const [champs, setChamps] = useState({});
  const [ajout, setAjout] = useState({ description: "", date_echeance: "" });
  const val = (e, k) => champs[e.id]?.[k] ?? e[k] ?? "";
  const set = (e, k, v) => setChamps((c) => ({ ...c, [e.id]: { ...c[e.id], [k]: v } }));
  const corriger = (e) => act(() => api(`/api/papiers/echeances/${e.id}`, { method: "PATCH", body: JSON.stringify({
    description: val(e, "description"), date_echeance: val(e, "date_echeance"),
    preavis_jours: val(e, "preavis_jours") === "" ? null : +val(e, "preavis_jours") }) }), "Échéance validée.");
  const ajouter = () => act(async () => {
    await api("/api/papiers/echeances", { method: "POST", body: JSON.stringify({ paperless_id: d.paperless_id, ...ajout }) });
    await api(`/api/papiers/documents/${d.paperless_id}/valider`, { method: "POST" });
  }, "Échéance ajoutée.");
  return (
    <div className="card" data-testid="papiers-a-verifier">
      <div className="pj-row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>{d.titre || `Document ${d.paperless_id}`}</b>
          <small className="pap-meta"> {d.resume || d.erreur || ""}{d.confiance != null ? ` · confiance ${Math.round(d.confiance * 100)} %` : ""} · <a href={d.lien_document} target="_blank" rel="noreferrer">ouvrir</a></small>
        </div>
        <div className="pj-row">
          <button className="btn btn--ghost" onClick={() => act(() => api(`/api/papiers/documents/${d.paperless_id}/retraiter`, { method: "POST" }), "Analyse relancée.")}>Relancer l'analyse</button>
          {d.statut !== "erreur" && <button className="btn" onClick={() => act(() => api(`/api/papiers/documents/${d.paperless_id}/valider`, { method: "POST" }), "Validé.")}>{enAttente.length ? "Tout valider" : "Rien à suivre"}</button>}
        </div>
      </div>
      {(d.avertissements || []).length > 0 && <ul className="pap-av">{d.avertissements.map((a) => <li key={a}>{a}</li>)}</ul>}
      {enAttente.map((e) => (
        <div className="pj-row pap-edit" key={e.id}>
          <input value={val(e, "description")} onChange={(x) => set(e, "description", x.target.value)} aria-label="Description" />
          <input type="date" value={val(e, "date_echeance")} onChange={(x) => set(e, "date_echeance", x.target.value)} aria-label="Date d'échéance" />
          <input type="number" min="0" placeholder="préavis (j)" value={val(e, "preavis_jours")} onChange={(x) => set(e, "preavis_jours", x.target.value)} style={{ width: 120 }} aria-label="Préavis en jours" />
          <button className="btn btn--primary" onClick={() => corriger(e)}>Valider</button>
          <button className="btn btn--ghost" onClick={() => act(() => api(`/api/papiers/echeances/${e.id}/ignorer`, { method: "POST" }))}>Ignorer</button>
        </div>
      ))}
      {!enAttente.length && d.statut !== "erreur" && (
        <div className="pj-row pap-edit">
          <input placeholder="Une échéance oubliée ? Description" value={ajout.description} onChange={(x) => setAjout({ ...ajout, description: x.target.value })} />
          <input type="date" value={ajout.date_echeance} onChange={(x) => setAjout({ ...ajout, date_echeance: x.target.value })} aria-label="Date" />
          <button className="btn" disabled={!ajout.description.trim() || !ajout.date_echeance} onClick={ajouter}>Ajouter</button>
        </div>
      )}
    </div>
  );
}

function Deposer({ actif, onFini }) {
  const [files, setFiles] = useState([]);           // {name, size, etat: attente|envoi|ok|erreur, erreur}
  const [envoi, setEnvoi] = useState(false);
  const [survol, setSurvol] = useState(false);
  const input = useRef(null);

  const ajouter = (liste) => setFiles((f) => [...f, ...Array.from(liste).map((file) => ({ file, name: file.name, size: file.size, etat: "attente" }))]);
  async function tout() {
    setEnvoi(true);
    const maj = (i, v) => setFiles((f) => f.map((x, j) => (j === i ? { ...x, ...v } : x)));
    let i = 0;
    const travail = async () => {
      while (i < files.length) {
        const k = i++;
        if (files[k].etat === "ok") continue;
        maj(k, { etat: "envoi" });
        try { await envoyerFichier(files[k].file); maj(k, { etat: "ok" }); } catch (e) { maj(k, { etat: "erreur", erreur: e.message }); }
      }
    };
    await Promise.all([travail(), travail()]);       // deux envois à la fois : le NAS suit sans peine
    setEnvoi(false);
    onFini();
  }
  const ok = files.filter((f) => f.etat === "ok").length;
  const ko = files.filter((f) => f.etat === "erreur").length;
  return (
    <div className="card" data-testid="papiers-deposer">
      <div className={`pap-drop ${survol ? "is-over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setSurvol(true); }} onDragLeave={() => setSurvol(false)}
        onDrop={(e) => { e.preventDefault(); setSurvol(false); ajouter(e.dataTransfer.files); }}
        onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()}>
        <b>Glisse ici tes papiers</b><span>PDF, photos, Word… autant que tu veux. Ou clique pour choisir.</span>
        <input ref={input} type="file" multiple hidden onChange={(e) => { ajouter(e.target.files); e.target.value = ""; }}
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.gif,.txt,.eml,.doc,.docx,.odt,.xls,.xlsx,.ods,.ppt,.pptx,.odp,.rtf" />
      </div>
      {files.length > 0 && (
        <>
          <div className="pj-row" style={{ margin: "10px 0" }}>
            <span className="page__sub">{files.length} fichier(s){ok ? ` · ${ok} envoyé(s)` : ""}{ko ? ` · ${ko} en erreur` : ""}</span>
            <button className="btn btn--primary" disabled={!actif || envoi || ok === files.length} onClick={tout}>{envoi ? "Envoi…" : "Tout envoyer"}</button>
            {!envoi && <button className="btn btn--ghost" onClick={() => setFiles([])}>Vider</button>}
          </div>
          {files.length > 0 && <div className="pap-bar"><div style={{ width: `${Math.round(((ok + ko) / files.length) * 100)}%` }} /></div>}
          <ul className="pj-trash__list pap-files">
            {files.slice(0, 300).map((f, i) => (
              <li key={`${f.name}-${i}`}><span style={{ flex: 1 }}>{f.name}</span>
                <span className="pap-meta">{f.etat === "ok" ? "✔ envoyé" : f.etat === "erreur" ? `✘ ${f.erreur}` : f.etat === "envoi" ? "envoi…" : `${Math.max(1, Math.round(f.size / 1024))} Ko`}</span></li>
            ))}
            {files.length > 300 && <li><span>… et {files.length - 300} autres</span></li>}
          </ul>
          {ok > 0 && <p className="page__sub">Envoyés : Paperless les lit, puis EVA les analyse un par un. Suis l'avancement en haut de la page.</p>}
        </>
      )}
      {!actif && <p className="page__warn">Configure d'abord Paperless (onglet Réglages).</p>}
      <p className="page__sub">Tu peux aussi copier des centaines de fichiers d'un coup dans un dossier surveillé du NAS (onglet Réglages), ou joindre un papier dans la conversation avec « range ça dans mes papiers ».</p>
    </div>
  );
}

function Reglages({ onSaved, setMsg, setError }) {
  const [r, setR] = useState(null);
  const [token, setToken] = useState("");
  const [test, setTest] = useState(null);
  const [nav, setNav] = useState(null);

  const charger = useCallback(async () => { try { setR(await api("/api/papiers/reglages")); } catch (e) { setError(e.message); } }, [setError]);
  useEffect(() => { charger(); }, [charger]);
  const tester = async () => { setTest({ en_cours: true }); try { setTest(await api("/api/papiers/test")); } catch (e) { setTest({ erreur: e.message }); } };
  useEffect(() => { if (r?.paperless_token) tester(); }, [r?.paperless_url]); // eslint-disable-line react-hooks/exhaustive-deps

  async function enregistrer(e) {
    e.preventDefault(); setError(""); setMsg("");
    const champs = {
      paperless_url: r.paperless_url, paperless_public_url: r.paperless_public_url, ollama_model: r.ollama_model,
      dossiers: r.dossiers, apres_import: r.apres_import, analyses_par_passage: +r.analyses_par_passage,
      alert_days: String(r.alert_days), confidence_threshold: +r.confidence_threshold,
    };
    if (token.trim()) champs.paperless_token = token.trim();
    try { setR(await api("/api/papiers/reglages", { method: "PUT", body: JSON.stringify(champs) })); setToken(""); setMsg("Réglages enregistrés."); onSaved(); tester(); }
    catch (err) { setError(err.message); }
  }
  const ouvrir = async (chemin) => { try { setNav(await api(`/api/papiers/dossiers?chemin=${encodeURIComponent(chemin)}`)); } catch (e) { setError(e.message); } };
  const creer = async () => {
    const nom = window.prompt("Nom du nouveau dossier :"); if (!nom) return;
    try { const c = await api("/api/papiers/dossiers", { method: "POST", body: JSON.stringify({ chemin: [nav.chemin, nom].filter(Boolean).join("/") }) }); await ouvrir(c.chemin); } catch (e) { setError(e.message); }
  };
  if (!r) return null;
  const set = (k, v) => setR({ ...r, [k]: v });
  const modeles = test?.modeles_disponibles || [];

  return (
    <form className="card pap-form" onSubmit={enregistrer} data-testid="papiers-reglages">
      <span className="card__label">Paperless (lecture et archivage)</span>
      <label>Adresse vue par EVA<input value={r.paperless_url} onChange={(e) => set("paperless_url", e.target.value)} placeholder="http://host.docker.internal:8002" /></label>
      <label>Adresse pour ouvrir les documents depuis ton navigateur<input value={r.paperless_public_url} onChange={(e) => set("paperless_public_url", e.target.value)} placeholder="http://192.168.1.10:8002" /></label>
      <label>Jeton API<input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={r.paperless_token ? "défini (laisser vide pour le garder)" : "à coller depuis Paperless › Profil › Jeton API"} autoComplete="off" /></label>
      <div className="pj-row">
        <button type="button" className="btn btn--ghost" onClick={tester}>Tester la connexion</button>
        {test && (test.en_cours ? <span className="page__sub">Test…</span> : test.erreur ? <span className="page__warn">{test.erreur}</span> : (
          <span className="page__sub">Paperless : {test.paperless || "—"} · Ollama : {test.ollama || "—"} · modèle : {test.modele === true ? "trouvé" : test.modele === false ? "absent" : "—"}</span>
        ))}
      </div>

      <span className="card__label">Analyse</span>
      <label>Modèle d'analyse (serveur IA)
        {modeles.length ? (
          <select value={r.ollama_model} onChange={(e) => set("ollama_model", e.target.value)}>
            {!modeles.includes(r.ollama_model) && <option value={r.ollama_model}>{r.ollama_model} (absent)</option>}
            {modeles.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        ) : <input value={r.ollama_model} onChange={(e) => set("ollama_model", e.target.value)} />}
      </label>
      <div className="pj-row">
        <button type="button" className="btn btn--ghost" onClick={async () => {
          if (!(await confirmer("Réanalyser tous les papiers avec le modèle choisi ? Les échéances que tu as corrigées ou ajoutées à la main sont gardées."))) return;
          try { const x = await api("/api/papiers/reanalyser", { method: "POST" }); setMsg(`${x.a_refaire} papier(s) seront réanalysés, petit à petit (avancement en haut de la page).`); onSaved(); }
          catch (err) { setError(err.message); }
        }}>Réanalyser tous les papiers</button>
        <span className="page__sub">après un changement de modèle (enregistre d'abord)</span>
      </div>
      <label>Documents analysés par passage, un passage par minute (le serveur IA reste partagé avec la conversation)
        <input type="number" min="1" max="20" value={r.analyses_par_passage} onChange={(e) => set("analyses_par_passage", e.target.value)} style={{ width: 90 }} /></label>
      <label>Alertes, en jours avant la date où il faut agir<input value={String(r.alert_days)} onChange={(e) => set("alert_days", e.target.value)} placeholder="30,7,1,0" /></label>
      <label>Seuil de confiance (en dessous : « à vérifier »)<input type="number" step="0.05" min="0" max="1" value={r.confidence_threshold} onChange={(e) => set("confidence_threshold", e.target.value)} style={{ width: 90 }} /></label>

      <span className="card__label">Dossiers surveillés</span>
      <span className="page__sub">Choisis-les dans <code>{r.racine_nas || r.racine}</code> du NAS. Tu peux y copier des centaines de fichiers d'un coup : EVA les envoie par lots.</span>
      <ul className="pj-trash__list">
        {r.dossiers.map((d) => <li key={d}><span style={{ flex: 1 }}>📁 {d}</span><button type="button" className="btn btn--ghost" onClick={() => set("dossiers", r.dossiers.filter((x) => x !== d))}>Retirer</button></li>)}
        {!r.dossiers.length && <li><span className="page__sub">Aucun : les papiers n'arrivent que par l'onglet Déposer ou la conversation.</span></li>}
      </ul>
      {!nav ? <button type="button" className="btn btn--ghost" onClick={() => ouvrir("")}>Ajouter un dossier…</button> : (
        <div className="pap-nav">
          <div className="pj-row"><b>📂 {nav.chemin || "(racine)"}</b>
            {nav.parent !== null && <button type="button" className="btn btn--ghost" onClick={() => ouvrir(nav.parent)}>↑ Remonter</button>}
            <button type="button" className="btn btn--ghost" onClick={creer}>Nouveau dossier</button>
            <button type="button" className="btn btn--primary" disabled={!nav.chemin || r.dossiers.includes(nav.chemin)} onClick={() => { set("dossiers", [...r.dossiers, nav.chemin]); setNav(null); }}>Surveiller ce dossier</button>
            <button type="button" className="btn btn--ghost" onClick={() => setNav(null)}>Fermer</button>
          </div>
          <ul className="pj-trash__list">{nav.dossiers.map((d) => <li key={d}><button type="button" className="btn btn--ghost" onClick={() => ouvrir([nav.chemin, d].filter(Boolean).join("/"))}>📁 {d}</button></li>)}
            {!nav.dossiers.length && <li><span className="page__sub">Pas de sous-dossier.</span></li>}</ul>
        </div>
      )}
      <fieldset className="pap-radio"><legend>Après l'envoi à Paperless, le fichier déposé est…</legend>
        {[["deplacer", "rangé dans un sous-dossier « _importés » (conseillé)"], ["supprimer", "supprimé (Paperless garde l'original)"], ["laisser", "laissé en place (EVA se souvient qu'il est envoyé)"]].map(([v, t]) => (
          <label key={v}><input type="radio" name="apres" checked={r.apres_import === v} onChange={() => set("apres_import", v)} /> {t}</label>
        ))}
      </fieldset>
      <div className="pj-row"><button className="btn btn--primary" type="submit">Enregistrer</button></div>
    </form>
  );
}
