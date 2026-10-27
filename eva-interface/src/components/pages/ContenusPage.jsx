import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { confirmer } from "../../confirmer";

const ICONES = { youtube: "▶️", instagram: "📸", tiktok: "🎵", twitch: "🟣", facebook: "📘", x: "✖️", linkedin: "💼", blog: "📝", podcast: "🎙️", autre: "✨" };
const jour = (d) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "");

function Editeur({ c, info, onClose, onSave }) {
  const [f, setF] = useState({ ...c });
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const moi = info.moi;
  const save = async () => { setErr(""); try { await onSave(f); onClose(); } catch (e) { setErr(e.message); } };
  const annoncer = async () => {
    setErr(""); setMsg("");
    try { const r = await api(`/api/contenus/${c.id}/annoncer`, { method: "POST", body: JSON.stringify({ salon: info.discord.length === 1 ? "" : f._salon || info.discord[0] }) }); setMsg(`Annoncé sur Discord (#${r.salon}).`); } catch (e) { setErr(e.message); }
  };
  return (
    <div className="dash-overlay" role="dialog" aria-label="Contenu" onClick={onClose}>
      <div className="dash-panel cont-editeur" onClick={(e) => e.stopPropagation()}>
        <div className="dash-header"><b>{c.id ? "Contenu" : "Nouvelle idée"}</b><button className="dash-close" onClick={onClose} aria-label="Fermer">✕</button></div>
        <label className="field"><span>Titre</span><input value={f.titre || ""} onChange={(e) => setF({ ...f, titre: e.target.value })} autoFocus data-testid="cont-titre" /></label>
        <div className="routergrid">
          <label className="field"><span>Étape</span><select value={f.etat} onChange={(e) => setF({ ...f, etat: e.target.value })}>{info.etats.map((e) => <option key={e} value={e}>{info.noms[e]}</option>)}</select></label>
          <label className="field"><span>Date prévue</span><input type="date" value={f.date_prevue || ""} onChange={(e) => setF({ ...f, date_prevue: e.target.value })} /></label>
        </div>
        <div className="cont-plateformes">{info.plateformes.map((p) => (
          <label key={p} className={`question__puce ${f.plateformes?.includes(p) ? "is-on" : ""}`}>
            <input type="checkbox" checked={!!f.plateformes?.includes(p)} onChange={() => setF({ ...f, plateformes: f.plateformes?.includes(p) ? f.plateformes.filter((x) => x !== p) : [...(f.plateformes || []), p] })} /> {ICONES[p]} {p}
          </label>
        ))}</div>
        <label className="field"><span>Notes (plan, script, idées de miniature…)</span><textarea rows={6} value={f.notes || ""} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
        <label className="field"><span>Lien une fois publié</span><input value={f.lien || ""} onChange={(e) => setF({ ...f, lien: e.target.value })} placeholder="https://…" /></label>
        {(!c.id || c.qui === moi) && <label className="checkrow"><input type="checkbox" checked={!!f.partage} onChange={(e) => setF({ ...f, partage: e.target.checked })} /> Partager avec la famille (chaîne commune)</label>}
        <div className="agentform__actions">
          <button className="btn btn--primary" onClick={save} disabled={!f.titre?.trim()} data-testid="cont-enregistrer">Enregistrer</button>
          {c.id && f.etat === "publie" && info.discord.length > 0 && <button className="btn" onClick={annoncer}>📣 Annoncer sur Discord</button>}
          {c.id && c.qui === moi && <button className="btn btn--danger" onClick={async () => { if ((await confirmer("Supprimer ce contenu ?"))) { await api(`/api/contenus/${c.id}`, { method: "DELETE" }); onClose(true); } }}>Supprimer</button>}
        </div>
        {msg && <p className="page__sub">{msg}</p>}
        {err && <p className="page__warn">{err}</p>}
      </div>
    </div>
  );
}

function Calendrier({ items, onOpen }) {
  const [m, setM] = useState(() => new Date().toISOString().slice(0, 7));
  const d0 = new Date(`${m}-01T12:00:00`);
  const decal = (d0.getDay() + 6) % 7;
  const nb = new Date(d0.getFullYear(), d0.getMonth() + 1, 0).getDate();
  const cases = [...Array(decal).fill(null), ...Array.from({ length: nb }, (_, i) => `${m}-${String(i + 1).padStart(2, "0")}`)];
  const parJour = useMemo(() => {
    const o = {};
    for (const c of items) { const d = c.date_publiee || c.date_prevue; if (d) (o[d] = o[d] || []).push(c); }
    return o;
  }, [items]);
  const bouger = (n) => { const d = new Date(`${m}-01T12:00:00`); d.setMonth(d.getMonth() + n); setM(d.toISOString().slice(0, 7)); };
  return (
    <div className="card">
      <div className="pj-row"><button className="btn btn--ghost" onClick={() => bouger(-1)}>‹</button><b style={{ textTransform: "capitalize" }}>{d0.toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}</b><button className="btn btn--ghost" onClick={() => bouger(1)}>›</button></div>
      <div className="cont-cal">
        {["lun", "mar", "mer", "jeu", "ven", "sam", "dim"].map((j) => <span key={j} className="cont-cal__tete">{j}</span>)}
        {cases.map((d, i) => (
          <div key={i} className={`cont-cal__jour ${d === new Date().toISOString().slice(0, 10) ? "is-auj" : ""}`}>
            {d && <span className="cont-cal__num">{Number(d.slice(8))}</span>}
            {(parJour[d] || []).map((c) => <button key={c.id} type="button" className={`cont-puce is-${c.etat}`} onClick={() => onOpen(c)}>{c.plateformes.map((p) => ICONES[p]).join("")} {c.titre}</button>)}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ContenusPage() {
  const [info, setInfo] = useState(null); const [ouvert, setOuvert] = useState(null); const [vue, setVue] = useState("tableau");
  const [insta, setInsta] = useState(null); const [err, setErr] = useState("");
  const charger = useCallback(() => api("/api/contenus").then(setInfo).catch((e) => setErr(e.message)), []);
  useEffect(() => { charger(); }, [charger]);
  const sauver = async (f) => {
    const corps = { titre: f.titre, etat: f.etat, plateformes: f.plateformes || [], date_prevue: f.date_prevue || null, notes: f.notes || "", lien: f.lien || "" };
    if (!f.id || f.qui === info.moi) corps.partage = !!f.partage;
    await api(f.id ? `/api/contenus/${f.id}` : "/api/contenus", { method: f.id ? "PATCH" : "POST", body: JSON.stringify(corps) });
    charger();
  };
  const avancer = async (c, sens) => {
    const i = info.etats.indexOf(c.etat) + sens;
    if (i < 0 || i >= info.etats.length) return;
    await api(`/api/contenus/${c.id}`, { method: "PATCH", body: JSON.stringify({ etat: info.etats[i] }) });
    charger();
  };
  if (!info) return <section className="page"><div className="page__body">{err ? <p className="page__warn">{err}</p> : <p className="dash-loading">Chargement…</p>}</div></section>;
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section className="page" data-testid="contenus-page">
      <header className="page__header"><h1>Contenus</h1><span className="page__sub">De l'idée à la publication. Dis aussi à EVA : « note une idée de vidéo : … », « qu'est-ce que je publie cette semaine ? »</span></header>
      <div className="page__body">
        <div className="pj-row">
          <div className="pj-sbx__tabs">{[["tableau", "Tableau"], ["calendrier", "Calendrier"]].map(([k, l]) => <button key={k} className={vue === k ? "is-on" : ""} onClick={() => setVue(k)}>{l}</button>)}</div>
          <button className="btn btn--primary" onClick={() => setOuvert({ titre: "", etat: "idee", plateformes: [], partage: false })} data-testid="cont-nouveau">+ Idée</button>
          {info.instagram && <button className="btn" onClick={() => api("/api/contenus/instagram").then(setInsta).catch((e) => setErr(e.message))}>📸 Stats Instagram</button>}
        </div>
        {insta && <p className="page__sub">📸 @{insta.compte} : <b>{insta.abonnes}</b> abonnés, {insta.publications} publications{insta.dernieres?.[0] ? ` · dernière : ${insta.dernieres[0].j_aime} ❤️ ${insta.dernieres[0].commentaires} 💬` : ""}</p>}
        {err && <p className="page__warn">{err}</p>}
        {vue === "tableau" ? (
          <div className="cont-kanban">
            {info.etats.map((e) => {
              const lst = info.contenus.filter((c) => c.etat === e);
              return (
                <div key={e} className="cont-col" data-testid={`cont-col-${e}`}>
                  <div className="cont-col__tete"><b>{info.noms[e]}</b><span>{lst.length}</span></div>
                  {lst.map((c) => (
                    <div key={c.id} className="cont-carte" onClick={() => setOuvert(c)}>
                      <div className="cont-carte__titre">{c.titre}</div>
                      <div className="cont-carte__meta">
                        <span>{c.plateformes.map((p) => ICONES[p]).join(" ")}</span>
                        {(c.date_publiee || c.date_prevue) && <span className={!c.date_publiee && c.date_prevue < today ? "page__warn" : ""}>{jour(c.date_publiee || c.date_prevue)}</span>}
                        {c.partage && <span title="Partagé avec la famille">👪</span>}
                      </div>
                      <div className="cont-carte__fleches" onClick={(ev) => ev.stopPropagation()}>
                        <button className="btn btn--ghost" disabled={e === info.etats[0]} onClick={() => avancer(c, -1)} aria-label="Étape précédente">‹</button>
                        <button className="btn btn--ghost" disabled={e === info.etats[info.etats.length - 1]} onClick={() => avancer(c, 1)} aria-label="Étape suivante" data-testid="cont-avancer">›</button>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        ) : <Calendrier items={info.contenus} onOpen={setOuvert} />}
      </div>
      {ouvert && <Editeur c={ouvert} info={info} onClose={(suppr) => { setOuvert(null); if (suppr) charger(); }} onSave={sauver} />}
    </section>
  );
}
