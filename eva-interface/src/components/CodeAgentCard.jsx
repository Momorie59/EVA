import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

// Agent de code (Aider, gratuit, modèles locaux) : installation à la demande, puis EVA s'en sert sur tes projets.
export default function CodeAgentCard() {
  const [s, setS] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api("/api/code-agent").then((x) => { setS(x); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.en_cours) return undefined;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [s?.en_cours, load]);
  const installer = async () => { setError(""); try { setS(await api("/api/code-agent/installer", { method: "POST" })); } catch (e) { setError(e.message); } };

  return (
    <div className="card" data-testid="code-agent-card">
      <span className="card__label">Agent de code</span>
      <p className="card__hint">Demande à EVA « dans mon projet X, ajoute… / corrige… » : elle confie le travail à Aider (logiciel libre, gratuit) avec ton modèle local. Chaque modification est enregistrée dans git et s'annule. EVA te demande toujours ton accord avant de lancer l'agent. Réservé aux personnes qui ont la fonctionnalité « Code & système ».</p>
      {!s && !error && <p className="card__hint">Chargement…</p>}
      {s && (
        <>
          <p>{s.installe ? <>✅ Installé (Aider {s.version}) — modèle utilisé : <b>{s.modele}</b> (modèle « code » du choix automatique, sinon le modèle principal).</> : s.en_cours ? "⏳ Installation en cours (quelques minutes, ~650 Mo)…" : "Pas encore installé."}</p>
          {s.travail_en_cours && <p className="card__hint">L'agent travaille en ce moment sur une demande.</p>}
          {!s.en_cours && <button className="btn btn--primary" onClick={installer} data-testid="code-agent-install">{s.installe ? "Réinstaller" : "Installer l'agent de code"}</button>}
          {(s.en_cours || s.erreur) && s.journal && <pre className="card__hint" style={{ whiteSpace: "pre-wrap", maxHeight: "10rem", overflow: "auto" }}>{s.journal}</pre>}
          {s.erreur && <p className="page__warn">Échec : {s.erreur}</p>}
        </>
      )}
      {error && <p className="page__warn" role="alert">{error}</p>}
    </div>
  );
}
