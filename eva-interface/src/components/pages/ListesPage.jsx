import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { confirmer } from "../../confirmer";

const RAYONS = ["Fruits et légumes", "Boulangerie", "Boucherie, poisson", "Crèmerie, œufs", "Frais", "Épicerie salée", "Épicerie sucrée",
  "Surgelés", "Boissons", "Bébé", "Hygiène, beauté", "Entretien, maison", "Animaux", "Divers"];

// Listes (courses, à faire…) : EVA les remplit à la voix (« ajoute du lait à la liste de courses »), on les coche ici, on peut les imprimer.
export default function ListesPage() {
  const [lists, setLists] = useState([]);
  const [cur, setCur] = useState(null);
  const [data, setData] = useState(null);
  const [text, setText] = useState("");
  const [newName, setNewName] = useState("");
  const [newPrive, setNewPrive] = useState(false);
  const [parRayon, setParRayon] = useState(() => { try { return localStorage.getItem("eva.listes.rayon") !== "0"; } catch { return true; } });
  const [rectoVerso, setRectoVerso] = useState(false);
  const basculerRayon = () => setParRayon((v) => { try { localStorage.setItem("eva.listes.rayon", v ? "0" : "1"); } catch { /* ignoré */ } return !v; });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const loadLists = useCallback(async () => {
    try { const d = await api("/api/lists"); setLists(d.lists); setCur((c) => c ?? d.lists[0]?.id ?? null); } catch (e) { setError(e.message); }
  }, []);
  const loadCur = useCallback(async () => {
    if (!cur) return;
    try { setData(await api(`/api/lists/${cur}`)); } catch (e) { setError(e.message); }
  }, [cur]);
  useEffect(() => { loadLists(); }, [loadLists]);
  useEffect(() => { loadCur(); const t = setInterval(() => { loadCur(); loadLists(); }, 5000); return () => clearInterval(t); }, [loadCur, loadLists]);

  async function act(fn, done) {
    setError(""); setMsg("");
    try { const r = await fn(); if (done) setMsg(typeof done === "function" ? done(r) : done); await loadCur(); await loadLists(); } catch (e) { setError(e.message); }
  }
  const add = (e) => { e.preventDefault(); const items = text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean); if (!items.length) return;
    act(() => api(`/api/lists/${cur}/items`, { method: "POST", body: JSON.stringify({ items }) }), (r) => r.already_there?.length ? `Déjà dans la liste : ${r.already_there.join(", ")}` : ""); setText(""); };
  const toggle = (i) => act(() => api(`/api/lists/${cur}/items/${i.id}`, { method: "PATCH", body: JSON.stringify({ done: !i.done }) }));
  const del = (i) => act(() => api(`/api/lists/${cur}/items/${i.id}`, { method: "DELETE" }));
  const clearDone = () => act(() => api(`/api/lists/${cur}/clear-done`, { method: "POST" }), (r) => `${r.removed} élément(s) retiré(s).`);
  const estCourses = data?.kind === "shopping";
  const rayons = estCourses && parRayon;
  const print = () => act(() => api(`/api/lists/${cur}/print`, { method: "POST", body: JSON.stringify({ recto_verso: rectoVerso, par_rayon: rayons }) }), "Envoyée à l'imprimante.");
  const texte = async () => (await api(`/api/lists/${cur}/texte?par_rayon=${rayons}`)).texte;
  const copier = () => act(async () => { await navigator.clipboard.writeText(await texte()); }, "Liste copiée : colle-la où tu veux (SMS, notes…).");
  const partager = () => act(async () => { const t = await texte(); if (navigator.share) await navigator.share({ title: data.name, text: t }); else { await navigator.clipboard.writeText(t); } }, navigator.share ? "" : "Partage non disponible ici : liste copiée.");
  const telegram = () => act(() => api(`/api/lists/${cur}/telegram`, { method: "POST" }), "Envoyée sur Telegram.");
  const createList = (e) => { e.preventDefault(); if (!newName.trim()) return; act(async () => { const l = await api("/api/lists", { method: "POST", body: JSON.stringify({ name: newName, prive: newPrive }) }); setCur(l.id); setNewName(""); setNewPrive(false); }); };
  const delList = async () => { if ((await confirmer(`Supprimer la liste « ${data?.name} » ?`))) act(async () => { await api(`/api/lists/${cur}`, { method: "DELETE" }); setCur(null); setData(null); }); };

  const open = data?.items?.filter((i) => !i.done) || [];
  const done = data?.items?.filter((i) => i.done) || [];
  return (
    <section className="page" data-testid="lists-page">
      <header className="page__header"><h1>Listes</h1><span className="page__sub">Courses, tâches… EVA les remplit à la voix ; elles se mettent à jour toutes seules ici.</span></header>
      <div className="page__body">
        <div className="pj-sbx__tabs" data-testid="lists-tabs">
          {lists.map((l) => <button key={l.id} className={l.id === cur ? "is-on" : ""} onClick={() => setCur(l.id)} title={l.prive ? "Liste privée : toi seul la vois" : "Liste de la famille"}>{l.prive ? "🔒 " : ""}{l.name}{l.open ? ` (${l.open})` : ""}</button>)}
          <form className="pj-row" onSubmit={createList}>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Nouvelle liste" data-testid="list-new-name" />
            <label className="page__sub" title="Toi seul la verras (ni la famille, ni les invités)"><input type="checkbox" checked={newPrive} onChange={(e) => setNewPrive(e.target.checked)} data-testid="list-new-prive" /> 🔒 privée</label>
            <button className="btn btn--ghost" type="submit" disabled={!newName.trim()}>Créer</button>
          </form>
        </div>
        {data && (
          <div className="card" data-testid="list-card">
            <form className="pj-row" onSubmit={add}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ajouter… (plusieurs séparés par une virgule)" data-testid="list-add-input" />
              <button className="btn btn--primary" type="submit" disabled={!text.trim()} data-testid="list-add-btn">Ajouter</button>
            </form>
            {estCourses && open.length > 0 && <label className="page__sub"><input type="checkbox" checked={parRayon} onChange={basculerRayon} data-testid="list-par-rayon" /> Ranger par rayon du magasin</label>}
            <ul className="pj-trash__list" data-testid="list-items">
              {(rayons ? [...new Set(open.map((i) => i.rayon))].sort((a, b) => RAYONS.indexOf(a) - RAYONS.indexOf(b)) : [null]).map((r) => (
                <li key={r || "tout"} className="listes__rayon" style={{ display: "block", padding: 0, border: 0 }}>
                  {r && <span className="card__label" style={{ marginTop: 8 }}>{r}</span>}
                  <ul className="pj-trash__list">
                    {open.filter((i) => !r || i.rayon === r).map((i) => (
                      <li key={i.id}><input type="checkbox" checked={false} onChange={() => toggle(i)} aria-label={`Cocher ${i.text}`} /><span>{i.text}{i.by === "eva" ? " · ajouté par EVA" : ""}</span><button className="btn btn--ghost" onClick={() => del(i)}>Retirer</button></li>
                    ))}
                  </ul>
                </li>
              ))}
              {!open.length && <li><span>Rien à faire ici. 🎉</span></li>}
            </ul>
            {done.length > 0 && (
              <>
                <span className="card__label" style={{ marginTop: 10 }}>Fait ({done.length})</span>
                <ul className="pj-trash__list" data-testid="list-done">
                  {done.map((i) => (
                    <li key={i.id}><input type="checkbox" checked onChange={() => toggle(i)} aria-label={`Décocher ${i.text}`} /><span style={{ textDecoration: "line-through", opacity: .7 }}>{i.text}</span><button className="btn btn--ghost" onClick={() => del(i)}>Retirer</button></li>
                  ))}
                </ul>
              </>
            )}
            <div className="pj-row" style={{ marginTop: 12 }}>
              {done.length > 0 && <button className="btn btn--ghost" onClick={clearDone} data-testid="list-clear-done">Vider les éléments faits</button>}
              <button className="btn" onClick={print} data-testid="list-print">🖨️ Imprimer</button>
              <label className="page__sub"><input type="checkbox" checked={rectoVerso} onChange={(e) => setRectoVerso(e.target.checked)} /> recto-verso</label>
              <button className="btn btn--ghost" onClick={partager} title="Envoyer sur le téléphone (SMS, WhatsApp, notes…)" data-testid="list-partager">📱 Partager</button>
              <button className="btn btn--ghost" onClick={copier}>📋 Copier</button>
              <button className="btn btn--ghost" onClick={telegram} title="Envoie la liste sur Telegram">✈️ Telegram</button>
              {!["Courses", "À faire"].includes(data.name) && <button className="btn btn--danger" onClick={delList}>Supprimer la liste</button>}
            </div>
          </div>
        )}
        {error && <p className="page__warn" role="alert" data-testid="lists-error">{error}</p>}
        {msg && <p className="page__sub">{msg}</p>}
      </div>
    </section>
  );
}
