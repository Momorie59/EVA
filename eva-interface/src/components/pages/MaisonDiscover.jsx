import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";

const KIND_ICON = { tuya: "💡", yeelight: "💡", wiz: "💡", kasa: "🔌", shelly: "🔌", tasmota: "🔌", wled: "🌈", printer: "🖨️", computer: "🖥️", hue: "🌉", media: "📺", homeassistant: "🏠" };
const TYPES = { light: "Lumière", switch: "Prise / interrupteur", fan: "Ventilateur", climate: "Chauffage / clim", cover: "Volet", media: "TV / enceinte", computer: "Ordinateur", other: "Autre" };

function Candidate({ c, onChanged, onManual }) {
  const [name, setName] = useState(c.name); const [room, setRoom] = useState(""); const [type, setType] = useState(c.type);
  const [key, setKey] = useState(""); const [res, setRes] = useState(null); const [busy, setBusy] = useState(false);
  const post = async (path, body) => { setBusy(true); try { return await api(`/api/home/discovery/${path}`, { method: "POST", body: JSON.stringify(body) }); } catch (e) { return { ok: false, error: e.message }; } finally { setBusy(false); } };
  const direct = c.status === "ready" || c.status === "needs_key";
  const test = async () => setRes(await post("test", { key: c.key, local_key: key }));
  const add = async (force = false) => { const r = await post("add", { key: c.key, name, room, type, local_key: key, force }); setRes(r); if (r.ok) onChanged(); };
  const ignore = async () => { await post("ignore", { key: c.key }); onChanged(); };
  return (
    <li className="card" data-testid={`cand-${c.ip}`} style={{ listStyle: "none", marginBottom: 8 }}>
      <span className="card__label">{KIND_ICON[c.kind] || "❓"} {c.label} — {c.ip}</span>
      <p className="page__sub">{c.mac ? `${c.mac}${c.vendor ? ` · ${c.vendor}` : ""} · ` : ""}{c.evidence.join(" · ")}</p>
      {c.link_device && <p className="page__sub">Cet appareil est déjà dans EVA (importé du cloud) : on lui ajoute son adresse pour le piloter en local.</p>}
      {c.hint && <p className="page__sub">{c.hint}</p>}
      {direct && !c.link_device && (
        <div className="pj-row">
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label={`Nom ${c.ip}`} placeholder="Nom (ex. Lampe salon)" data-testid={`cand-name-${c.ip}`} />
          <input value={room} onChange={(e) => setRoom(e.target.value)} aria-label={`Pièce ${c.ip}`} placeholder="Pièce" data-testid={`cand-room-${c.ip}`} />
          {c.kind !== "printer" && c.kind !== "computer" && <select value={type} onChange={(e) => setType(e.target.value)} aria-label={`Type ${c.ip}`}>{Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
        </div>
      )}
      {c.kind === "tuya" && <div className="pj-row"><input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Clé locale (vide = prise dans ton compte Tuya cloud)" aria-label={`Clé locale ${c.ip}`} autoComplete="off" data-testid={`cand-key-${c.ip}`} style={{ minWidth: 280 }} /></div>}
      {res && <p className={res.ok ? "page__sub" : "page__warn"} role={res.ok ? undefined : "alert"} data-testid={`cand-res-${c.ip}`}>{res.ok ? `✔ ${res.info || "ajouté."}` : `✘ ${res.error}`}{res.details?.length ? ` (${res.details.join(" | ")})` : ""}</p>}
      <div className="pj-row">
        {direct && <button className="btn" onClick={test} disabled={busy} data-testid={`cand-test-${c.ip}`}>Tester</button>}
        {direct && <button className="btn btn--primary" onClick={() => add(false)} disabled={busy} data-testid={`cand-add-${c.ip}`}>{c.link_device ? "Passer en local" : "Ajouter"}</button>}
        {res?.can_force && <button className="btn btn--ghost" onClick={() => add(true)} disabled={busy}>Ajouter quand même</button>}
        {c.kind === "unknown" && <button className="btn" onClick={() => onManual(c)}>Configurer à la main…</button>}
        <button className="btn btn--ghost" onClick={ignore} disabled={busy} data-testid={`cand-ignore-${c.ip}`}>Ignorer</button>
      </div>
    </li>
  );
}

export default function MaisonDiscover({ onChanged, onManual }) {
  const [ov, setOv] = useState(null); const [err, setErr] = useState(""); const timer = useRef(null);
  const load = useCallback(async () => { try { setOv(await api("/api/home/discovery")); setErr(""); } catch (e) { setErr(e.message); } }, []);
  useEffect(() => { load(); }, [load]);
  const running = ov?.state?.running;
  useEffect(() => { if (!running) return undefined; timer.current = setInterval(load, 2000); return () => clearInterval(timer.current); }, [running, load]);
  const wasRunning = useRef(false);
  useEffect(() => { if (wasRunning.current && !running) onChanged?.(); wasRunning.current = !!running; }, [running, onChanged]);
  if (!ov) return err ? <p className="page__warn" role="alert">{err}</p> : null;
  const { result: r, settings: s, scanner } = ov;
  const todo = r.candidates.filter((c) => !c.already);
  const direct = todo.filter((c) => ["ready", "needs_key"].includes(c.status));
  const info = todo.filter((c) => !["ready", "needs_key"].includes(c.status));
  const done = r.candidates.filter((c) => c.already);
  const start = async () => { try { await api("/api/home/discovery/scan", { method: "POST", body: JSON.stringify({ quick: false }) }); } catch (e) { setErr(e.message); } load(); };
  const cfg = async (patch) => { try { await api("/api/home/discovery/settings", { method: "PUT", body: JSON.stringify({ enabled: s.enabled, interval_min: s.interval_min, cidr: s.cidr, ...patch }) }); } catch (e) { setErr(e.message); } load(); };
  const changed = () => { load(); onChanged?.(); };
  const problem = r.problem || (!scanner.up && scanner.problem) || "";
  return (
    <div className="card" data-testid="discover-panel">
      <span className="card__label">Appareils trouvés sur ton réseau</span>
      <p className="page__sub">EVA écoute ton réseau (ARP, mDNS, SSDP, diffusions Tuya / WiZ / Yeelight / Kasa) et reconnaît les ampoules, prises, rubans LED, imprimantes et ordinateurs. Rien n'est ajouté sans ton accord, et chaque ajout est testé avant d'être enregistré.</p>
      <div className="pj-row">
        <button className="btn btn--primary" onClick={start} disabled={running} data-testid="disc-scan">{running ? (ov.state.step || "Recherche…") : "Chercher les appareils"}</button>
        <label><input type="checkbox" checked={!!s.enabled} onChange={(e) => cfg({ enabled: e.target.checked })} data-testid="disc-auto" /> recherche automatique toutes les <select value={s.interval_min} onChange={(e) => cfg({ interval_min: Number(e.target.value) })} aria-label="Intervalle">{[10, 30, 60, 180, 720, 1440].map((m) => <option key={m} value={m}>{m >= 60 ? `${m / 60} h` : `${m} min`}</option>)}</select></label>
      </div>
      {err && <p className="page__warn" role="alert">{err}</p>}
      {ov.state.error && <p className="page__warn" role="alert">Dernière recherche en échec : {ov.state.error}</p>}
      {problem && <p className="page__warn" role="alert" data-testid="disc-problem">⚠ Détection réduite. {problem}</p>}
      {r.at > 0 && <p className="page__sub" data-testid="disc-summary">Dernière recherche : {new Date(r.at * 1000).toLocaleString("fr-FR")} · {r.hosts} machine(s) vue(s) · {r.source === "scanner" ? "service eva-scanner (complet)" : "depuis le conteneur (réduit)"}{r.took ? ` · ${r.took} s` : ""}{Object.keys(r.errors || {}).length ? ` · sondes en échec : ${Object.entries(r.errors).map(([k, v]) => `${k} (${v})`).join(", ")}` : ""}</p>}
      {r.healed?.length > 0 && <p className="page__sub" data-testid="disc-healed">🔧 Adresse mise à jour automatiquement : {r.healed.map((h) => `${h.name} ${h.old} → ${h.new}`).join(" ; ")}.</p>}
      {r.at > 0 && !direct.length && !running && <p className="page__sub">Aucun nouvel appareil à ajouter. Si un appareil manque : vérifie qu'il est allumé et connecté au même réseau, rallume-le (les appareils Tuya s'annoncent à l'allumage), puis relance la recherche.</p>}
      <ul style={{ padding: 0, margin: 0 }}>{direct.map((c) => <Candidate key={c.key} c={c} onChanged={changed} onManual={onManual} />)}</ul>
      {info.length > 0 && (
        <details open><summary>À ajouter autrement ({info.length})</summary>
          <ul style={{ padding: 0, margin: 0 }}>{info.map((c) => <Candidate key={c.key} c={c} onChanged={changed} onManual={onManual} />)}</ul></details>
      )}
      {r.others?.length > 0 && (
        <details><summary>Autres machines du réseau ({r.others.length})</summary>
          <ul className="pj-trash__list" data-testid="disc-others">{r.others.map((o) => <li key={o.key}><span><b>{o.ip}</b> {o.vendor || ""} {o.hostname || ""} <small>{o.mac}{o.hint ? ` — ${o.hint}` : ""}</small></span><button className="btn" onClick={() => onManual(o)}>Configurer à la main…</button></li>)}</ul></details>
      )}
      {done.length > 0 && <p className="page__sub">{done.length} appareil(s) déjà dans EVA : {done.map((c) => c.device_name || c.label).join(", ")}.</p>}
      {r.ignored > 0 && <p className="page__sub">{r.ignored} ignoré(s). <button className="btn btn--ghost" onClick={async () => { await api("/api/home/discovery/ignore", { method: "POST", body: JSON.stringify({ reset: true }) }); load(); }}>Les réafficher</button></p>}
    </div>
  );
}
