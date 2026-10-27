import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const BADGE = { gpu: ["✅", "is-gpu"], mixed: ["⚠️", "is-mixed"] };
const fmtN = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${Math.round(n / 1e3)} k` : String(n || 0));
const key = (s) => String(s || "").toLowerCase();

// « Suggestions » : EVA interroge Hugging Face et propose, par rôle, les meilleurs modèles qui tiennent sur le serveur IA.
export default function HFRecommend({ installed, cfg, onApply }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [pick, setPick] = useState({});
  const [pulls, setPulls] = useState([]);
  const [msg, setMsg] = useState("");
  const timer = useRef(null);

  function load(refresh = false) {
    setBusy(true); setError("");
    api(`/api/models/recommend${refresh ? "?refresh=true" : ""}`)
      .then((d) => { setData(d); setPick((p) => { const n = { ...p }; d.roles.forEach((r) => { if (!(r.role in n)) n[r.role] = cfg[r.role] || r.role === "default" ? "" : (r.choices[0]?.ollama || ""); }); return n; }); })
      .catch((e) => setError(e.message)).finally(() => setBusy(false));
  }
  useEffect(() => { load(); return () => clearInterval(timer.current); }, []); // eslint-disable-line

  const have = new Set(installed.map((m) => key(m.name)));
  const isHave = (name) => have.has(key(name)) || have.has(key(name) + ":latest");

  async function go() {
    setMsg(""); setError("");
    const chosen = Object.entries(pick).filter(([, name]) => name);
    const todo = chosen.filter(([, name]) => !isHave(name));
    try {
      for (const [, name] of todo) await api("/api/models/pull", { method: "POST", body: JSON.stringify({ name }) });
    } catch (e) { setError(e.message); return; }
    const names = new Set(todo.map(([, n]) => n));
    const tick = async () => {
      try {
        const { pulls: all } = await api("/api/models/pulls");
        const mine = all.filter((p) => names.has(p.name));
        setPulls(mine);
        const err = mine.find((p) => p.error);
        if (err) { clearInterval(timer.current); setError(`Téléchargement de ${err.name} impossible : ${err.error}`); return; }
        if (mine.every((p) => p.done)) {
          clearInterval(timer.current);
          const assign = Object.fromEntries(chosen);
          await onApply(assign);
          setMsg("Modèles installés et attribués. Pense à relire puis enregistrer si tu veux ajuster.");
        }
      } catch (e) { clearInterval(timer.current); setError(e.message); }
    };
    if (!todo.length) { await onApply(Object.fromEntries(chosen)); setMsg("Ces modèles étaient déjà installés : attribution mise à jour."); return; }
    clearInterval(timer.current); timer.current = setInterval(tick, 2000); tick();
  }

  return (
    <div className="hfrec" data-testid="hf-recommend">
      <span className="card__label">Suggestions Hugging Face</span>
      {busy && <p className="card__hint">EVA cherche sur Hugging Face les modèles les plus performants qui tiennent sur ton serveur IA… (jusqu'à une minute)</p>}
      {error && <p className="page__warn" role="alert">{error}</p>}
      {data && (
        <p className="card__hint">Pour {data.hardware.vram_gb} Go de mémoire vidéo et {data.hardware.ram_gb} Go de RAM. Choix classés par popularité, fraîcheur et taille : ✅ tient sur la carte (rapide). Rien n'est installé sans ton accord.</p>
      )}
      {data?.roles.map((r) => (
        <fieldset key={r.role} className="hfrec__role" data-testid={`rec-${r.role}`}>
          <legend>{r.label}</legend>
          {r.choices.length === 0 && <p className="card__hint">Rien de convaincant trouvé pour ce rôle.</p>}
          {r.choices.map((c) => {
            const [icon, cls] = BADGE[c.level] || BADGE.mixed;
            return (
              <label key={c.ollama} className={`hfrec__choice ${pick[r.role] === c.ollama ? "is-on" : ""}`}>
                <input type="radio" name={`rec-${r.role}`} checked={pick[r.role] === c.ollama} onChange={() => setPick({ ...pick, [r.role]: c.ollama })} data-testid={`rec-${r.role}-${c.repo.split("/")[1]}`} />
                <span className="hfrec__name"><b>{c.repo}</b> <small>{c.quant} · {c.size_gb} Go · {c.params_b} G paramètres</small></span>
                <span className={`hf-fit ${cls}`} title={c.detail}>{icon} {c.verdict}</span>
                <small className="card__hint">{fmtN(c.downloads)} téléchargements · {fmtN(c.likes)} ♥{isHave(c.ollama) ? " · déjà installé" : ""}</small>
                <a href={`https://huggingface.co/${c.repo}`} target="_blank" rel="noreferrer">voir ↗</a>
              </label>
            );
          })}
          {r.choices.length > 0 && (
            <label className="hfrec__choice"><input type="radio" name={`rec-${r.role}`} checked={!pick[r.role]} onChange={() => setPick({ ...pick, [r.role]: "" })} /><span>Ne rien changer pour ce rôle ({cfg[r.role] || "réglage actuel"})</span></label>
          )}
        </fieldset>
      ))}
      {pulls.map((p) => (
        <div key={p.name} className="hfrec__pull"><small>{p.name} — {p.error ? p.error : p.done ? "terminé" : p.total ? `${Math.round((p.completed / p.total) * 100)} %` : p.status}</small>
          <div className="disk__bar"><i style={{ width: `${p.total ? Math.round((p.completed / p.total) * 100) : p.done ? 100 : 5}%` }} /></div></div>
      ))}
      {msg && <p className="page__sub" role="status">{msg}</p>}
      <div className="agentform__actions">
        <button className="btn" onClick={() => load(true)} disabled={busy}>Relancer la recherche</button>
        <button className="btn btn--primary" onClick={go} disabled={busy || !data} data-testid="rec-go">Installer et utiliser la sélection</button>
      </div>
    </div>
  );
}
