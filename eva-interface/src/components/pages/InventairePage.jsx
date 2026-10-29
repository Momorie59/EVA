import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { confirmer } from "../../confirmer";

const VIDE = { nom: "", emplacement: "", quantite: 1, notes: "", prive: false };
const jj = (iso) => (iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "");

// Inventaire de la maison et prêts : « où est la perceuse ? », « j'ai prêté la tondeuse à Paul » (à la voix ou ici).
export default function InventairePage() {
  const [d, setD] = useState(null); const [q, setQ] = useState(""); const [err, setErr] = useState(""); const [msg, setMsg] = useState("");
  const [f, setF] = useState(null); const [pret, setPret] = useState(null);
  const charger = useCallback(() => api(`/api/inventaire?q=${encodeURIComponent(q)}`).then((x) => { setD(x); setErr(""); })
    .catch((e) => setErr(e.status === 404 ? "Le module Inventaire est coupé : Paramètres › Modules." : e.message)), [q]);
  useEffect(() => { const t = setTimeout(charger, 200); return () => clearTimeout(t); }, [charger]);
  const agir = (p, ok) => p.then((r) => { if (ok) setMsg(typeof ok === "function" ? ok(r) : ok); charger(); return r; }).catch((e) => setErr(e.message));
  const enregistrer = (e) => { e.preventDefault(); agir(api("/api/inventaire", { method: "POST", body: JSON.stringify({ ...f, quantite: Number(f.quantite) || 0 }) }), (r) => `✔ ${r.nom} : ${r.emplacement || "emplacement non noté"}`).then(() => setF(null)); };
  const preter = (e) => { e.preventDefault(); agir(api("/api/inventaire/prets", { method: "POST", body: JSON.stringify(pret) }), (r) => `✔ ${r.objet} ${r.sens === "prete" ? "prêté à" : "emprunté à"} ${r.personne}`).then(() => setPret(null)); };
  const rendu = (p) => agir(api(`/api/inventaire/prets/${p.id}/rendu`, { method: "POST" }), `✔ ${p.objet} rendu.`);
  const retirer = async (o) => { if (await confirmer(`Retirer « ${o.nom} » de l'inventaire ?`)) agir(api(`/api/inventaire/${o.id}`, { method: "DELETE" }), "Retiré."); };

  const groupes = {};
  for (const o of d?.objets || []) (groupes[o.emplacement.split(" › ")[0] || "Sans emplacement"] ||= []).push(o);
  const prets = d?.prets || [];
  return (
    <section className="page" data-testid="inventaire-page">
      <header className="page__header"><h1>Inventaire</h1><span className="page__sub">Où sont rangées les affaires, et à qui on les a prêtées. À la voix : « où est la perceuse ? », « la perceuse est dans le garage, sur l'établi », « j'ai prêté la tondeuse à Paul ».</span></header>
      <div className="page__body">
        {err && <p className="page__warn" role="alert">{err}</p>}
        {msg && <p className="page__sub" role="status">{msg}</p>}
        <div className="pj-row">
          <input className="convs__search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Chercher : perceuse, piles, câble HDMI…" aria-label="Chercher un objet" data-testid="inv-q" style={{ flex: 1 }} />
          <button className="btn btn--primary" onClick={() => setF({ ...VIDE })} data-testid="inv-ajouter">+ Objet</button>
          <button className="btn" onClick={() => setPret({ objet: "", personne: "", sens: "prete", retour: "" })} data-testid="inv-preter">🤝 Prêt</button>
        </div>
        {f && (
          <form className="card agentform" onSubmit={enregistrer} data-testid="inv-form">
            <div className="routergrid">
              <label className="field"><span>Objet</span><input value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} autoFocus required data-testid="inv-nom" /></label>
              <label className="field"><span>Rangé où (du plus grand au plus petit)</span><input value={f.emplacement} onChange={(e) => setF({ ...f, emplacement: e.target.value })} placeholder="Garage › Établi › Tiroir 2" list="inv-lieux" data-testid="inv-lieu" /></label>
              <label className="field"><span>Quantité</span><input type="number" min="0" value={f.quantite} onChange={(e) => setF({ ...f, quantite: e.target.value })} /></label>
              <label className="field"><span>Notes</span><input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="modèle, taille, piles…" /></label>
            </div>
            <datalist id="inv-lieux">{(d?.lieux || []).map((l) => <option key={l} value={l} />)}</datalist>
            <label className="page__sub"><input type="checkbox" checked={f.prive} onChange={(e) => setF({ ...f, prive: e.target.checked })} /> 🔒 Privé (moi seul le vois)</label>
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" data-testid="inv-ok">Enregistrer</button><button className="btn" type="button" onClick={() => setF(null)}>Annuler</button></div>
          </form>
        )}
        {pret && (
          <form className="card agentform" onSubmit={preter} data-testid="inv-pret-form">
            <div className="routergrid">
              <label className="field"><span>Sens</span><select value={pret.sens} onChange={(e) => setPret({ ...pret, sens: e.target.value })}><option value="prete">J'ai prêté</option><option value="emprunte">On m'a prêté</option></select></label>
              <label className="field"><span>Objet</span><input value={pret.objet} onChange={(e) => setPret({ ...pret, objet: e.target.value })} required list="inv-objets" data-testid="inv-pret-objet" /></label>
              <label className="field"><span>{pret.sens === "prete" ? "À qui" : "Par qui"}</span><input value={pret.personne} onChange={(e) => setPret({ ...pret, personne: e.target.value })} required data-testid="inv-pret-qui" /></label>
              <label className="field"><span>Retour prévu (facultatif)</span><input type="date" value={pret.retour} onChange={(e) => setPret({ ...pret, retour: e.target.value })} /></label>
            </div>
            <datalist id="inv-objets">{(d?.objets || []).map((o) => <option key={o.id} value={o.nom} />)}</datalist>
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" data-testid="inv-pret-ok">Noter le prêt</button><button className="btn" type="button" onClick={() => setPret(null)}>Annuler</button></div>
          </form>
        )}
        {prets.length > 0 && (
          <div className="card" data-testid="inv-prets">
            <span className="card__label">Prêts en cours ({prets.length})</span>
            <ul className="pj-trash__list">{prets.map((p) => (
              <li key={p.id} className="pj-row"><span>{p.sens === "prete" ? "➡️" : "⬅️"} <b>{p.objet}</b> {p.sens === "prete" ? "prêté à" : "emprunté à"} <b>{p.personne}</b> depuis le {jj(p.depuis)}
                {p.retour_prevu && <span className={p.en_retard ? "page__warn" : "page__sub"}> · retour {p.en_retard ? "prévu le" : "le"} {jj(p.retour_prevu)}{p.en_retard ? " — en retard" : ""}</span>}</span>
                <button className="btn btn--ghost" onClick={() => rendu(p)}>Rendu ✔</button></li>
            ))}</ul>
          </div>
        )}
        {!d ? (!err && <p className="page__sub">Chargement…</p>) : d.objets.length === 0 ? (
          <p className="dash-empty">{q ? "Rien trouvé." : "Inventaire vide : ajoute un objet, ou dis à EVA « la perceuse est dans le garage »."}</p>
        ) : (
          <div className="pj-grid">
            {Object.entries(groupes).map(([lieu, objets]) => (
              <div key={lieu} className="card">
                <span className="card__label">{lieu} ({objets.length})</span>
                <ul className="pj-trash__list">{objets.map((o) => (
                  <li key={o.id} className="pj-row"><span><b>{o.nom}</b>{o.quantite !== 1 ? ` ×${o.quantite}` : ""}{o.prive ? " 🔒" : ""}
                    <small className="page__sub" style={{ display: "block" }}>{o.emplacement.split(" › ").slice(1).join(" › ") || o.emplacement}{o.notes ? ` · ${o.notes}` : ""}{o.pret ? ` · ${o.pret.sens === "prete" ? "prêté à" : "emprunté à"} ${o.pret.personne}` : ""}</small></span>
                    <span className="sat-actions"><button className="btn btn--ghost" onClick={() => setF({ ...o })}>✏️</button><button className="btn btn--ghost" onClick={() => retirer(o)}>🗑️</button></span></li>
                ))}</ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
