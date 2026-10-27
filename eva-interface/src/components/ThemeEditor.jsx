import { useState } from "react";
import { PRESETS, normalizeTheme, presetTheme } from "../theme/theme";
import { useTheme } from "../theme/store";

const COLOR_FIELDS = [
  ["bgA", "Fond (haut)"], ["bgB", "Fond (milieu)"], ["bgC", "Fond (bas)"],
  ["glow", "Lueur centrale"], ["accent", "Accent"], ["accent2", "Accent 2"], ["ink", "Texte"],
];

function Seg({ label, value, options, onChange, testid }) {
  return (
    <div className="te-row" data-testid={testid}>
      <span className="te-row__label">{label}</span>
      <div className="te-seg" role="group" aria-label={label}>
        {options.map(([v, text]) => (
          <button key={v} type="button" className={value === v ? "is-on" : ""} aria-pressed={value === v} onClick={() => onChange(v)}>{text}</button>
        ))}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step = 1, unit = "", fmt, onChange, testid }) {
  return (
    <label className="te-row">
      <span className="te-row__label">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} data-testid={testid} />
      <span className="te-row__val">{fmt ? fmt(value) : Math.round(value)}{unit}</span>
    </label>
  );
}

// Éditeur de thème : palettes, couleurs libres, transparence, disposition. Tout s'applique en direct.
export default function ThemeEditor() {
  const [theme, setTheme, resetTheme] = useTheme();
  const [io, setIo] = useState({ open: false, text: "", error: "" });
  const L = theme.layout;
  const setLayout = (patch) => setTheme((t) => ({ ...t, layout: { ...t.layout, ...patch } }));
  const setColor = (k, v) => setTheme((t) => ({ ...t, preset: "custom", colors: { ...t.colors, [k]: v } }));

  function exportJson() {
    const { updatedAt, ...clean } = theme; // eslint-disable-line no-unused-vars
    const text = JSON.stringify(clean, null, 2);
    setIo({ open: true, text, error: "" });
    try { navigator.clipboard?.writeText(text); } catch { /* le texte reste affiché pour copier à la main */ }
  }
  function importJson() {
    try {
      const parsed = JSON.parse(io.text);
      if (!parsed || typeof parsed !== "object") throw new Error();
      setTheme(normalizeTheme(parsed));
      setIo({ open: false, text: "", error: "" });
    } catch {
      setIo((s) => ({ ...s, error: "Ce n'est pas un thème valide (JSON attendu)." }));
    }
  }

  return (
    <div className="te" data-testid="theme-editor">
      <section>
        <h3 className="te-h">Palettes</h3>
        <div className="te-presets">
          {Object.entries(PRESETS).map(([id, p]) => (
            <button key={id} type="button" className={`te-preset ${theme.preset === id ? "is-on" : ""}`} data-testid={`preset-${id}`}
              onClick={() => setTheme((t) => ({ ...presetTheme(id), layout: t.layout }))} aria-pressed={theme.preset === id}>
              <span className="te-preset__sw" style={{ background: `linear-gradient(135deg, ${p.colors.bgA}, ${p.colors.bgB} 55%, ${p.colors.bgC})` }}>
                <i style={{ background: p.colors.accent }} />
              </span>
              <span>{p.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3 className="te-h">Couleurs</h3>
        <div className="te-colors">
          {COLOR_FIELDS.map(([k, label]) => (
            <label key={k} className="te-color">
              <input type="color" value={theme.colors[k]} onChange={(e) => setColor(k, e.target.value)} data-testid={`color-${k}`} aria-label={label} />
              <span>{label}</span>
              <code>{theme.colors[k]}</code>
            </label>
          ))}
        </div>
        <Slider label="Transparence des panneaux" value={theme.glass} min={0} max={0.9} step={0.01} unit=" %" fmt={(v) => Math.round(v * 100)} onChange={(v) => setTheme((t) => ({ ...t, preset: "custom", glass: v }))} testid="glass" />
        <Slider label="Flou du verre" value={theme.blur} min={0} max={40} unit=" px" onChange={(v) => setTheme((t) => ({ ...t, blur: v }))} testid="blur" />
        <Slider label="Lisibilité du texte secondaire" value={theme.textStrength} min={0.6} max={1} step={0.01} unit=" %" fmt={(v) => Math.round(v * 100)} onChange={(v) => setTheme((t) => ({ ...t, textStrength: v }))} testid="textstrength" />
        <Slider label="Arrondi des coins" value={L.radius} min={0} max={32} unit=" px" onChange={(v) => setLayout({ radius: v })} testid="radius" />
      </section>

      <section>
        <h3 className="te-h">Disposition (écran large)</h3>
        <Seg label="Menu" value={L.nav} testid="seg-nav" onChange={(v) => setLayout({ nav: v })}
          options={[["left", "Latéral"], ["rail", "Icônes"], ["top", "En haut"], ["hidden", "Masqué"]]} />
        <Seg label="Conversation" value={L.chat} testid="seg-chat" onChange={(v) => setLayout({ chat: v })}
          options={[["right", "Droite"], ["left", "Gauche"], ["hidden", "Masquée"]]} />
        <Seg label="Widgets" value={L.widgets} testid="seg-widgets" onChange={(v) => setLayout({ widgets: v })}
          options={[["bottom", "En bas"], ["left", "Gauche"], ["right", "Droite"], ["hidden", "Masqués"]]} />
        <Seg label="Taille du texte" value={L.density} testid="seg-density" onChange={(v) => setLayout({ density: v })}
          options={[["compact", "Compact"], ["normal", "Normal"], ["large", "Grand"]]} />
        <Slider label="Taille du logo" value={L.logo} min={60} max={140} unit=" %" onChange={(v) => setLayout({ logo: v })} testid="logo" />
        <div className="te-toggles">
          <label><input type="checkbox" checked={L.rings} onChange={(e) => setLayout({ rings: e.target.checked })} data-testid="tog-rings" /> Anneaux HUD</label>
          <label><input type="checkbox" checked={L.grid} onChange={(e) => setLayout({ grid: e.target.checked })} data-testid="tog-grid" /> Grille de fond</label>
          <label><input type="checkbox" checked={L.notes} onChange={(e) => setLayout({ notes: e.target.checked })} data-testid="tog-notes" /> Post-it affichés</label>
        </div>
        <p className="te-note">Sur téléphone, la disposition reste adaptée à l'écran : seules les couleurs, la transparence et la taille du texte s'appliquent.</p>
      </section>

      <section className="te-actions">
        <button type="button" className="btn" onClick={exportJson} data-testid="theme-export">Exporter</button>
        <button type="button" className="btn" onClick={() => setIo({ open: true, text: "", error: "" })} data-testid="theme-import-open">Importer</button>
        <button type="button" className="btn btn--ghost" onClick={() => { resetTheme(); setIo({ open: false, text: "", error: "" }); }} data-testid="theme-reset">Réinitialiser</button>
      </section>
      {io.open && (
        <div className="te-io">
          <textarea value={io.text} onChange={(e) => setIo({ open: true, text: e.target.value, error: "" })} rows={8} spellCheck={false} aria-label="Thème au format JSON" data-testid="theme-json" placeholder="Colle ici un thème exporté (JSON)" />
          {io.error && <p className="te-error" role="alert">{io.error}</p>}
          <div className="te-actions">
            <button type="button" className="btn" onClick={importJson} data-testid="theme-import">Appliquer ce thème</button>
            <button type="button" className="btn btn--ghost" onClick={() => setIo({ open: false, text: "", error: "" })}>Fermer</button>
          </div>
        </div>
      )}
    </div>
  );
}
