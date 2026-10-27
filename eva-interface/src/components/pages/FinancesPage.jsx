import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { CORE_URL, authHeaders } from "../../urls";
import { confirmer } from "../../confirmer";

const eur = (v) => (v ?? 0).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
const moisCourant = () => new Date().toISOString().slice(0, 7);
const nomMois = (m) => new Date(`${m}-01T12:00:00`).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
const decaler = (m, n) => { const d = new Date(`${m}-01T12:00:00`); d.setMonth(d.getMonth() + n); return d.toISOString().slice(0, 7); };

function Tableau({ mois, tb, onCategorie }) {
  const maxEvol = Math.max(1, ...tb.evolution.flatMap((e) => [e.revenus, e.depenses]));
  const maxCat = Math.max(1, ...tb.par_categorie.map((c) => Math.max(c.depense, c.budget || 0)));
  return (
    <div className="fin-grille">
      <div className="fin-tuiles">
        <div className="fin-tuile"><span>Revenus</span><b className="is-plus">{eur(tb.revenus)}</b></div>
        <div className="fin-tuile"><span>Dépenses</span><b className="is-moins">{eur(tb.depenses)}</b></div>
        <div className="fin-tuile"><span>Reste du mois</span><b className={tb.solde_mois >= 0 ? "is-plus" : "is-moins"}>{eur(tb.solde_mois)}</b></div>
        <div className="fin-tuile"><span>Sur les comptes</span><b>{eur(tb.comptes.reduce((s, c) => s + c.solde, 0))}</b></div>
      </div>
      <div className="card fin-carte">
        <h3>Dépenses par catégorie — {nomMois(mois)}</h3>
        {tb.depassements.length > 0 && <p className="page__warn">Budget dépassé : {tb.depassements.join(", ")}</p>}
        {tb.par_categorie.length ? tb.par_categorie.map((c) => (
          <button type="button" key={c.categorie} className="fin-cat" onClick={() => onCategorie(c.categorie)} title="Voir les opérations">
            <span className="fin-cat__nom">{c.categorie}</span>
            <span className="fin-cat__barre">
              <i className={c.budget && c.depense > c.budget ? "is-depasse" : ""} style={{ width: `${(c.depense / maxCat) * 100}%` }} />
              {c.budget ? <em style={{ left: `${(c.budget / maxCat) * 100}%` }} title={`Budget ${eur(c.budget)}`} /> : null}
            </span>
            <span className="fin-cat__val">{eur(c.depense)}{c.budget ? <small> / {eur(c.budget)}</small> : null}</span>
          </button>
        )) : <p className="page__sub">Aucune dépense ce mois-ci. Importe un relevé dans l'onglet « Comptes ».</p>}
      </div>
      <div className="card fin-carte">
        <h3>6 derniers mois</h3>
        <div className="fin-evol">
          {tb.evolution.map((e) => (
            <div key={e.mois} className="fin-evol__mois" title={`${nomMois(e.mois)} : +${eur(e.revenus)} / −${eur(e.depenses)}`}>
              <div className="fin-evol__barres"><i className="is-plus" style={{ height: `${(e.revenus / maxEvol) * 100}%` }} /><i className="is-moins" style={{ height: `${(e.depenses / maxEvol) * 100}%` }} /></div>
              <span>{new Date(`${e.mois}-01T12:00:00`).toLocaleDateString("fr-FR", { month: "short" })}</span>
            </div>
          ))}
        </div>
        <p className="page__sub"><span className="fin-legende is-plus" /> revenus · <span className="fin-legende is-moins" /> dépenses</p>
        <h3>Plus grosses dépenses</h3>
        <ul className="fin-liste">{tb.plus_grosses.map((o, i) => <li key={i}><span>{new Date(o.jour).toLocaleDateString("fr-FR")} · {o.libelle}</span><b>{eur(o.montant)}</b></li>)}</ul>
      </div>
    </div>
  );
}

function Operations({ mois, categories, filtre, setFiltre }) {
  const [ops, setOps] = useState([]); const [q, setQ] = useState(""); const [msg, setMsg] = useState("");
  const charger = useCallback(() => api(`/api/finances/operations?mois=${mois}&categorie=${encodeURIComponent(filtre)}&q=${encodeURIComponent(q)}`).then((d) => setOps(d.operations)).catch(() => {}), [mois, filtre, q]);
  useEffect(() => { charger(); }, [charger]);
  const changer = async (o, categorie) => {
    const r = await api(`/api/finances/operations/${o.id}`, { method: "PATCH", body: JSON.stringify({ categorie }) });
    setMsg(r.semblables ? `Catégorie retenue : ${r.semblables} opération(s) semblable(s) mise(s) à jour, et les prochaines suivront.` : "Catégorie retenue pour les prochaines opérations semblables.");
    charger();
  };
  return (
    <div className="card fin-carte">
      <div className="pj-row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Chercher un libellé…" />
        <select value={filtre} onChange={(e) => setFiltre(e.target.value)}><option value="">Toutes les catégories</option>{categories.map((c) => <option key={c}>{c}</option>)}</select>
        <span className="page__sub">{ops.length} opération(s) · {eur(ops.reduce((s, o) => s + o.montant, 0))}</span>
      </div>
      {msg && <p className="page__sub">{msg}</p>}
      <table className="fin-table" data-testid="fin-operations">
        <tbody>{ops.map((o) => (
          <tr key={o.id}>
            <td>{new Date(o.jour).toLocaleDateString("fr-FR")}</td>
            <td className="fin-table__lib">{o.libelle}</td>
            <td><select value={o.categorie} onChange={(e) => changer(o, e.target.value)}>{categories.map((c) => <option key={c}>{c}</option>)}</select></td>
            <td className={o.montant < 0 ? "is-moins" : "is-plus"}>{eur(o.montant)}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Comptes({ onChange }) {
  const [lst, setLst] = useState([]); const [f, setF] = useState({ nom: "", solde_initial: "" }); const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const fichier = useRef(null); const cible = useRef(null);
  const charger = () => api("/api/finances/comptes").then((d) => setLst(d.comptes)).catch(() => {});
  useEffect(() => { charger(); }, []);
  const importer = async (e) => {
    const fi = e.target.files?.[0]; e.target.value = "";
    if (!fi) return;
    setErr(""); setMsg("Import en cours…");
    try {
      const res = await fetch(`${CORE_URL}/api/finances/comptes/${cible.current}/import?nom=${encodeURIComponent(fi.name)}`, { method: "POST", headers: authHeaders(), body: fi });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || `Erreur ${res.status}`);
      setMsg(`${d.ajoutees} opération(s) ajoutée(s)${d.deja_la ? `, ${d.deja_la} déjà présente(s)` : ""}.`); charger(); onChange();
    } catch (x) { setErr(x.message); setMsg(""); }
  };
  return (
    <div className="card fin-carte">
      <p className="page__sub">Télécharge tes relevés depuis l'espace de ta banque au format <b>CSV</b> ou <b>OFX</b> (souvent « Exporter / Télécharger les opérations »), puis importe-les ici. Rien n'est envoyé à l'extérieur ; une opération déjà importée n'est jamais doublée.</p>
      <input ref={fichier} type="file" accept=".csv,.ofx,.qfx,.txt" hidden onChange={importer} />
      {lst.map((c) => (
        <div key={c.id} className="pj-row fin-compte">
          <span>🏦 <b>{c.nom}</b> · solde estimé <b>{eur(c.solde)}</b> <span className="page__sub">({c.operations} op.{c.dernier ? `, jusqu'au ${new Date(c.dernier).toLocaleDateString("fr-FR")}` : ""})</span></span>
          <button className="btn btn--primary" onClick={() => { cible.current = c.id; fichier.current?.click(); }} data-testid="fin-importer">Importer un relevé</button>
          <button className="btn btn--ghost" onClick={async () => { const s = window.prompt("Solde au début des opérations importées (€) :", String(c.solde_initial)); if (s !== null) { await api(`/api/finances/comptes/${c.id}`, { method: "PATCH", body: JSON.stringify({ solde_initial: s }) }); charger(); onChange(); } }}>Solde de départ</button>
          <button className="btn btn--danger" onClick={async () => { if ((await confirmer(`Supprimer « ${c.nom} » et toutes ses opérations ?`))) { await api(`/api/finances/comptes/${c.id}`, { method: "DELETE" }); charger(); onChange(); } }}>Supprimer</button>
        </div>
      ))}
      <form className="pj-row" onSubmit={async (e) => { e.preventDefault(); try { await api("/api/finances/comptes", { method: "POST", body: JSON.stringify(f) }); setF({ nom: "", solde_initial: "" }); charger(); } catch (x) { setErr(x.message); } }}>
        <input value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} placeholder="Nom du compte (ex. Compte courant)" data-testid="fin-nom" />
        <input value={f.solde_initial} onChange={(e) => setF({ ...f, solde_initial: e.target.value })} placeholder="Solde de départ (€)" inputMode="decimal" />
        <button className="btn" disabled={!f.nom.trim()}>Ajouter le compte</button>
      </form>
      {msg && <p className="page__sub" data-testid="fin-msg">{msg}</p>}
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}

function Budgets({ categories, onChange }) {
  const [b, setB] = useState({});
  useEffect(() => { api("/api/finances/budgets").then((d) => setB(d.budgets)).catch(() => {}); }, []);
  const regler = async (categorie, montant) => { const d = await api("/api/finances/budgets", { method: "PUT", body: JSON.stringify({ categorie, montant }) }); setB(d.budgets); onChange(); };
  return (
    <div className="card fin-carte">
      <p className="page__sub">Un plafond par mois et par catégorie (vide = pas de budget). EVA te le rappelle dans le tableau de bord et quand tu lui demandes où tu en es.</p>
      <div className="fin-budgets">{categories.filter((c) => !["Revenus", "Virements internes", "Épargne"].includes(c)).map((c) => (
        <label key={c} className="field"><span>{c}</span>
          <input defaultValue={b[c] ?? ""} key={`${c}-${b[c]}`} inputMode="decimal" placeholder="—" onBlur={(e) => { if ((e.target.value || "") !== String(b[c] ?? "")) regler(c, e.target.value); }} />
        </label>
      ))}</div>
    </div>
  );
}

export default function FinancesPage() {
  const [mois, setMois] = useState(moisCourant());
  const [tab, setTab] = useState("tableau");
  const [tb, setTb] = useState(null); const [err, setErr] = useState("");
  const [filtre, setFiltre] = useState("");
  const charger = useCallback(() => api(`/api/finances/tableau?mois=${mois}`).then(setTb).catch((e) => setErr(e.message)), [mois]);
  useEffect(() => { charger(); }, [charger]);
  return (
    <section className="page" data-testid="finances-page">
      <header className="page__header"><h1>Finances</h1><span className="page__sub">🔒 Privé : toi seul vois tes comptes. Demande aussi à EVA : « combien j'ai dépensé en restaurants ce mois-ci ? »</span></header>
      <div className="page__body">
        <div className="pj-row fin-barre">
          <div className="pj-sbx__tabs">{[["tableau", "Tableau de bord"], ["operations", "Opérations"], ["comptes", "Comptes & import"], ["budgets", "Budgets"]].map(([k, l]) => <button key={k} className={tab === k ? "is-on" : ""} onClick={() => setTab(k)} data-testid={`fin-tab-${k}`}>{l}</button>)}</div>
          <span className="fin-mois"><button className="btn btn--ghost" onClick={() => setMois(decaler(mois, -1))}>‹</button><b>{nomMois(mois)}</b><button className="btn btn--ghost" onClick={() => setMois(decaler(mois, 1))} disabled={mois >= moisCourant()}>›</button></span>
        </div>
        {err && <p className="page__warn">{err}</p>}
        {tb && tab === "tableau" && <Tableau mois={mois} tb={tb} onCategorie={(c) => { setFiltre(c); setTab("operations"); }} />}
        {tb && tab === "operations" && <Operations mois={mois} categories={tb.categories} filtre={filtre} setFiltre={setFiltre} />}
        {tab === "comptes" && <Comptes onChange={charger} />}
        {tb && tab === "budgets" && <Budgets categories={tb.categories} onChange={charger} />}
      </div>
    </section>
  );
}
