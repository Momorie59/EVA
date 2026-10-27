import { useEffect, useState } from "react";
import { api } from "../api";

export default function PersonalityCard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api("/api/personality").then(setData).catch((e) => setError(e.message)); }, []);
  async function pick(id) {
    setError("");
    try { const r = await api("/api/personality", { method: "PUT", body: JSON.stringify({ id }) }); setData((d) => ({ ...d, current: r.current })); }
    catch (e) { setError(e.message); }
  }
  return (
    <div className="card routercard">
      <span className="card__label">Personnalité d'EVA</span>
      {error && <p className="page__warn">{error}</p>}
      {data && (
        <label className="field"><span>Style des réponses</span>
          <select data-testid="personality" value={data.current} onChange={(e) => pick(e.target.value)}>
            {data.presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
      )}
      <p className="page__sub">Tu peux aussi le dire : « EVA, passe en mode concis », « sois plus chaleureuse », « reviens en mode normal ». Le style reste actif jusqu'au prochain changement.</p>
    </div>
  );
}
