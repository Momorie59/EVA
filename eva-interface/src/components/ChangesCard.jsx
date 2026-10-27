import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

const KIND = { fs_write: "Fichier écrit", fs_append: "Ajout à un fichier", fs_delete: "Fichier supprimé", skill_save: "Skill enregistré", skill_install: "Skill installé" };

// Tout ce qu'EVA a écrit elle-même (fichiers, skills), avec un bouton pour revenir en arrière.
export default function ChangesCard() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api("/api/changes?limit=30").then((d) => setItems(d.changes)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function undo(c, force = false) {
    setError("");
    try { await api(`/api/changes/${c.id}/undo`, { method: "POST", body: JSON.stringify({ force }) }); load(); }
    catch (e) {
      if (!force && /forcer/.test(e.message) && (await confirmer(`${e.message}\n\nAnnuler quand même ?`))) return undo(c, true);
      setError(e.message);
    }
  }

  return (
    <div className="card routercard">
      <span className="card__label">Modifications faites par EVA (annulables)</span>
      {error && <p className="page__warn">{error}</p>}
      {items && items.length === 0 && <p className="page__sub">Rien pour l'instant : EVA n'a encore rien écrit seule.</p>}
      <ul className="changelist" data-testid="change-list">
        {(items || []).map((c) => (
          <li key={c.id} className={c.undone ? "is-undone" : ""}>
            <div>
              <b>{KIND[c.kind] || c.kind}</b> — <code>{c.path}</code>
              <span className="changelist__when"> · {new Date(c.created_at).toLocaleString("fr-FR")}{c.created ? " · création" : ""}{c.deleted ? " · suppression" : ""}</span>
              {c.preview && <pre className="changelist__preview">{c.preview.slice(0, 160)}</pre>}
            </div>
            {c.undone ? <em>annulée</em> : <button className="btn" onClick={() => undo(c)}>↶ Annuler</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}
