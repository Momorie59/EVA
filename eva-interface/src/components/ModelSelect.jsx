import { grouper } from "../models/catalogue";

// Liste déroulante de modèles rangée par origine, avec des noms lisibles (Paramètres).
export default function ModelSelect({ value, onChange, modeles, vide, manquant = "pas encore téléchargé", ...rest }) {
  const groupes = grouper(modeles);
  const connu = !value || modeles.some((m) => m.name === value);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
      {vide !== undefined && <option value="">{vide}</option>}
      {!connu && <option value={value}>{value} · {manquant}</option>}
      {groupes.map((g) => (
        <optgroup key={g.id} label={`${g.icone} ${g.label}`}>
          {g.modeles.map((d) => (
            <option key={d.name} value={d.name}>
              {d.titre}{d.variante ? ` ${d.variante}` : ""}{d.source ? ` — ${d.source}` : ""}
              {d.lent ? " · très lent" : d.tools === false ? " · sans outils" : ""}{d.vision ? " · images" : ""}{d.charge ? " · ⚡" : ""}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
