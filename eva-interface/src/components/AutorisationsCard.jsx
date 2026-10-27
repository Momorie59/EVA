import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const NOMS = { code_run: "Exécuter du code", github_push: "Envoyer vers GitHub", fs_write: "Écrire un fichier", fs_edit: "Modifier un fichier", fs_delete: "Supprimer un fichier", terminal_run: "Commandes du terminal" };

// Les outils que tu as choisi d'autoriser « toujours » : EVA ne les redemande plus. Retirables à tout moment.
export default function AutorisationsCard() {
  const [outils, setOutils] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api("/api/autorisations").then((x) => { setOutils(x.outils); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const retirer = (o) => api(`/api/autorisations/${encodeURIComponent(o)}`, { method: "DELETE" }).then((x) => setOutils(x.outils)).catch((e) => setError(e.message));
  const tout = () => api("/api/autorisations", { method: "DELETE" }).then((x) => setOutils(x.outils)).catch((e) => setError(e.message));
  return (
    <div className="card routercard" data-testid="autorisations-card">
      <span className="card__label">Autorisations « toujours »</span>
      <p className="page__sub">Quand EVA te demande un accord, « Autoriser cette fois » ne laisse aucune trace ; « Toujours autoriser » l'ajoute ici et elle ne te redemande plus pour cet outil. Retire une autorisation à tout moment.</p>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {outils && outils.length === 0 && <p className="card__hint">Aucune autorisation permanente : EVA te demande chaque fois.</p>}
      {(outils || []).map((o) => (
        <div key={o} className="schedrow" data-testid="autorisation">
          <span style={{ flex: 1 }}><strong>{NOMS[o] || o}</strong> <small className="card__hint">({o})</small></span>
          <button className="btn btn--ghost" onClick={() => retirer(o)}>Retirer</button>
        </div>
      ))}
      {outils && outils.length > 1 && <button className="btn btn--danger" onClick={tout}>Tout retirer</button>}
    </div>
  );
}
