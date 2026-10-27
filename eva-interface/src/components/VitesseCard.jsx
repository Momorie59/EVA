import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const s = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1).replace(".", ",")} s` : `${ms} ms`);

// Vitesse du serveur IA : ce qui est en mémoire vidéo, les rechargements de modèles (le grand ralentisseur sur 6 Go) et la vitesse.
export default function VitesseCard() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api("/api/models/vitesse").then((x) => { setD(x); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  return (
    <div className="card" data-testid="vitesse-card">
      <span className="card__label">Vitesse du serveur IA</span>
      <p className="card__hint">Sur une carte de 6 Go, deux modèles ne tiennent pas toujours ensemble : passer de l'un à l'autre oblige à en recharger un (plusieurs secondes). EVA prend le modèle déjà chargé quand il peut répondre, et mesure tout ici (dernière heure).</p>
      {err && <p className="page__warn">{err}</p>}
      {d && (
        <>
          <b>En mémoire maintenant</b>
          {d.charges === null && <p className="card__hint">Serveur IA injoignable.</p>}
          {d.charges && d.charges.length === 0 && <p className="card__hint">Aucun modèle chargé (il se chargera au prochain message).</p>}
          {d.charges && d.charges.map((m) => (
            <div key={m.name} className="schedrow">
              <span style={{ minWidth: "9rem" }}>{m.name}</span>
              <span className="card__hint">{String(m.vram_gb).replace(".", ",")} Go en mémoire vidéo{m.vram_gb < m.size_gb * 0.95 ? ` sur ${String(m.size_gb).replace(".", ",")} Go : déborde, plus lent` : ""}</span>
            </div>
          ))}
          <ul className="access__legend">
            <li>{d.tours} réponse(s) mesurée(s), <b>{d.rechargements} rechargement(s) de modèle</b>{d.rechargements ? ` (${s(d.rechargement_moyen_ms)} chacun en moyenne)` : ""}</li>
            {d.lecture_tokens_s && <li>Lecture : {d.lecture_tokens_s.toLocaleString("fr-FR")} jetons/s · Écriture : {(d.ecriture_tokens_s || 0).toLocaleString("fr-FR")} jetons/s</li>}
          </ul>
          {d.conseil && <p className="page__warn" data-testid="vitesse-conseil">💡 {d.conseil}</p>}
          {d.derniers.length > 0 && (
            <details>
              <summary className="card__hint">Dernières réponses</summary>
              <table className="md-table"><thead><tr><th>Modèle</th><th>Chargement</th><th>Lecture</th><th>Écriture</th></tr></thead>
                <tbody>{d.derniers.map((t, i) => (
                  <tr key={i}><td>{t.model}</td><td>{t.load_ms >= 1500 ? `⚠ ${s(t.load_ms)}` : s(t.load_ms)}</td><td>{t.prompt_tokens} jetons, {s(t.prompt_ms)}</td><td>{t.gen_tokens} jetons, {s(t.gen_ms)}</td></tr>
                ))}</tbody></table>
            </details>
          )}
          <button className="btn btn--ghost" onClick={load}>Actualiser</button>
        </>
      )}
    </div>
  );
}
