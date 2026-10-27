import { useEffect, useState } from "react";
import { api } from "../api";

// Paramètres › Modules : activer ou non le wiki et le livre de recettes (pour toute la maison).
export default function ModulesCard() {
  const [mods, setMods] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/modules").then((d) => setMods(d.modules || [])).catch((e) => setErr(e.message)); }, []);
  const basculer = async (m) => {
    try {
      const d = await api("/api/modules", { method: "PUT", body: JSON.stringify({ [m.id]: !m.actif }) });
      setMods(d.modules || []);
      window.dispatchEvent(new Event("eva:modules-changed"));
    } catch (e) { setErr(e.message); }
  };
  return (
    <div className="card" data-testid="modules-card">
      <span className="card__label">Modules</span>
      <p className="card__hint">Des fonctions en plus, à activer seulement si tu en as besoin. Un module coupé disparaît du menu et des outils d'EVA ; ses pages et recettes restent gardées sur le NAS et reviennent quand tu le rallumes. Qui y a droit : Paramètres › Sécurité & données › Fonctionnalités.</p>
      {mods.map((m) => (
        <label key={m.id} className="module-row">
          <input type="checkbox" checked={m.actif} onChange={() => basculer(m)} data-testid={`module-${m.id}`} />
          <span className="module-row__icon" aria-hidden="true">{m.icon}</span>
          <span><b>{m.label}</b><br /><small className="card__hint">{m.hint}</small></span>
        </label>
      ))}
      {err && <p className="page__warn">{err}</p>}
      <PluginsBloc />
    </div>
  );
}

// Plugins : outils ajoutés sans toucher au code d'EVA (dossier plugins/, lecture seule). Voir PLUGINS.md.
function PluginsBloc() {
  const [d, setD] = useState(null); const [err, setErr] = useState("");
  const relire = () => api("/api/plugins").then((x) => { setD(x); setErr(""); }).catch((e) => setErr(e.status === 404 ? "" : e.message));
  useEffect(() => { relire(); }, []);
  const basculer = (p) => api("/api/plugins", { method: "PUT", body: JSON.stringify({ [p.nom]: !p.actif }) }).then(setD).catch((e) => setErr(e.message));
  if (!d) return err ? <p className="page__warn">{err}</p> : null;
  return (
    <div data-testid="plugins">
      <span className="card__label" style={{ marginTop: 14 }}>Plugins</span>
      <p className="card__hint">Des outils ajoutés sans toucher au code d'EVA : un dossier par plugin dans <code>plugins/</code> à côté de docker-compose.yml (guide : PLUGINS.md). C'est du code qui tourne avec les droits d'EVA : n'active que ceux dont tu as lu le code.</p>
      {d.plugins.length === 0 && <p className="card__hint">Aucun plugin trouvé dans {d.dossier}.</p>}
      {d.plugins.map((p) => (
        <label key={p.nom} className="module-row">
          <input type="checkbox" checked={p.actif} onChange={() => basculer(p)} data-testid={`plugin-${p.nom}`} />
          <span className="module-row__icon" aria-hidden="true">🧩</span>
          <span><b>{p.nom}</b><br /><small className="card__hint">{p.description}{p.outils.length ? ` · outils : ${p.outils.join(", ")}` : ""}</small>
            {p.erreur && <small className="page__warn" style={{ display: "block" }}>⚠️ {p.erreur}</small>}</span>
        </label>
      ))}
      <button className="btn btn--ghost" onClick={relire} data-testid="plugins-relire">↻ Relire le dossier</button>
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}
