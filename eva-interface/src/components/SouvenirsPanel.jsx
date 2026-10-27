import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

// Ce qu'EVA retient de moi : préférences, faits, décisions. Tout est visible, modifiable, désactivable et effaçable.
export default function SouvenirsPanel() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [texte, setTexte] = useState("");
  const [kind, setKind] = useState("");
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => api("/api/memoire").then((x) => { setD(x); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (d?.reprise?.etat !== "en cours") return undefined; const t = setTimeout(load, 4000); return () => clearTimeout(t); }, [d, load]);

  const run = async (fn) => { setError(""); try { await fn(); await load(); } catch (e) { setError(e.message); } };
  if (!d) return error ? <p className="page__warn">{error}</p> : <p className="card__hint">Chargement…</p>;

  const add = (e) => { e.preventDefault(); run(async () => { await api("/api/memoire", { method: "POST", body: JSON.stringify({ texte, kind: kind || null }) }); setTexte(""); }); };
  const patch = (s, body) => run(() => api(`/api/memoire/${s.id}`, { method: "PATCH", body: JSON.stringify(body) }));
  const del = async (s) => { if ((await confirmer(`Effacer « ${s.texte} » ?`))) run(() => api(`/api/memoire/${s.id}`, { method: "DELETE" })); };
  const saveEdit = () => run(async () => { await api(`/api/memoire/${edit.id}`, { method: "PATCH", body: JSON.stringify({ texte: edit.texte, kind: edit.kind }) }); setEdit(null); });

  return (
    <div data-testid="souvenirs">
      <div className="card">
        <label className="access__f">
          <input type="checkbox" checked={d.actif} onChange={() => run(() => api("/api/memoire/reglage", { method: "PUT", body: JSON.stringify({ actif: !d.actif }) }))} data-testid="memoire-actif" />
          <b>Mémoire allumée</b>
        </label>
        <p className="card__hint">EVA retient seulement ce que tu lui demandes (« retiens que… ») ou ce qu'elle te propose de retenir, affiché dans la conversation. Ces souvenirs ne sont qu'à toi : personne d'autre ne les voit. « Oublie que… » ou la corbeille ci-dessous les effacent. Mémoire coupée : EVA n'en utilise ni n'en ajoute aucun.</p>
        <form className="schedrow" onSubmit={add}>
          <input value={texte} onChange={(e) => setTexte(e.target.value)} placeholder="Ex. Je préfère les réponses courtes" maxLength={500} style={{ flex: 1 }} data-testid="souvenir-texte" />
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Sorte : automatique</option>
            {Object.entries(d.sortes).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <button className="btn btn--primary" type="submit" disabled={texte.trim().length < 3} data-testid="souvenir-add">Retenir</button>
        </form>
      </div>
      <div className="card">
        <span className="card__label">Anciennes conversations</span>
        <p className="card__hint">EVA relit ce que tu as dit de toi dans tes conversations passées et en garde les faits durables (jamais de santé, d'argent, de religion ni de mots de passe). Tu peux tout corriger ou effacer ensuite.</p>
        <button className="btn" disabled={!d.actif || d.reprise?.etat === "en cours"} onClick={() => run(() => api("/api/memoire/reprendre", { method: "POST" }))} data-testid="memoire-reprendre">Relire mes conversations</button>
        {d.reprise && <p className="card__hint" data-testid="memoire-reprise">{d.reprise.etat === "en cours" ? `Lecture en cours… (${d.reprise.lus} passage(s), ${d.reprise.retenus} souvenir(s) trouvé(s))` : d.reprise.etat === "fini" ? `Terminé : ${d.reprise.retenus} souvenir(s) retenu(s).` : "La lecture a échoué (serveur IA indisponible ?)."}</p>}
      </div>
      {d.souvenirs.length === 0 && <p className="card__hint">EVA n'a encore rien retenu de toi.</p>}
      {Object.entries(d.sortes).map(([k, lab]) => {
        const ls = d.souvenirs.filter((s) => s.kind === k);
        if (!ls.length) return null;
        return (
          <div key={k} className="card">
            <span className="card__label">{lab}s</span>
            {ls.map((s) => (
              <div key={s.id} className="schedrow" style={{ opacity: s.actif ? 1 : 0.5 }} data-testid="souvenir">
                {edit?.id === s.id ? (
                  <>
                    <input value={edit.texte} onChange={(e) => setEdit({ ...edit, texte: e.target.value })} maxLength={500} style={{ flex: 1 }} />
                    <select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>
                      {Object.entries(d.sortes).map(([kk, l]) => <option key={kk} value={kk}>{l}</option>)}
                    </select>
                    <button className="btn btn--primary" onClick={saveEdit}>Enregistrer</button>
                    <button className="btn btn--ghost" onClick={() => setEdit(null)}>Annuler</button>
                  </>
                ) : (
                  <>
                    <span style={{ flex: 1 }}>{s.texte} {s.source === "eva" && <small className="card__hint">(proposé par EVA)</small>}</span>
                    <label className="access__f" title="Un souvenir désactivé est gardé mais n'est plus utilisé">
                      <input type="checkbox" checked={s.actif} onChange={() => patch(s, { actif: !s.actif })} />actif
                    </label>
                    <button className="btn btn--ghost" onClick={() => setEdit({ id: s.id, texte: s.texte, kind: s.kind })}>Modifier</button>
                    <button className="btn btn--ghost" onClick={() => del(s)} aria-label="Effacer">🗑️</button>
                  </>
                )}
              </div>
            ))}
          </div>
        );
      })}
      {error && <p className="page__warn" role="alert">{error}</p>}
    </div>
  );
}
