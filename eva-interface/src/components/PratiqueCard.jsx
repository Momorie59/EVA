import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "./AuthGate";

// Paramètres › Services connectés › Infos pratiques : poubelles, vacances, carburants, actualités (et un aperçu de chacun).
export default function PratiqueCard() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const [r, setR] = useState(null); const [err, setErr] = useState(""); const [ok, setOk] = useState(""); const [apercu, setApercu] = useState({});
  useEffect(() => { api("/api/pratique/reglages").then(setR).catch((e) => setErr(e.status === 404 ? "" : e.message)); }, []);
  if (!r) return err ? <p className="page__warn">{err}</p> : null;
  const bacs = r.poubelles.bacs;
  const setBacs = (b) => setR({ ...r, poubelles: { ...r.poubelles, bacs: b } });
  const enregistrer = () => {
    setErr(""); setOk("");
    api("/api/pratique/reglages", { method: "PUT", body: JSON.stringify({ zone: r.zone, region: r.region, carburant: r.carburant, poubelles: r.poubelles, actu: r.actu }) })
      .then((x) => { setR({ ...r, ...x }); setOk("Enregistré."); }).catch((e) => setErr(e.message));
  };
  const voir = (quoi) => api(`/api/pratique/apercu/${quoi}`).then((x) => setApercu((a) => ({ ...a, [quoi]: x.error ? `⚠️ ${x.error}` : x.phrase }))).catch((e) => setApercu((a) => ({ ...a, [quoi]: `⚠️ ${e.message}` })));
  const Apercu = ({ quoi }) => (
    <span className="pj-row"><button type="button" className="btn btn--ghost" onClick={() => voir(quoi)}>Essayer</button>{apercu[quoi] && <small className="page__sub">{apercu[quoi]}</small>}</span>
  );
  return (
    <div className="card" data-testid="pratique-card">
      <span className="card__label">Infos pratiques</span>
      <p className="card__hint">EVA répond à « quelle poubelle je sors ? », « c'est quand les vacances ? », « le prix du gazole ? », « les titres du jour », « un jour comme aujourd'hui ». Données publiques (Éducation nationale, ministère de l'Économie, Wikipédia, ton journal).</p>

      <span className="card__label" style={{ marginTop: 10 }}>🗑 Poubelles</span>
      <p className="card__hint">Les jours comme les écrit ta commune : « lundi et jeudi », « mercredi semaines paires », « 1er et 3e vendredi du mois ».</p>
      {bacs.map((b, i) => (
        <div key={i} className="pj-row">
          <select value={b.bac} disabled={!admin} onChange={(e) => setBacs(bacs.map((x, j) => (j === i ? { ...x, bac: e.target.value } : x)))}>
            {Object.entries(r.bacs_possibles).map(([k, l]) => <option key={k} value={k}>{l.replace(/^(les|le) /, "")}</option>)}
          </select>
          <input value={b.jours} disabled={!admin} onChange={(e) => setBacs(bacs.map((x, j) => (j === i ? { ...x, jours: e.target.value } : x)))} placeholder="lundi et jeudi" data-testid={`bac-jours-${i}`} />
          {admin && <button type="button" className="btn btn--ghost" onClick={() => setBacs(bacs.filter((_, j) => j !== i))}>✕</button>}
        </div>
      ))}
      {admin && bacs.length < 8 && <button type="button" className="btn btn--ghost" onClick={() => setBacs([...bacs, { bac: "menager", jours: "" }])} data-testid="bac-ajouter">+ Bac</button>}
      <label className="page__sub"><input type="checkbox" checked={r.poubelles.veille} disabled={!admin} onChange={(e) => setR({ ...r, poubelles: { ...r.poubelles, veille: e.target.checked } })} /> Prévenir la veille au soir à
        <select value={r.poubelles.heure_veille} disabled={!admin} onChange={(e) => setR({ ...r, poubelles: { ...r.poubelles, heure_veille: Number(e.target.value) } })}>{[17, 18, 19, 20, 21, 22].map((h) => <option key={h} value={h}>{h} h</option>)}</select>
        (écran, Telegram et satellites)</label>
      <Apercu quoi="poubelles" />

      <span className="card__label" style={{ marginTop: 10 }}>🏖 Vacances scolaires et jours fériés</span>
      <div className="pj-row">
        <select value={r.zone} disabled={!admin} onChange={(e) => setR({ ...r, zone: e.target.value })} data-testid="pratique-zone">{["A", "B", "C", "Corse"].map((z) => <option key={z} value={z}>{z === "Corse" ? "Corse" : `Zone ${z}`}</option>)}</select>
        <select value={r.region} disabled={!admin} onChange={(e) => setR({ ...r, region: e.target.value })}><option value="metropole">Métropole</option><option value="alsace-moselle">Alsace-Moselle</option></select>
        <Apercu quoi="vacances" />
      </div>

      <span className="card__label" style={{ marginTop: 10 }}>⛽ Carburants</span>
      <div className="pj-row">
        <input value={r.carburant.lieu} disabled={!admin} onChange={(e) => setR({ ...r, carburant: { ...r.carburant, lieu: e.target.value } })} placeholder="Commune ou code postal" />
        <select value={r.carburant.type} disabled={!admin} onChange={(e) => setR({ ...r, carburant: { ...r.carburant, type: e.target.value } })}>{Object.entries(r.carburants).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <Apercu quoi="carburants" />
      </div>

      <span className="card__label" style={{ marginTop: 10 }}>📰 Actualités</span>
      <div className="pj-row">
        <input value={r.actu.url} disabled={!admin} onChange={(e) => setR({ ...r, actu: { ...r.actu, url: e.target.value } })} placeholder="https://www.franceinfo.fr/titres.rss" style={{ flex: 1 }} />
        <Apercu quoi="actu" />
      </div>
      <p className="card__hint">Flux RSS de ton journal préféré (Le Monde, Le Progrès, Ouest-France…) : utilisé pour « les titres du jour » et le point du matin, à la place d'une recherche web.</p>

      <span className="card__label" style={{ marginTop: 10 }}>📅 Éphéméride</span>
      <Apercu quoi="ephemeride" />

      {admin && <div className="agentform__actions"><button className="btn btn--primary" onClick={enregistrer} data-testid="pratique-ok">Enregistrer</button></div>}
      {ok && <p className="page__sub">{ok}</p>}
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}
