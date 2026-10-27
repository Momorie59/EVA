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
    </div>
  );
}
