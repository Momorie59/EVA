import { useState } from "react";
import ThemeEditor from "./ThemeEditor";
import { carteMeteoOn, popupsOn } from "../hooks/useEvaCore";

export default function ThemeCard() {
  const [pop, setPop] = useState(popupsOn());
  const toggle = (v) => { setPop(v); try { localStorage.setItem("eva.popups", v ? "1" : "0"); } catch { /* ignoré */ } };
  const [meteo, setMeteo] = useState(carteMeteoOn());
  const toggleMeteo = (v) => { setMeteo(v); try { localStorage.setItem("eva.carte_meteo", v ? "1" : "0"); } catch { /* ignoré */ } };
  return (
    <div className="card" data-testid="theme-card">
      <span className="card__label">Apparence</span>
      <p className="card__hint">Palette, couleurs, transparence et disposition de l'interface. Les changements sont immédiats et conservés sur le serveur : tu retrouves le même thème sur tous tes écrans.</p>
      <label className="switch-row" data-testid="popups-toggle">
        <input type="checkbox" checked={pop} onChange={(e) => toggle(e.target.checked)} /> Fenêtres flottantes (heure, actualités, présentations — jamais la météo)
      </label>
      <label className="switch-row" data-testid="meteo-toggle">
        <input type="checkbox" checked={meteo} onChange={(e) => toggleMeteo(e.target.checked)} /> Carte météo dans la conversation
      </label>
      <p className="card__hint">Désactivés par défaut : EVA répond simplement dans la conversation (la météo reste dans le widget de l'accueil). Réglage propre à cet écran.</p>
      <ThemeEditor />
    </div>
  );
}
