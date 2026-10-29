import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../AuthGate";
import MaisonDiscover from "./MaisonDiscover";
import { confirmer } from "../../confirmer";

const FIELDS = {
  tuya: [["device_id", "ID de l'appareil *"], ["ip", "Adresse IP (mode local ; vide = cloud)"], ["local_key", "Clé locale", "password"], ["version", "Version (3.3, 3.4, 3.5)"], ["switch_dp", "N° de l'interrupteur (1 par défaut)"]],
  shelly: [["ip", "Adresse IP *"], ["gen", "Génération (1 ou 2)"], ["channel", "Canal (0 par défaut)"]],
  tasmota: [["ip", "Adresse IP *"]],
  wled: [["ip", "Adresse IP *"]],
  yeelight: [["ip", "Adresse IP * (active « Contrôle LAN » dans l'appli Yeelight)"], ["port", "Port (55443)"]],
  wiz: [["ip", "Adresse IP *"]],
  kasa: [["ip", "Adresse IP *"]],
  wol: [["mac", "Adresse MAC * (AA:BB:CC:DD:EE:FF)"], ["ip", "Adresse IP (pour connaître l'état)"], ["broadcast", "Adresse de diffusion (ex. 192.168.1.255)"]],
  mqtt: [["host", "Serveur MQTT *"], ["port", "Port (1883)"], ["username", "Utilisateur"], ["password", "Mot de passe", "password"], ["topic", "Topic de commande *"], ["payload_on", "Message « allumer » (ON)"], ["payload_off", "Message « éteindre » (OFF)"], ["state_topic", "Topic d'état"], ["brightness_topic", "Topic de luminosité"]],
  hue: [["ip", "Adresse IP du pont *"], ["light", "N° de la lampe *"]],
  cast: [["ip", "Adresse IP de l'enceinte / TV *"], ["port", "Port (8009)"]],
  ha: [["entity_id", "Entité Home Assistant * (ex. light.salon)"]],
};
const DRIVER_NAMES = { cast: "Google Home / Nest / Chromecast", hue: "Philips Hue (pont)", tuya: "Tuya / Smart Life", shelly: "Shelly", tasmota: "Tasmota", wled: "WLED", yeelight: "Yeelight", wiz: "WiZ", kasa: "TP-Link Kasa", wol: "Wake-on-LAN (allumer un PC)", mqtt: "MQTT", ha: "Home Assistant" };
const ACTIONS = [["on", "Allumer"], ["off", "Éteindre"], ["toggle", "Basculer"], ["brightness", "Luminosité (0-100)"], ["color", "Couleur"], ["temperature", "Température"]];

function useCall() {
  const [error, setError] = useState(""); const [msg, setMsg] = useState("");
  const call = useCallback(async (fn, done) => {
    setError(""); setMsg("");
    try { const r = await fn(); if (done) setMsg(typeof done === "function" ? done(r) : done); return r; } catch (e) { setError(e.message); return null; }
  }, []);
  return { error, msg, call, setMsg, Notice: () => <>{error && <p className="page__warn" role="alert" data-testid="maison-error">{error}</p>}{msg && <p className="page__sub" data-testid="maison-msg">{msg}</p>}</> };
}

function DeviceForm({ initial, prefill, meta, onDone, onCancel }) {
  const [tested, setTested] = useState("");
  const [f, setF] = useState(initial || prefill || { name: "", room: "", type: "light", driver: "tuya", config: {}, aliases: "", confirm: false });
  const { call, Notice } = useCall();
  const setCfg = (k, v) => setF({ ...f, config: { ...f.config, [k]: v } });
  async function submit(e) {
    e.preventDefault();
    const r = await call(() => api(initial ? `/api/home/admin/devices/${initial.id}` : "/api/home/admin/devices", { method: initial ? "PUT" : "POST", body: JSON.stringify(f) }));
    if (r) onDone();
  }
  const test = async (action) => {
    setTested("Test en cours…");
    try { const r = await api("/api/home/admin/devices/test", { method: "POST", body: JSON.stringify({ driver: f.driver, type: f.type, config: f.config, action }) }); setTested(`✔ L'appareil répond${r.on === true ? " (allumé)" : r.on === false ? " (éteint)" : ""}.`); }
    catch (e) { setTested(`✖ ${e.message}`); }
  };
  return (
    <form className="agentform" onSubmit={submit} data-testid="device-form">
      <label className="field"><span>Nom *</span><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="dev-name" /></label>
      <label className="field"><span>Pièce</span><input value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })} placeholder="Salon" data-testid="dev-room" /></label>
      <label className="field"><span>Type</span><select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} data-testid="dev-type">{Object.entries(meta.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label className="field"><span>Pilote</span><select value={f.driver} onChange={(e) => setF({ ...f, driver: e.target.value, config: Object.fromEntries(Object.entries(f.config).filter(([k]) => k === "ip" || k === "mac")) })} data-testid="dev-driver">{meta.drivers.map((d) => <option key={d} value={d}>{DRIVER_NAMES[d] || d}</option>)}</select></label>
      {FIELDS[f.driver].map(([k, label, type]) => (
        <label className="field" key={k}><span>{label}</span><input type={type || "text"} value={f.config[k] ?? ""} onChange={(e) => setCfg(k, e.target.value)} autoComplete="off" data-testid={`dev-cfg-${k}`} /></label>
      ))}
      <label className="field"><span>Autres noms (séparés par une virgule)</span><input value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} placeholder="liseuse, grande lampe" /></label>
      <label className="field"><span><input type="checkbox" checked={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.checked })} /> Toujours demander confirmation avant qu'EVA le commande</span></label>
      <div className="agentform__actions">
        <button className="btn" type="button" onClick={() => test("state")} data-testid="dev-test-state">Tester (état)</button>
        <button className="btn" type="button" onClick={() => test("on")} data-testid="dev-test-on">Tester : allumer</button>
        <button className="btn" type="button" onClick={() => test("off")} data-testid="dev-test-off">Tester : éteindre</button>
      </div>
      {tested && <p className="page__sub" data-testid="dev-test-result">{tested}</p>}
      <div className="agentform__actions">
        <button className="btn btn--primary" type="submit" data-testid="dev-save">{initial ? "Enregistrer" : "Ajouter"}</button>
        <button className="btn" type="button" onClick={onCancel}>Annuler</button>
      </div>
      <Notice />
    </form>
  );
}

function TuyaImport({ onDone }) {
  const [st, setSt] = useState(null); const [f, setF] = useState({ region: "eu", key: "", secret: "", device_id: "" });
  const [list, setList] = useState(null); const [sel, setSel] = useState({}); const [room, setRoom] = useState("");
  const { call, Notice } = useCall();
  useEffect(() => { api("/api/home/tuya").then(setSt).catch(() => {}); }, []);
  const save = async (e) => { e.preventDefault(); if (await call(() => api("/api/home/admin/tuya/creds", { method: "POST", body: JSON.stringify(f) }), "Compte Tuya enregistré.")) setSt(await api("/api/home/tuya")); };
  const fetchList = async () => { const r = await call(() => api("/api/home/admin/tuya/devices", { method: "POST" })); if (r) setList(r.devices); };
  const imp = async () => { const ids = Object.keys(sel).filter((k) => sel[k]); const r = await call(() => api("/api/home/admin/tuya/import", { method: "POST", body: JSON.stringify({ ids, room }) }), (x) => `${x.added.length} appareil(s) importé(s).`); if (r) { setList(null); setSel({}); onDone(); } };
  return (
    <details className="card" data-testid="tuya-import">
      <summary>Importer mes appareils Tuya / Smart Life</summary>
      <p className="page__sub">Crée un compte gratuit sur iot.tuya.com (projet « Smart Home », lie ton application Smart Life avec le code QR), puis recopie l'Access ID, l'Access Secret et l'ID d'un de tes appareils (visible dans l'appli). EVA récupère tous tes appareils avec leurs clés locales ; ils se pilotent d'abord via le cloud Tuya ; pour un pilotage local (plus rapide, sans Internet), ouvre l'appareil (Modifier) et renseigne son adresse IP — l'onglet Réseau repère les appareils Tuya (port 6668).</p>
      <form className="agentform" onSubmit={save}>
        <label className="field"><span>Région</span><select value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })}>{["eu", "us", "cn", "in", "us-e", "eu-w"].map((r) => <option key={r}>{r}</option>)}</select></label>
        <label className="field"><span>Access ID {st?.configured ? `(enregistré : ${st.key})` : ""}</span><input value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} autoComplete="off" /></label>
        <label className="field"><span>Access Secret</span><input type="password" value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value })} autoComplete="off" /></label>
        <label className="field"><span>ID d'un appareil</span><input value={f.device_id} onChange={(e) => setF({ ...f, device_id: e.target.value })} autoComplete="off" /></label>
        <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!f.key || !f.secret || !f.device_id}>Enregistrer</button>
          {st?.configured && <button className="btn" type="button" onClick={fetchList} data-testid="tuya-fetch">Récupérer mes appareils</button>}</div>
      </form>
      {list && (
        <div style={{ marginTop: 10 }}>
          <ul className="pj-trash__list">{list.map((d) => <li key={d.device_id}><label><input type="checkbox" disabled={d.already} checked={!!sel[d.device_id]} onChange={(e) => setSel({ ...sel, [d.device_id]: e.target.checked })} /> {d.name}{d.already ? " (déjà importé)" : ""}</label></li>)}</ul>
          <div className="pj-row"><input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Pièce pour ces appareils" /><button className="btn btn--primary" onClick={imp} disabled={!Object.values(sel).some(Boolean)}>Importer</button></div>
        </div>
      )}
      <Notice />
    </details>
  );
}

function HueImport({ onDone }) {
  const [ponts, setPonts] = useState([]); const [ip, setIp] = useState(""); const [lampes, setLampes] = useState(null);
  const [pont, setPont] = useState(""); const [sel, setSel] = useState({}); const [room, setRoom] = useState("");
  const { call, Notice } = useCall();
  const load = () => api("/api/home/admin/hue").then((r) => setPonts(r.ponts)).catch(() => {});
  useEffect(() => { load(); }, []);
  const appairer = async (e) => { e.preventDefault(); if (await call(() => api("/api/home/admin/hue/appairer", { method: "POST", body: JSON.stringify({ ip }) }), (r) => `Pont « ${r.nom} » appairé.`)) { setIp(""); load(); } };
  const voir = async (p) => { const r = await call(() => api(`/api/home/admin/hue/${p}/lampes`)); if (r) { setPont(p); setLampes(r.lampes); setSel(Object.fromEntries(r.lampes.map((l) => [l.id, !l.deja]))); } };
  const imp = async () => { const ids = Object.keys(sel).filter((k) => sel[k]); const r = await call(() => api(`/api/home/admin/hue/${pont}/importer`, { method: "POST", body: JSON.stringify({ ids, piece: room }) }), (x) => `${x.ajoutees.length} lampe(s) ajoutée(s).`); if (r) { setLampes(null); onDone(); } };
  const oublier = (p) => confirmer(`Oublier le pont ${p.nom} ? (les lampes déjà ajoutées restent mais ne répondront plus)`).then((ok) => ok && (call(() => api(`/api/home/admin/hue/${p.ip}`, { method: "DELETE" })).then(load)));
  return (
    <details className="card" data-testid="hue-import">
      <summary>Philips Hue (sans Home Assistant)</summary>
      <p className="page__sub">EVA parle directement au pont Hue sur ton réseau. Repère son adresse IP (appli Hue › Paramètres › Ponts Hue, ou onglet Réseau), <b>appuie sur le bouton rond du pont</b>, puis clique sur « Appairer » dans les 30 secondes.</p>
      {ponts.map((p) => (
        <div className="pj-row" key={p.ip}><span>💡 <b>{p.nom}</b> · {p.ip}</span>
          <button className="btn" onClick={() => voir(p.ip)} data-testid="hue-lampes">Voir les lampes</button>
          <button className="btn btn--ghost" onClick={() => oublier(p)}>Oublier</button></div>
      ))}
      <form className="pj-row" onSubmit={appairer}><input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="IP du pont (ex. 192.168.1.20)" data-testid="hue-ip" />
        <button className="btn btn--primary" type="submit" disabled={!ip.trim()} data-testid="hue-appairer">Appairer</button></form>
      {lampes && (
        <div style={{ marginTop: 10 }}>
          <ul className="pj-trash__list">{lampes.map((l) => <li key={l.id}><label><input type="checkbox" disabled={l.deja} checked={!!sel[l.id]} onChange={(e) => setSel({ ...sel, [l.id]: e.target.checked })} /> {l.nom}{l.couleur ? " 🎨" : ""}{!l.joignable ? " (injoignable)" : ""}{l.deja ? " (déjà ajoutée)" : ""}</label></li>)}</ul>
          <div className="pj-row"><input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Pièce pour ces lampes" /><button className="btn btn--primary" onClick={imp} disabled={!Object.values(sel).some(Boolean)} data-testid="hue-importer">Ajouter</button></div>
        </div>
      )}
      <Notice />
    </details>
  );
}

function HaImport({ onDone }) {
  const [open, setOpen] = useState(false); const [list, setList] = useState(null); const [pick, setPick] = useState({}); const [names, setNames] = useState({});
  const [cfg, setCfg] = useState(null); const [busy, setBusy] = useState(false);
  const { call, Notice } = useCall();
  const fetchList = async () => {
    setBusy(true);
    try { const c = await api("/api/home/admin/ha/candidates", { method: "POST" }); setList(c.entities); setCfg(null); setPick(Object.fromEntries(c.entities.map((e) => [e.entity_id, !e.already]))); }
    catch (e) { if (/configur|Jeton|injoignable|Adresse/i.test(e.message)) setCfg({ url: "", token: "", err: e.message }); else setCfg({ url: "", token: "", err: e.message }); }
    setBusy(false);
  };
  const saveCfg = async (ev) => { ev.preventDefault(); const r = await call(() => api("/api/homeassistant", { method: "PUT", body: JSON.stringify({ url: cfg.url, token: cfg.token }) })); if (r) fetchList(); };
  const importPicked = async () => {
    const items = list.filter((e) => pick[e.entity_id]).map((e) => ({ entity_id: e.entity_id, name: names[e.entity_id] ?? e.name, room: e.room }));
    const r = await call(() => api("/api/home/admin/ha/import", { method: "POST", body: JSON.stringify({ items }) }), (x) => `${x.added.length} ajouté(s)${x.skipped.length ? ` · ${x.skipped.length} ignoré(s)` : ""}.`);
    if (r) { setList(null); setOpen(false); onDone(); }
  };
  if (!open) return <div className="card"><span className="card__label">Home Assistant</span><p className="page__sub">Si tu utilises Home Assistant, EVA reprend tes lumières, prises, volets, chauffages… avec leurs pièces, et les pilote via Home Assistant.</p><div className="pj-row"><button className="btn btn--primary" onClick={() => { setOpen(true); fetchList(); }} data-testid="ha-open">Importer depuis Home Assistant</button></div></div>;
  return (
    <div className="card" data-testid="ha-import">
      <span className="card__label">Importer depuis Home Assistant</span>
      {busy && <p className="page__sub">Lecture de Home Assistant…</p>}
      {cfg && (
        <form className="agentform" onSubmit={saveCfg}>
          {cfg.err && <p className="page__warn">{cfg.err}</p>}
          <label className="field"><span>Adresse de Home Assistant</span><input value={cfg.url} onChange={(e) => setCfg({ ...cfg, url: e.target.value })} placeholder="http://192.168.1.20:8123" data-testid="ha-url" /></label>
          <label className="field"><span>Jeton d'accès longue durée (Home Assistant › ton profil › Sécurité)</span><input type="password" value={cfg.token} onChange={(e) => setCfg({ ...cfg, token: e.target.value })} data-testid="ha-token" autoComplete="off" /></label>
          <div className="agentform__actions"><button className="btn btn--primary" type="submit" data-testid="ha-connect">Connecter</button><button className="btn" type="button" onClick={() => setOpen(false)}>Annuler</button></div>
        </form>
      )}
      {list && (
        <>
          <p className="page__sub">{list.length} entité(s) commandable(s). Coche celles à ajouter ; tu peux renommer. Les serrures, alarmes, portails et garages ne sont jamais proposés.</p>
          <ul className="pj-trash__list" data-testid="ha-list">
            {list.map((e) => <li key={e.entity_id}><label><input type="checkbox" disabled={e.already} checked={!!pick[e.entity_id]} onChange={(ev) => setPick({ ...pick, [e.entity_id]: ev.target.checked })} /> <input defaultValue={e.name} disabled={e.already} aria-label={`Nom ${e.entity_id}`} onChange={(ev) => setNames({ ...names, [e.entity_id]: ev.target.value })} /> <small>{e.room || "sans pièce"} · {e.entity_id}{e.already ? " — déjà ajouté" : ""}</small></label></li>)}
            {!list.length && <li><span>Aucune entité commandable trouvée.</span></li>}
          </ul>
          <div className="pj-row"><button className="btn btn--primary" onClick={importPicked} disabled={!Object.values(pick).some(Boolean)} data-testid="ha-import-go">Ajouter la sélection</button><button className="btn" onClick={() => setOpen(false)}>Fermer</button></div>
        </>
      )}
      <Notice />
    </div>
  );
}

function DevicesTab({ admin }) {
  const [data, setData] = useState(null); const [edit, setEdit] = useState(null); const [adding, setAdding] = useState(false); const [prefill, setPrefill] = useState(null); const [states, setStates] = useState({});
  const { call, Notice } = useCall();
  const load = useCallback(async () => { try { setData(await api("/api/home/devices")); } catch { /* affiché ailleurs */ } }, []);
  useEffect(() => { load(); }, [load]);
  const act = (d, action, value) => call(async () => { const r = await api(`/api/home/devices/${d.id}/control`, { method: "POST", body: JSON.stringify({ action, value }) }); if (action === "state") setStates((s) => ({ ...s, [d.id]: r.on })); return r; }, action === "state" ? "" : `${d.name} : ${action} envoyé.`);
  const del = async (d) => { if ((await confirmer(`Supprimer « ${d.name} » ?`))) call(() => api(`/api/home/admin/devices/${d.id}`, { method: "DELETE" })).then(load); };
  if (!data) return null;
  const rooms = [...new Set(data.devices.map((d) => d.room || "Sans pièce"))];
  return (
    <div data-testid="devices-tab">
      {admin && <MaisonDiscover onChanged={load} onManual={(o) => { setAdding(true); setPrefill({ name: o.hostname ? o.hostname.split(".")[0] : "", room: "", type: "light", driver: (o.vendor || "").includes("Espressif") || (o.vendor || "").includes("Tuya") ? "tuya" : "shelly", config: { ip: o.ip, ...(o.mac ? { mac: o.mac } : {}) }, aliases: "", confirm: false }); }} />}
      {admin && <HueImport onDone={load} />}
      {admin && <HaImport onDone={load} />}
      {rooms.map((room) => (
        <div className="card" key={room}>
          <span className="card__label">{room}</span>
          <ul className="pj-trash__list">
            {data.devices.filter((d) => (d.room || "Sans pièce") === room).map((d) => (
              <li key={d.id} data-testid={`device-${d.name}`}>
                <span><b>{d.name}</b> — {data.types[d.type]} · {DRIVER_NAMES[d.driver]}{states[d.id] === true ? " · allumé" : states[d.id] === false ? " · éteint" : ""}</span>
                <button className="btn btn--primary" onClick={() => act(d, "on")}>Allumer</button>
                {d.driver !== "wol" && <button className="btn" onClick={() => act(d, "off")}>Éteindre</button>}
                <button className="btn btn--ghost" onClick={() => act(d, "state")}>État</button>
                {d.type === "light" && d.driver !== "wol" && <input type="range" min="1" max="100" defaultValue="100" aria-label={`Luminosité ${d.name}`} onMouseUp={(e) => act(d, "brightness", e.target.value)} onTouchEnd={(e) => act(d, "brightness", e.target.value)} />}
                {admin && <button className="btn btn--ghost" onClick={() => setEdit({ ...d })}>Modifier</button>}
                {admin && <button className="btn btn--danger" onClick={() => del(d)}>Supprimer</button>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {!data.devices.length && <p className="page__sub">Aucun appareil pour l'instant.{admin ? " Lance la recherche ci-dessus, ou importe tes appareils Tuya." : ""}</p>}
      <Notice />
      {admin && (edit
        ? <div className="card"><span className="card__label">Modifier « {edit.name} »</span><DeviceForm initial={edit} meta={data} onDone={() => { setEdit(null); load(); }} onCancel={() => setEdit(null)} /></div>
        : adding
          ? <div className="card"><span className="card__label">Nouvel appareil (réglage manuel)</span><DeviceForm prefill={prefill} meta={data} onDone={() => { setAdding(false); setPrefill(null); load(); }} onCancel={() => { setAdding(false); setPrefill(null); }} /></div>
          : <div className="pj-row"><button className="btn btn--primary" onClick={() => setAdding(true)} data-testid="dev-add">Ajouter à la main</button></div>)}
      {admin && <TuyaImport onDone={load} />}
    </div>
  );
}

function ScenesTab({ admin }) {
  const [data, setData] = useState(null); const [form, setForm] = useState(null);
  const { call, Notice } = useCall();
  const load = useCallback(async () => { try { setData(await api("/api/home/devices")); } catch { /* ignoré */ } }, []);
  useEffect(() => { load(); }, [load]);
  if (!data) return null;
  const run = (s) => call(() => api(`/api/home/scenes/${s.id}/run`, { method: "POST" }), (r) => `Scène « ${s.name} » : ${r.results.filter((x) => x.ok).length}/${r.results.length} étape(s) réussie(s).${r.results.some((x) => !x.ok) ? " Erreurs : " + r.results.filter((x) => !x.ok).map((x) => `${x.device} (${x.error})`).join(" ; ") : ""}`);
  const save = async (e) => { e.preventDefault(); if (await call(() => api(form.id ? `/api/home/admin/scenes/${form.id}` : "/api/home/admin/scenes", { method: form.id ? "PUT" : "POST", body: JSON.stringify({ name: form.name, actions: form.actions }) }))) { setForm(null); load(); } };
  const setAct = (i, patch) => setForm({ ...form, actions: form.actions.map((a, j) => (i === j ? { ...a, ...patch } : a)) });
  return (
    <div data-testid="scenes-tab">
      <div className="card">
        <ul className="pj-trash__list">
          {data.scenes.map((s) => (
            <li key={s.id} data-testid={`scene-${s.name}`}><span><b>{s.name}</b> — {s.actions.length} étape(s)</span>
              <button className="btn btn--primary" onClick={() => run(s)}>Lancer</button>
              {admin && <button className="btn btn--ghost" onClick={() => setForm({ ...s })}>Modifier</button>}
              {admin && <button className="btn btn--danger" onClick={() => confirmer(`Supprimer la scène « ${s.name} » ?`).then((ok) => ok && (call(() => api(`/api/home/admin/scenes/${s.id}`, { method: "DELETE" })).then(load)))}>Supprimer</button>}
            </li>
          ))}
          {!data.scenes.length && <li><span>Aucune scène. Une scène regroupe plusieurs actions (« soirée cinéma » : éteindre le plafonnier, lampe à 20 %…).</span></li>}
        </ul>
      </div>
      <Notice />
      {admin && (form
        ? (
          <form className="card agentform" onSubmit={save} data-testid="scene-form">
            <label className="field"><span>Nom de la scène</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="scene-name" /></label>
            {form.actions.map((a, i) => (
              <div className="pj-row" key={i}>
                <select value={a.device} onChange={(e) => setAct(i, { device: e.target.value })} data-testid={`scene-dev-${i}`}><option value="">— appareil —</option>{data.devices.map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}</select>
                <select value={a.action} onChange={(e) => setAct(i, { action: e.target.value })} data-testid={`scene-act-${i}`}>{ACTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                {["brightness", "color", "temperature"].includes(a.action) && <input value={a.value ?? ""} onChange={(e) => setAct(i, { value: e.target.value })} placeholder="valeur" style={{ maxWidth: 110 }} />}
                <button type="button" className="btn btn--ghost" onClick={() => setForm({ ...form, actions: form.actions.filter((_, j) => j !== i) })}>Retirer</button>
              </div>
            ))}
            <div className="agentform__actions">
              <button type="button" className="btn" onClick={() => setForm({ ...form, actions: [...form.actions, { device: "", action: "off" }] })} data-testid="scene-add-step">Ajouter une étape</button>
              <button className="btn btn--primary" type="submit" data-testid="scene-save">Enregistrer la scène</button>
              <button type="button" className="btn" onClick={() => setForm(null)}>Annuler</button>
            </div>
          </form>
        )
        : <div className="pj-row"><button className="btn btn--primary" onClick={() => setForm({ name: "", actions: [{ device: "", action: "off" }] })} data-testid="scene-new">Nouvelle scène</button></div>)}
    </div>
  );
}


const JOURS_COURTS = ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"];
const ROUTINE_VIDE = { nom: "", declencheur: { type: "heure", heure: "22:00", jours: [0, 1, 2, 3, 4, 5, 6] }, actions: [{ type: "scene", scene: "" }] };

// Routines : à une heure ou quand un capteur change, EVA lance une scène, pilote un appareil, fait une annonce ou prévient.
function RoutinesTab({ admin }) {
  const [lst, setLst] = useState(null); const [scenes, setScenes] = useState([]); const [form, setForm] = useState(null);
  const { call, Notice } = useCall();
  const load = useCallback(async () => {
    try { setLst((await api("/api/home/routines")).routines); } catch { setLst([]); }
    try { const d = await api("/api/home/devices"); setScenes(d.scenes || []); } catch { /* ignoré */ }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!lst) return null;
  const save = async (e) => {
    e.preventDefault();
    const body = { nom: form.nom, declencheur: form.declencheur, actions: form.actions, actif: form.actif ?? true };
    if (await call(() => api(form.id ? `/api/home/routines/${form.id}` : "/api/home/routines", { method: form.id ? "PATCH" : "POST", body: JSON.stringify(body) }))) { setForm(null); load(); }
  };
  const decl = form?.declencheur;
  const setDecl = (p) => setForm({ ...form, declencheur: { ...form.declencheur, ...p } });
  const setAct = (i, p) => setForm({ ...form, actions: form.actions.map((a, j) => (i === j ? { ...a, ...p } : a)) });
  return (
    <div data-testid="routines-tab">
      <div className="card">
        <p className="page__sub">Une routine se lance toute seule : à une heure (« tous les soirs à 22 h → scène Bonne nuit ») ou quand un capteur de Home Assistant change (« température du salon &gt; 26 → ventilateur », « porte du garage ouverte → préviens-moi »). Tu peux aussi les créer en parlant à EVA. Ce qui est sensible (volets, ordinateurs) n'est jamais lancé seul : EVA te prévient à la place.</p>
        <ul className="pj-trash__list">
          {lst.map((r) => (
            <li key={r.id} className={r.actif ? "" : "is-off"} data-testid={`routine-${r.nom}`}>
              <span><b>{r.actif ? "" : "⏸ "}{r.nom}</b><small className="page__sub" style={{ display: "block" }}>{r.description}{r.dernier ? ` · dernière fois : ${new Date(r.dernier.ts * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} (${r.dernier.compte.join(", ")})` : ""}</small></span>
              <span className="sat-actions">
                <button className="btn" onClick={() => call(() => api(`/api/home/routines/${r.id}/lancer`, { method: "POST" }), (x) => `Fait : ${x.fait.join(", ")}`).then(load)}>Essayer</button>
                {admin && <button className="btn btn--ghost" onClick={() => call(() => api(`/api/home/routines/${r.id}`, { method: "PATCH", body: JSON.stringify({ actif: !r.actif }) })).then(load)}>{r.actif ? "Pause" : "Activer"}</button>}
                {admin && <button className="btn btn--ghost" onClick={() => setForm({ ...r })}>Modifier</button>}
                {admin && <button className="btn btn--danger" onClick={() => confirmer(`Supprimer la routine « ${r.nom} » ?`).then((ok) => ok && (call(() => api(`/api/home/routines/${r.id}`, { method: "DELETE" })).then(load)))}>Supprimer</button>}
              </span>
            </li>
          ))}
          {!lst.length && <li><span>Aucune routine pour l'instant.</span></li>}
        </ul>
      </div>
      <Notice />
      {admin && (form ? (
        <form className="card agentform" onSubmit={save} data-testid="routine-form">
          <label className="field"><span>Nom</span><input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} placeholder="Bonne nuit" data-testid="routine-nom" /></label>
          <span className="card__label">Quand ?</span>
          <div className="pj-row">
            <select value={decl.type} onChange={(e) => setForm({ ...form, declencheur: e.target.value === "heure" ? ROUTINE_VIDE.declencheur : { type: "capteur", entite: "", condition: ">", valeur: "" } })}>
              <option value="heure">À une heure</option><option value="capteur">Quand un capteur change</option>
            </select>
            {decl.type === "heure" ? (<>
              <input type="time" value={decl.heure} onChange={(e) => setDecl({ heure: e.target.value })} data-testid="routine-heure" />
              {JOURS_COURTS.map((j, i) => (
                <label key={j} className="page__sub"><input type="checkbox" checked={decl.jours.includes(i)} onChange={() => setDecl({ jours: decl.jours.includes(i) ? decl.jours.filter((x) => x !== i) : [...decl.jours, i].sort() })} /> {j}</label>
              ))}
            </>) : (<>
              <input value={decl.entite} onChange={(e) => setDecl({ entite: e.target.value })} placeholder="sensor.salon_temperature" />
              <select value={decl.condition} onChange={(e) => setDecl({ condition: e.target.value })}>{[">", "<", ">=", "<=", "=", "!="].map((c) => <option key={c}>{c}</option>)}</select>
              <input value={decl.valeur} onChange={(e) => setDecl({ valeur: e.target.value })} placeholder="26 / on / below_horizon" style={{ maxWidth: 150 }} />
            </>)}
          </div>
          <span className="card__label">Alors…</span>
          {form.actions.map((a, i) => (
            <div className="pj-row" key={i}>
              <select value={a.type} onChange={(e) => setAct(i, { type: e.target.value })}>
                <option value="scene">Lancer la scène</option><option value="appareil">Piloter l'appareil</option><option value="annonce">Annoncer</option><option value="notifier">Me prévenir</option>
              </select>
              {a.type === "scene" && <select value={a.scene || ""} onChange={(e) => setAct(i, { scene: e.target.value })}><option value="">— scène —</option>{scenes.map((s) => <option key={s.id}>{s.name}</option>)}</select>}
              {a.type === "appareil" && <><input value={a.appareil || ""} onChange={(e) => setAct(i, { appareil: e.target.value })} placeholder="lampe du salon" />
                <select value={a.action || "on"} onChange={(e) => setAct(i, { action: e.target.value })}>{ACTIONS.filter(([k]) => k !== "state").map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></>}
              {(a.type === "annonce" || a.type === "notifier") && <input value={a.texte || ""} onChange={(e) => setAct(i, { texte: e.target.value })} placeholder={a.type === "annonce" ? "Il est l'heure d'aller au lit" : "La porte du garage est ouverte"} />}
              {a.type === "annonce" && <input value={a.piece || ""} onChange={(e) => setAct(i, { piece: e.target.value })} placeholder="pièce (vide = partout)" style={{ maxWidth: 160 }} />}
              <button type="button" className="btn btn--ghost" onClick={() => setForm({ ...form, actions: form.actions.filter((_, j) => j !== i) })}>Retirer</button>
            </div>
          ))}
          <div className="agentform__actions">
            <button type="button" className="btn" onClick={() => setForm({ ...form, actions: [...form.actions, { type: "notifier", texte: "" }] })}>Ajouter une action</button>
            <button className="btn btn--primary" type="submit" data-testid="routine-save">Enregistrer</button>
            <button type="button" className="btn" onClick={() => setForm(null)}>Annuler</button>
          </div>
        </form>
      ) : <div className="pj-row"><button className="btn btn--primary" onClick={() => setForm(JSON.parse(JSON.stringify(ROUTINE_VIDE)))} data-testid="routine-new">Nouvelle routine</button></div>)}
    </div>
  );
}

function PrintersTab({ admin }) {
  const [data, setData] = useState(null); const [f, setF] = useState({ name: "", uri: "" }); const [cidr, setCidr] = useState(""); const [found, setFound] = useState(null); const [busy, setBusy] = useState(false);
  const { call, Notice } = useCall();
  const load = useCallback(async () => { try { const d = await api("/api/print/printers"); setData(d); setCidr((c) => c || d.cidr); } catch { /* ignoré */ } }, []);
  useEffect(() => { load(); }, [load]);
  if (!data) return null;
  const add = async (e) => { e.preventDefault(); if (await call(() => api("/api/print/admin/printers", { method: "POST", body: JSON.stringify(f) }), "Imprimante ajoutée."))  { setF({ name: "", uri: "" }); load(); } };
  const scan = async () => { setBusy(true); const r = await call(() => api("/api/print/admin/scan", { method: "POST", body: JSON.stringify({ cidr }) })); setBusy(false); if (r) setFound(r.found); };
  return (
    <div data-testid="printers-tab">
      <div className="card">
        <p className="page__sub">EVA imprime en IPP (AirPrint) depuis le NAS : tu peux donc lui demander d'imprimer d'où que tu sois — une liste de courses, une recette, un fichier de projet.</p>
        <ul className="pj-trash__list">
          {data.printers.map((p) => (
            <li key={p.id} data-testid={`printer-${p.name}`}><span><b>{p.name}</b>{p.is_default ? " (par défaut)" : ""}<br /><small>{p.uri}</small></span>
              <button className="btn btn--ghost" onClick={() => call(() => api(`/api/print/printers/${p.id}/test`, { method: "POST" }), "Page de test envoyée.")} data-testid={`print-test-${p.name}`}>Page de test</button>
              {admin && !p.is_default && <button className="btn btn--ghost" onClick={() => call(() => api(`/api/print/admin/printers/${p.id}/default`, { method: "POST" })).then(load)}>Par défaut</button>}
              {admin && <button className="btn btn--danger" onClick={() => call(() => api(`/api/print/admin/printers/${p.id}`, { method: "DELETE" })).then(load)}>Supprimer</button>}
            </li>
          ))}
          {!data.printers.length && <li><span>Aucune imprimante.</span></li>}
        </ul>
      </div>
      <Notice />
      {admin && (
        <div className="card">
          <span className="card__label">Ajouter une imprimante</span>
          <form className="agentform" onSubmit={add}>
            <label className="field"><span>Nom</span><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Imprimante bureau" data-testid="pr-name" /></label>
            <label className="field"><span>Adresse IPP</span><input value={f.uri} onChange={(e) => setF({ ...f, uri: e.target.value })} placeholder="ipp://192.168.1.50:631/ipp/print" data-testid="pr-uri" /></label>
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!f.name || !f.uri} data-testid="pr-add">Ajouter</button></div>
          </form>
          <div className="pj-row" style={{ marginTop: 8 }}>
            <input value={cidr} onChange={(e) => setCidr(e.target.value)} aria-label="Plage réseau" />
            <button className="btn" onClick={scan} disabled={busy} data-testid="pr-scan">{busy ? "Recherche…" : "Chercher sur le réseau"}</button>
          </div>
          {found && <ul className="pj-trash__list">{found.map((x) => <li key={x.uri}><span>{x.model || "Imprimante"} — <small>{x.uri}</small></span><button className="btn btn--ghost" onClick={() => setF({ name: x.model || "Imprimante", uri: x.uri })}>Utiliser</button></li>)}{!found.length && <li><span>Aucune imprimante IPP trouvée sur cette plage.</span></li>}</ul>}
        </div>
      )}
    </div>
  );
}

function NetworkTab() {
  const [ov, setOv] = useState(null); const [cidr, setCidr] = useState(""); const [deep, setDeep] = useState(false); const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(null); const [out, setOut] = useState(null); const [cmd, setCmd] = useState({});
  const { call, Notice } = useCall();
  const load = useCallback(async () => { try { const d = await api("/api/net/overview"); setOv(d); setCidr((c) => c || d.cidr); } catch { /* ignoré */ } }, []);
  useEffect(() => { load(); }, [load]);
  if (!ov) return null;
  const scan = async () => { setBusy(true); await call(() => api("/api/net/scan", { method: "POST", body: JSON.stringify({ cidr, deep }) })); setBusy(false); load(); };
  const save = async (e) => { e.preventDefault(); if (await call(() => api(form.id ? `/api/net/hosts/${form.id}` : "/api/net/hosts", { method: form.id ? "PUT" : "POST", body: JSON.stringify(form) }), "Machine enregistrée.")) { setForm(null); load(); } };
  const inspect = async (h) => { const r = await call(() => api("/api/net/inspect", { method: "POST", body: JSON.stringify({ host: h.name }) })); if (r) { setOut({ title: `Inspection de ${h.name}`, sections: r.sections }); load(); } };
  const ssh = async (h) => { const r = await call(() => api("/api/net/ssh", { method: "POST", body: JSON.stringify({ host: h.name, command: cmd[h.id] }) })); if (r) { setOut({ title: `${h.username}@${h.name} › ${cmd[h.id]}`, sections: { "Sortie": r.stdout + (r.stderr ? `\n[stderr]\n${r.stderr}` : ""), "Code retour": String(r.exit) } }); load(); } };
  const scanRes = ov.scan;
  return (
    <div data-testid="network-tab">
      <div className="card">
        <span className="card__label">Analyse du réseau</span>
        <p className="page__sub">Pour ajouter des appareils, utilise Appareils › « Appareils trouvés sur ton réseau ». Ici : liste brute des machines. Analyse limitée à ton réseau privé. L'analyse approfondie (adresses MAC, constructeurs, système) utilise nmap dans un conteneur : <code>docker pull instrumentisto/nmap</code> une fois sur le NAS.</p>
        <div className="pj-row">
          <input value={cidr} onChange={(e) => setCidr(e.target.value)} aria-label="Plage réseau" data-testid="net-cidr" />
          <label><input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> approfondie (nmap)</label>
          <button className="btn" onClick={scan} disabled={busy} data-testid="net-scan">{busy ? "Analyse…" : "Analyser le réseau"}</button>
        </div>
        {scanRes && (
          <div className="pj-table" style={{ maxHeight: 340, marginTop: 8 }}>
            <p className="page__sub">{scanRes.hosts.length} appareil(s) sur {scanRes.cidr} — {new Date(scanRes.at).toLocaleString("fr-FR")}</p>
            <table data-testid="net-table"><thead><tr><th>Adresse</th><th>Nom</th><th>Constructeur</th><th>MAC</th><th>Ports ouverts</th></tr></thead>
              <tbody>{scanRes.hosts.map((h) => <tr key={h.ip}><td>{h.ip}</td><td>{h.known_as || h.hostname}</td><td>{h.vendor}</td><td>{h.mac}</td><td>{h.ports.map((p) => p.service || p.port).join(", ")}</td></tr>)}</tbody></table>
          </div>
        )}
      </div>
      <div className="card">
        <span className="card__label">Machines accessibles (SSH)</span>
        <p className="page__sub">Les accès que tu enregistres ici (souvent <b>root</b>) servent à EVA pour inspecter ou administrer la machine — chaque commande demande ton accord quand EVA la propose, et tout est tracé dans le Journal d'accès. L'empreinte de la machine est mémorisée à la première connexion ; si elle change, EVA refuse de se connecter.</p>
        <ul className="pj-trash__list">
          {ov.hosts.map((h) => (
            <li key={h.id} data-testid={`host-${h.name}`}><span><b>{h.name}</b> — {h.username}@{h.address}:{h.port}{h.host_key ? ` · empreinte ${h.host_key.slice(0, 18)}…` : " · empreinte pas encore mémorisée"}</span>
              <button className="btn btn--primary" onClick={() => inspect(h)} data-testid={`inspect-${h.name}`}>Inspecter</button>
              <input value={cmd[h.id] || ""} onChange={(e) => setCmd({ ...cmd, [h.id]: e.target.value })} placeholder="commande…" style={{ minWidth: 160 }} data-testid={`cmd-${h.name}`} />
              <button className="btn" disabled={!cmd[h.id]} onClick={() => ssh(h)} data-testid={`run-${h.name}`}>Exécuter</button>
              {h.host_key && <button className="btn btn--ghost" onClick={() => call(() => api(`/api/net/hosts/${h.id}/forget-key`, { method: "POST" }), "Empreinte oubliée.").then(load)}>Oublier l'empreinte</button>}
              <button className="btn btn--ghost" onClick={() => setForm({ ...h, secret: "" })}>Modifier</button>
              <button className="btn btn--danger" onClick={() => confirmer(`Supprimer « ${h.name} » ?`).then((ok) => ok && (call(() => api(`/api/net/hosts/${h.id}`, { method: "DELETE" })).then(load)))}>Supprimer</button>
            </li>
          ))}
          {!ov.hosts.length && <li><span>Aucune machine enregistrée.</span></li>}
        </ul>
        {out && (
          <div className="card" data-testid="net-output"><span className="card__label">{out.title}</span>
            {Object.entries(out.sections).map(([k, v]) => <div key={k}><b>{k}</b><pre className="pj-text" style={{ minHeight: 0, maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap" }}>{v}</pre></div>)}
            <button className="btn" onClick={() => setOut(null)}>Fermer</button></div>
        )}
        <Notice />
        {form
          ? (
            <form className="agentform" onSubmit={save} data-testid="host-form">
              <label className="field"><span>Nom</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="host-name" /></label>
              <label className="field"><span>Adresse IP</span><input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="host-address" /></label>
              <label className="field"><span>Port SSH</span><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} /></label>
              <label className="field"><span>Utilisateur</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} data-testid="host-user" /></label>
              <label className="field"><span>Connexion par</span><select value={form.auth} onChange={(e) => setForm({ ...form, auth: e.target.value })}><option value="password">Mot de passe</option><option value="key">Clé privée</option></select></label>
              <label className="field"><span>{form.auth === "key" ? "Clé privée (format OpenSSH, sans phrase secrète)" : "Mot de passe"}{form.id ? " — laisse vide pour garder l'actuel" : ""}</span>
                {form.auth === "key" ? <textarea rows={4} value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} /> : <input type="password" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} autoComplete="new-password" data-testid="host-secret" />}</label>
              <div className="agentform__actions"><button className="btn btn--primary" type="submit" data-testid="host-save">Enregistrer</button><button className="btn" type="button" onClick={() => setForm(null)}>Annuler</button></div>
            </form>
          )
          : <div className="pj-row"><button className="btn btn--primary" onClick={() => setForm({ name: "", address: "", port: 22, username: "root", auth: "password", secret: "" })} data-testid="host-new">Ajouter une machine</button></div>}
      </div>
    </div>
  );
}

function HueScenes() {
  const [list, setList] = useState([]); const { call, Notice } = useCall();
  useEffect(() => { api("/api/home/hue/scenes").then((r) => setList(r.scenes || [])).catch(() => {}); }, []);
  if (!list.length) return null;
  return (
    <div className="card" data-testid="hue-scenes"><h3>Scènes Philips Hue</h3>
      <div className="pj-row" style={{ flexWrap: "wrap" }}>{list.map((sc) => <button key={sc.ip + sc.id} className="btn" onClick={() => call(() => api(`/api/home/hue/scenes/${sc.ip}/${sc.groupe}/${sc.id}`, { method: "POST" }), `« ${sc.nom} » lancée.`)}>{sc.piece ? `${sc.piece} · ` : ""}{sc.nom}</button>)}</div>
      <Notice /></div>
  );
}

function PresenceTab({ admin }) {
  const [e, setE] = useState(null); const [pers, setPers] = useState({}); const [nom, setNom] = useState(""); const [busy, setBusy] = useState(false); const [ouvert, setOuvert] = useState({});
  const { call, Notice } = useCall();
  const load = useCallback(async () => {
    try {
      if (admin) { const r = await api("/api/home/admin/presence"); setE(r); setPers(r.reglages || {}); }
      else { const r = await api("/api/home/presence"); setE({ etat: r.personnes, erreur: r.erreur }); }
    } catch (x) {
      setE({ etat: [], erreur: x.status === 404 ? "Cette fonction n'est pas encore disponible sur le serveur : eva-core n'a pas été reconstruit avec la dernière mise à jour (docker compose up -d --build eva-core)." : x.message, indisponible: true });
    }
  }, [admin]);
  useEffect(() => { load(); }, [load]);
  const scan = async () => { setBusy(true); const r = await call(() => api("/api/home/admin/presence/scan", { method: "POST" })); setBusy(false); if (r) setE({ ...e, ...r }); };
  const save = (p) => call(() => api("/api/home/admin/presence", { method: "PUT", body: JSON.stringify({ personnes: p }) }), "Enregistré.").then((r) => { if (r) { setPers(r.personnes); load(); } });
  const toggle = (n, mac) => { const macs = pers[n].macs.includes(mac) ? pers[n].macs.filter((m) => m !== mac) : [...pers[n].macs, mac]; save({ ...pers, [n]: { macs } }); };
  if (!e) return <p className="page__sub">Chargement…</p>;
  const etat = e.etat || [];
  return (
    <div className="pj-grid">
      <div className="card" data-testid="presence-etat"><h3>Qui est à la maison ?</h3>
        <p className="page__sub">EVA regarde quels téléphones sont connectés au wifi (toutes les 2 minutes). Demande-lui « qui est à la maison ? ».</p>
        {etat.length ? <ul className="pj-trash__list">{etat.map((p) => <li key={p.nom}>{p.present ? "🏠" : "🚶"} <b>{p.nom}</b> — {p.present ? (p.piece ? `à la maison, ${p.piece.toLowerCase()}` : "à la maison") : p.vu_il_y_a_min != null ? `parti(e) (vu il y a ${p.vu_il_y_a_min} min)` : "pas vu"}</li>)}</ul>
          : <p className="page__sub">Personne n'est inscrit pour l'instant.</p>}
        {e.erreur && <p className="page__warn">{e.erreur}</p>}
      </div>
      {admin && !e.indisponible && (
        <div className="card" data-testid="presence-reglages"><h3>Téléphones de chacun</h3>
          <p className="page__sub">Ajoute une personne, puis coche son téléphone parmi les appareils vus sur le réseau. Astuce : sur iPhone/Android, désactive « adresse privée / MAC aléatoire » pour le wifi de la maison, sinon l'adresse change.</p>
          <form className="pj-row" onSubmit={(ev) => { ev.preventDefault(); if (nom.trim() && !pers[nom.trim()]) { setPers({ ...pers, [nom.trim()]: { macs: [] } }); setOuvert({ ...ouvert, [nom.trim()]: true }); setNom(""); } }}>
            <input value={nom} onChange={(ev) => setNom(ev.target.value)} placeholder="Prénom" data-testid="presence-nom" /><button className="btn" type="submit">Ajouter</button>
            <button className="btn" type="button" onClick={scan} disabled={busy} data-testid="presence-scan">{busy ? "Recherche…" : "Scanner maintenant"}</button></form>
          <div className="routergrid" data-testid="presence-auto">
            {[["depart", "Quand tout le monde part"], ["arrivee", "Quand quelqu'un rentre (maison vide)"]].map(([k, l]) => (
              <label key={k} className="field"><span>{l}</span>
                <select value={e.automatismes?.[k] || ""} onChange={(ev) => call(() => api("/api/home/admin/presence", { method: "PUT", body: JSON.stringify({ personnes: pers, automatismes: { ...(e.automatismes || {}), [k]: ev.target.value || null } }) }), "Enregistré.").then(load)} data-testid={`presence-${k}`}>
                  <option value="">Ne rien faire</option>
                  {(e.scenes || []).map((sc) => <option key={sc.id} value={sc.id}>Lancer la scène « {sc.nom} »</option>)}
                </select></label>
            ))}
          </div>
          {e.dernier_automatisme && <p className="page__sub">Dernier automatisme : {e.dernier_automatisme.texte}</p>}
          {Object.entries(pers).map(([n, c]) => (
            <details key={n} className="card" open={!!ouvert[n]} onToggle={(ev) => { const v = ev.currentTarget.open; setOuvert((o) => ({ ...o, [n]: v })); }}><summary><b>{n}</b> · {c.macs.length} appareil(s) <button className="btn btn--ghost" onClick={(ev) => { ev.preventDefault(); const p = { ...pers }; delete p[n]; save(p); }}>Retirer</button></summary>
              <ul className="pj-trash__list">
                {[...new Set([...c.macs, ...(e.appareils || []).map((a) => a.mac)])].map((m) => { const a = (e.appareils || []).find((x) => x.mac === m); return (
                  <li key={m}><label><input type="checkbox" checked={c.macs.includes(m)} onChange={() => toggle(n, m)} /> {m}{a ? ` · ${a.ip} · vu il y a ${a.vu_il_y_a_min} min` : " · pas vu récemment"}</label></li>); })}
              </ul>
              {!(e.appareils || []).length && <p className="page__sub">Aucun appareil vu : clique sur « Scanner maintenant ».</p>}
            </details>
          ))}
          <Notice />
        </div>
      )}
      {admin && !e.indisponible && <PresencePieces />}
    </div>
  );
}

// Présence pièce par pièce : un ESP32 par pièce avec le firmware libre ESPresense (Bluetooth), relié par MQTT. Voir MAISON.md.
function PresencePieces() {
  const [d, setD] = useState(null); const [c, setC] = useState(null); const [err, setErr] = useState("");
  const charger = useCallback(() => api("/api/home/admin/espresense").then((x) => { setD(x); setC((v) => v || x.reglages); setErr(""); }).catch((x) => setErr(x.status === 404 ? "" : x.message)), []);
  useEffect(() => { charger(); const t = setInterval(charger, 10000); return () => clearInterval(t); }, [charger]);
  const enregistrer = (chg) => api("/api/home/admin/espresense", { method: "PUT", body: JSON.stringify({ ...c, ...chg }) }).then((x) => { setD(x); setC(x.reglages); }).catch((x) => setErr(x.message));
  if (!d || !c) return err ? <p className="page__warn">{err}</p> : null;
  const personnes = [...new Set(Object.values(c.appareils || {}))];
  return (
    <div className="card" data-testid="presence-pieces"><h3>Pièce par pièce (ESP32)</h3>
      <p className="page__sub">Un ESP32 par pièce (firmware gratuit <b>ESPresense</b>) repère en Bluetooth les téléphones et montres de la famille : EVA sait alors <b>dans quelle pièce</b> est chacun (« où est Léa ? »), et dit les rappels sur le satellite de la pièce où tu es. Pas-à-pas : MAISON.md, « Présence pièce par pièce ».</p>
      <label className="page__sub"><input type="checkbox" checked={!!c.actif} onChange={(ev) => enregistrer({ actif: ev.target.checked })} data-testid="esp-actif" /> Activer</label>
      {c.actif && (
        <>
          <div className="routergrid">
            <label className="field"><span>Courtier MQTT</span><input value={c.hote} onChange={(ev) => setC({ ...c, hote: ev.target.value })} placeholder="eva-mqtt" /></label>
            <label className="field"><span>Port</span><input type="number" value={c.port} onChange={(ev) => setC({ ...c, port: ev.target.value })} /></label>
            <label className="field"><span>Utilisateur (facultatif)</span><input value={c.utilisateur} onChange={(ev) => setC({ ...c, utilisateur: ev.target.value })} /></label>
            <label className="field"><span>Mot de passe</span><input type="password" value={c.mot_de_passe} onChange={(ev) => setC({ ...c, mot_de_passe: ev.target.value })} /></label>
          </div>
          <div className="pj-row"><button className="btn" onClick={() => enregistrer({})}>Enregistrer</button>
            <span className={d.etat.connecte ? "page__sub" : "page__warn"}>{d.etat.connecte ? `✅ Connecté au courtier · ${d.etat.messages} message(s) reçu(s) · pièces : ${d.etat.pieces_vues.join(", ") || "aucune encore"}` : d.etat.erreur || "⏳ Connexion au courtier…"}</span></div>
          <span className="card__label" style={{ marginTop: 10 }}>Appareils vus par les ESP32</span>
          {d.appareils.length === 0 ? <p className="page__sub">Aucun pour l'instant. Inscris les téléphones dans la page de chaque ESP32 (bouton « Enroll ») : ils apparaissent ici sous le nom donné.</p> : (
            <ul className="pj-trash__list">{d.appareils.map((a) => (
              <li key={a.id} className="pj-row"><span><b>{a.nom || a.id}</b> <small className="page__sub">{a.id} · {a.piece}, {a.distance} m · il y a {a.vu_il_y_a_s} s</small></span>
                <input list="esp-personnes" value={c.appareils?.[a.id] || ""} placeholder="À qui ?" style={{ maxWidth: 160 }}
                  onChange={(ev) => setC({ ...c, appareils: { ...(c.appareils || {}), [a.id]: ev.target.value } })}
                  onBlur={() => enregistrer({})} data-testid={`esp-qui-${a.id}`} /></li>
            ))}</ul>
          )}
          <datalist id="esp-personnes">{personnes.map((p) => <option key={p} value={p} />)}</datalist>
          {Object.keys(d.pieces).length > 0 && <p className="page__sub">En ce moment : {Object.entries(d.pieces).map(([p, x]) => `${p} → ${x.piece.toLowerCase()}`).join(" · ")}</p>}
        </>
      )}
      {err && <p className="page__warn">{err}</p>}
    </div>
  );
}

const SYSTEMES = [["windows", "🪟 Windows"], ["mac", "🍎 Mac"], ["linux", "🐧 Linux / Raspberry Pi"], ["android", "🤖 Android"]];
const OPTIONS_SAT = [
  ["ecran", "👁️ Écran", "EVA voit l'écran, clique, et peut prendre la main (toujours avec ton accord)"],
  ["fenetre", "💬 Fenêtre flottante", "ce que tu dis et la réponse, dans un coin de l'écran"],
  ["tableau", "🗂️ Tableau au repos", "heure, météo, rendez-vous, colis quand personne ne parle"],
  ["gestes", "✋ Gestes", "devant la webcam : pause, volume, onglets… (l'image ne quitte pas l'ordinateur)"],
  ["local", "🎙️ Éveil local", "« EVA » est reconnu sur la machine : rien n'est envoyé avant"],
];
const systemeDetecte = () => {
  const ua = `${navigator.userAgentData?.platform || ""} ${navigator.platform || ""} ${navigator.userAgent || ""}`.toLowerCase();
  if (ua.includes("android")) return "android";
  if (ua.includes("win")) return "windows";
  if (ua.includes("mac") && !/iphone|ipad/.test(ua)) return "mac";
  return "linux";
};
const versionNum = (v) => String(v || "").split(".").map((x) => parseInt(x, 10) || 0);
const plusAncienne = (a, b) => { const x = versionNum(a); const y = versionNum(b); for (let i = 0; i < 3; i += 1) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) < (y[i] || 0); } return false; };

function QrCode({ texte }) {
  const [src, setSrc] = useState("");
  useEffect(() => { import("qrcode").then((q) => q.toDataURL(texte, { margin: 1, width: 220 })).then(setSrc).catch(() => setSrc("")); }, [texte]);
  return src ? <img src={src} alt="QR code à scanner avec le téléphone" width="220" height="220" style={{ background: "#fff", borderRadius: 8 }} data-testid="sat-qr" /> : null;
}

// Copier : presse-papiers moderne (https), sinon l'ancienne méthode (EVA en http sur le réseau local).
async function copierTexte(t) {
  try { await navigator.clipboard.writeText(t); return true; } catch { /* repli */ }
  try {
    const z = document.createElement("textarea"); z.value = t; z.style.position = "fixed"; z.style.opacity = "0";
    document.body.appendChild(z); z.select(); const ok = document.execCommand("copy"); z.remove(); return ok;
  } catch { return false; }
}

function telecharger(nom, contenu) {
  const url = URL.createObjectURL(new Blob([contenu], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url; a.download = nom; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const DUREES_OPTIONS = { ecran: [2, 5], gestes: [5, 10], local: [1, 3] };

function InstallerSatellite({ sat, durees, onFermer, onFait }) {
  const [systeme, setSysteme] = useState(systemeDetecte);
  const [genre, setGenre] = useState(["linux", "android"].includes(systemeDetecte()) ? "piece" : "pc");
  const [opts, setOpts] = useState(() => new Set(["linux", "android"].includes(systemeDetecte()) ? [] : ["ecran", "fenetre"]));
  const [res, setRes] = useState(null);
  const [copie, setCopie] = useState(false);
  const { call, Notice } = useCall();
  const choisirGenre = (g) => { setGenre(g); setOpts(new Set(g === "pc" ? ["ecran", "fenetre"] : [])); };
  const basculer = (o) => setOpts((x) => { const n = new Set(x); if (n.has(o)) n.delete(o); else n.add(o); return n; });
  const dureeTexte = (d, options) => {
    if (!d) return "";
    let [mini, maxi] = [d.min, d.max];
    options.forEach((o) => { const x = DUREES_OPTIONS[o]; if (x) { mini += x[0]; maxi += x[1]; } });
    return `Installation : environ ${mini} à ${maxi} minutes${d.note ? ` (${d.note})` : ""}.`;
  };
  const preparer = async () => {
    if (sat.en_ligne && !(await confirmer(`« ${sat.nom} » est en ligne. Le préparer à nouveau crée une nouvelle clé : l'installation actuelle cessera de marcher jusqu'à ce que tu relances l'installateur. Continuer ?`))) return;
    const r = await call(() => api(`/api/home/admin/satellites/${sat.id}/installateur`, { method: "POST", body: JSON.stringify({ systeme, options: genre === "pc" ? [...opts] : [...opts].filter((o) => o === "local"), eva: window.location.origin }) }));
    if (r) { setRes(r); if (systeme === "windows") telecharger(r.fichier.nom, r.fichier.contenu); onFait?.(); }
  };
  const copier = async () => { if (await copierTexte(res.commande)) { setCopie(true); setTimeout(() => setCopie(false), 2500); } };
  return (
    <div className="card sat-inst" data-testid="sat-installer">
      <h3>Installer « {sat.nom} »</h3>
      {!res ? (
        <>
          <span className="card__label">1. Sur quel système ?</span>
          <div className="sat-inst__choix" role="radiogroup">
            {SYSTEMES.map(([id, l]) => <button key={id} type="button" className={systeme === id ? "is-on" : ""} onClick={() => { setSysteme(id); if (!["linux", "android"].includes(id) && genre !== "pc") choisirGenre("pc"); }} data-testid={`sat-sys-${id}`}>{l}{id === systemeDetecte() && <small> (cet appareil)</small>}</button>)}
          </div>
          {systeme === "android" ? (
            <p className="page__sub">Un téléphone ou une tablette Android (8 ou plus) devient un satellite : « EVA… » en mains libres (ou bouton Parler), réponses avec la voix d'EVA, annonces, « fais sonner mon téléphone ». Un vieux téléphone posé en charge dans une pièce fait une très bonne enceinte EVA.</p>
          ) : (<>
          <span className="card__label">2. Pour quoi faire ?</span>
          <div className="sat-inst__choix">
            <button type="button" className={genre === "pc" ? "is-on" : ""} onClick={() => choisirGenre("pc")}>🖥️ Mon ordinateur<small>micro, écran, prise en main</small></button>
            <button type="button" className={genre === "piece" ? "is-on" : ""} onClick={() => choisirGenre("piece")}>🔊 Une enceinte dans une pièce<small>Raspberry Pi, vieux PC sans écran</small></button>
          </div>
          <span className="card__label">3. Options</span>
          <div className="sat-inst__options">
            {OPTIONS_SAT.filter(([id]) => genre === "pc" || id === "local").map(([id, l, aide]) => (
              <label key={id} className="sat-inst__option"><input type="checkbox" checked={opts.has(id)} onChange={() => basculer(id)} data-testid={`sat-opt-${id}`} /><span><b>{l}</b><small>{aide}</small></span></label>
            ))}
          </div>
          </>)}
          <p className="page__sub" data-testid="sat-duree">⏱️ {dureeTexte(durees?.[systeme], systeme === "android" ? [] : genre === "pc" ? [...opts] : [...opts].filter((o) => o === "local"))}</p>
          <div className="agentform__actions">
            <button className="btn btn--primary" onClick={preparer} data-testid="sat-preparer">{systeme === "windows" ? "⬇️ Télécharger l'installateur" : systeme === "android" ? "Préparer le téléphone" : "Préparer la commande"}</button>
            <button className="btn btn--ghost" onClick={onFermer}>Annuler</button>
          </div>
        </>
      ) : (
        <>
          {res.duree && <p className="page__sub">⏱️ {res.duree.texte}</p>}
          {systeme === "android" ? (
            <>
              <p className="page__sub">{res.aide}</p>
              <div className="sat-android">
                <QrCode texte={res.lien} />
                <div className="sat-android__etapes">
                  <p><b>1.</b> Installer l'appli sur le téléphone :</p>
                  {res.apk_present ? <a className="btn" href={res.apk} data-testid="sat-apk">⬇️ Télécharger EVA Satellite (APK)</a>
                    : <p className="page__warn">L'appli n'est pas encore sur ce NAS : installe la dernière mise à jour d'EVA.</p>}
                  <p><b>2.</b> Puis, <b>sur le téléphone</b>, ouvre ce lien (ou scanne le QR code avec l'appareil photo) :</p>
                  <a className="btn btn--primary" href={res.lien} data-testid="sat-lien">📱 Ouvrir dans l'appli</a>
                  <details><summary className="page__sub">ou recopier à la main</summary><pre className="mcpsrv__pre">{`Adresse : ${window.location.origin}\nClé : ${new URLSearchParams(res.lien.split("?")[1]).get("jeton")}`}</pre></details>
                </div>
              </div>
            </>
          ) : systeme === "windows" ? (
            <>
              <p><b>Le fichier {res.fichier.nom} vient d'être téléchargé.</b> Sur l'ordinateur à équiper, double-clique dessus.</p>
              <p className="page__sub">{res.aide}</p>
              <div className="agentform__actions"><button className="btn" onClick={() => telecharger(res.fichier.nom, res.fichier.contenu)}>⬇️ Télécharger à nouveau</button></div>
              <details><summary className="page__sub">ou en commande PowerShell</summary><pre className="mcpsrv__pre">{res.commande}</pre></details>
            </>
          ) : (
            <>
              <p>{res.aide}</p>
              <pre className="mcpsrv__pre" data-testid="sat-commande">{res.commande}</pre>
              <div className="agentform__actions">
                <button className="btn btn--primary" onClick={copier}>{copie ? "✓ Copiée" : "📋 Copier la commande"}</button>
                <button className="btn" onClick={() => telecharger(res.fichier.nom, res.fichier.contenu)}>⬇️ Ou télécharger {res.fichier.nom}</button>
              </div>
            </>
          )}
          <p className="page__sub">Ensuite dis « EVA, quelle heure est-il ? » : le satellite passe 🟢 en ligne ici dans la minute. Il se met ensuite à jour <b>tout seul</b> à chaque nouvelle version d'EVA. La commande contient une clé personnelle : ne la partage pas. <a href={`${window.location.origin}/api/public/satellite/LISEZMOI.txt`} target="_blank" rel="noreferrer">Mode d'emploi complet</a></p>
          <div className="agentform__actions"><button className="btn btn--ghost" onClick={onFermer}>Terminé</button></div>
        </>
      )}
      <Notice />
    </div>
  );
}


// Désinstaller à la main : vrais liens de téléchargement (clic) et commandes avec bouton Copier.
function Desinstallation({ commandes }) {
  const [copie, setCopie] = useState("");
  const copier = async (k, t) => { if (await copierTexte(t)) { setCopie(k); setTimeout(() => setCopie(""), 2500); } };
  return (
    <div className="sat-desinst">
      {[["windows", "🪟 Windows"], ["mac", "🍎 Mac"], ["linux", "🐧 Linux / Raspberry Pi"], ["android", "🤖 Android"]].map(([k, l]) => {
        const c = commandes?.[k] || {};
        return (
          <div key={k} className="sat-desinst__ligne">
            <span className="card__label">{l}</span>
            <p className="page__sub">{c.aide}</p>
            {c.commande && <pre className="mcpsrv__pre">{c.commande}</pre>}
            <div className="pj-row">
              {c.commande && <button className="btn btn--primary" onClick={() => copier(k, c.commande)}>{copie === k ? "✓ Copiée" : "📋 Copier la commande"}</button>}
              {c.fichier && <a className="btn" href={c.fichier} download={c.nom} data-testid={`desinst-${k}`}>⬇️ Télécharger {c.nom}</a>}
            </div>
          </div>
        );
      })}
    </div>
  );
}


// Diagnostic d'un satellite : connecté ? micro assez fort ? qu'a-t-il compris ? dernières erreurs et journal.
function DiagnosticSatellite({ sat, onFermer }) {
  const [d, setD] = useState(null); const [t, setT] = useState(null); const [occupe, setOccupe] = useState(false); const [err, setErr] = useState("");
  const charger = useCallback(() => api(`/api/home/admin/satellites/${sat.id}/diagnostic`, { method: "POST", body: "{}" }).then(setD).catch((e) => setErr(e.message)), [sat.id]);
  useEffect(() => { charger(); }, [charger]);
  const tester = async () => {
    setOccupe(true); setErr("");
    try { setT((await api(`/api/home/admin/satellites/${sat.id}/diagnostic`, { method: "POST", body: JSON.stringify({ test: true }) })).test); charger(); }
    catch (e) { setErr(e.message); } finally { setOccupe(false); }
  };
  const g = d?.diag || {};
  const quand = (ts) => (ts ? new Date(ts * 1000).toLocaleTimeString("fr-FR") : "jamais");
  return (
    <div className="card" data-testid="sat-diag">
      <h3>🩺 Diagnostic « {sat.nom} »</h3>
      {!d ? <p className="page__sub">{err || "Interrogation du satellite…"}</p> : !d.connecte ? (
        <>
          <p className="page__warn">❌ Le satellite n'est pas connecté à EVA (dernier contact : {sat.dernier ? new Date(sat.dernier * 1000).toLocaleString("fr-FR") : "jamais"}).</p>
          <ol className="page__sub">
            <li>Sur la machine, lance le raccourci <b>« EVA démarrer »</b> (bureau), ou redémarre la session.</li>
            <li>Regarde son journal : Windows <code>%USERPROFILE%\eva-satellite\satellite.log</code> ; Linux / Mac <code>~/eva-satellite/satellite.log</code> (Raspberry Pi en service : <code>journalctl -u eva-satellite -n 50</code>).</li>
            <li>« Clé refusée » dans le journal : le satellite a été réinstallé ailleurs → <b>Réinstaller</b> ici avec un nouveau fichier.</li>
            <li>Toujours rien : désinstalle puis réinstalle avec le dernier fichier (Réinstaller).</li>
          </ol>
        </>
      ) : g.error ? <p className="page__warn">{g.error}</p> : (
        <>
          <p>✅ Connecté · version {g.version} · {g.systeme}{g.en_pause ? " · ⏸ en pause" : ""}</p>
          <ul className="page__sub">
            <li>Micro : seuil de parole {g.micro?.seuil}, niveau récent {g.micro?.niveau_recent}{g.micro?.eveil_local ? " · éveil local" : " · éveil par le serveur (Whisper)"}</li>
            <li>Phrases entendues : {g.phrases} · comprises : {g.transcrites} · « EVA » reconnu : {g.eveils} · demandes : {g.commandes}</li>
            <li>Dernière voix entendue : {quand(g.derniere_voix)}{g.dernier_texte !== undefined && <> · compris : « {g.dernier_texte} »</>}</li>
            {g.derniere_erreur && <li className="page__warn">Dernière erreur : {g.derniere_erreur}</li>}
          </ul>
          {g.phrases === 0 && <p className="page__warn">Il n'a encore entendu aucune phrase : micro coupé, mauvais micro (Paramètres son de la machine › micro par défaut), ou trop loin. Fais le test ci-dessous.</p>}
          {g.phrases > 0 && g.eveils === 0 && <p className="page__warn">Il entend des phrases mais jamais « EVA » au début : regarde ce qu'il a compris (« Entendu sans EVA » dans le journal) et dis « EVA » bien distinctement, en premier.</p>}
          <div className="pj-row">
            <button className="btn btn--primary" onClick={tester} disabled={occupe} data-testid="sat-test">{occupe ? "Test en cours (il parle puis écoute 4 s)…" : "🎤 Tester le haut-parleur et le micro"}</button>
            <button className="btn btn--ghost" onClick={charger}>Actualiser</button>
          </div>
          {t && (t.error ? <p className="page__warn">{t.error}</p> : (
            <div className="sat-test">
              <p>🔊 As-tu entendu « Test du satellite » ? Si non : haut-parleur coupé ou mauvaise sortie son sur la machine.</p>
              <p>{t.entendu ? "✅" : "❌"} Micro : niveau {t.niveau} pour un seuil de {t.seuil}{!t.entendu && " → ta voix est trop faible pour lui : rapproche-toi, monte le volume du micro, ou choisis le bon micro dans les réglages son de la machine"}.</p>
              <p>{t.texte ? "✅" : "❌"} Compris : « {t.texte || "rien"} »{t.texte && (t.mot_eveil ? " — « EVA » reconnu ✅" : " — pour lui parler, commence par « EVA »")}</p>
            </div>
          ))}
          <details><summary className="page__sub">Journal du satellite</summary><pre className="mcpsrv__pre" style={{ maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap" }}>{(g.journal || []).join("\n")}</pre></details>
        </>
      )}
      {err && <p className="page__warn">{err}</p>}
      <div className="agentform__actions"><button className="btn btn--ghost" onClick={onFermer}>Fermer</button></div>
    </div>
  );
}

// Mode miroir : écran qui reconnaît la famille (visages appris ici), s'allume quand quelqu'un se présente.
function MiroirTab({ admin }) {
  const [e, setE] = useState(null); const [err, setErr] = useState(""); const [msg, setMsg] = useState("");
  const [qui, setQui] = useState(""); const [prise, setPrise] = useState(0); const videoRef = useRef(null); const fluxRef = useRef(null);
  const charger = useCallback(() => api("/api/miroir/etat").then((d) => { setE(d); setErr(""); }).catch((x) => setErr(x.status === 404 ? "Le mode miroir arrive avec la prochaine reconstruction d'eva-core." : x.message)), []);
  useEffect(() => { charger(); }, [charger]);
  useEffect(() => { if (!e?.telechargement?.en_cours) return undefined; const t = setInterval(charger, 3000); return () => clearInterval(t); }, [e?.telechargement?.en_cours, charger]);
  useEffect(() => () => fluxRef.current?.getTracks().forEach((t) => t.stop()), []);
  const telecharger = () => api("/api/miroir/modeles", { method: "POST" }).then(() => setTimeout(charger, 800)).catch((x) => setErr(x.message));
  const apprendre = async () => {
    setErr(""); setMsg("");
    try {
      const flux = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      fluxRef.current = flux; videoRef.current.srcObject = flux; await videoRef.current.play();
      const images = []; const c = document.createElement("canvas");
      for (let i = 0; i < 6; i++) {
        setPrise(i + 1);
        await new Promise((r) => setTimeout(r, 900));
        c.width = videoRef.current.videoWidth; c.height = videoRef.current.videoHeight;
        c.getContext("2d").drawImage(videoRef.current, 0, 0); images.push(c.toDataURL("image/jpeg", 0.85));
      }
      const r = await api("/api/miroir/visages", { method: "POST", body: JSON.stringify({ qui: qui || undefined, images }) });
      setMsg(`✅ Visage de ${r.qui} appris (${r.photos} photo(s) retenue(s)). Il est reconnu dès maintenant par le miroir.`); charger();
    } catch (x) { setErr(x.name === "NotAllowedError" ? "Caméra refusée : autorise-la dans le navigateur." : x.message); }
    finally { setPrise(0); fluxRef.current?.getTracks().forEach((t) => t.stop()); fluxRef.current = null; }
  };
  const oublier = async (p) => { if (await confirmer(`Effacer le visage de ${p} ? Le miroir ne le reconnaîtra plus.`)) api(`/api/miroir/visages/${encodeURIComponent(p)}`, { method: "DELETE" }).then(charger).catch((x) => setErr(x.message)); };
  const adresse = `${window.location.origin}/?miroir`;
  if (!e) return err ? <p className="page__warn">{err}</p> : <p className="page__sub">Chargement…</p>;
  return (
    <div className="pj-grid">
      <div className="card sat-carte" data-testid="miroir-tab">
        <h3>Miroir intelligent</h3>
        <p className="page__sub">Un écran (une vieille tablette, un PC avec webcam, un écran derrière un miroir sans tain) qui reconnaît la famille : il s'allume quand quelqu'un se présente, salue la personne, affiche <b>ses</b> infos (météo, agenda, colis, post-it) et on parle à EVA en disant « EVA… » ou en touchant l'écran. Plusieurs personnes ou un inconnu : rien de personnel n'est affiché. Personne : écran noir.</p>
        <p className="page__sub">🔒 La reconnaissance se fait <b>sur le NAS</b>. Aucune image n'est gardée : seules les empreintes des visages appris ci-dessous (des nombres, pas des photos), effaçables à tout moment.</p>
        {!e.modeles_prets && (
          admin ? <p><button className="btn btn--primary" onClick={telecharger} disabled={e.telechargement.en_cours} data-testid="miroir-modeles">{e.telechargement.en_cours ? "Téléchargement…" : `Télécharger la reconnaissance des visages (${e.taille_mo} Mo, une fois)`}</button>
            {e.telechargement.erreur && <span className="page__warn" style={{ display: "block" }}>{e.telechargement.erreur}</span>}</p>
            : <p className="page__warn">L'administrateur doit d'abord activer la reconnaissance des visages (Maison › Miroir).</p>
        )}
        <div className="pj-row">
          <button className="btn btn--primary" onClick={() => window.dispatchEvent(new Event("eva:miroir"))} data-testid="miroir-ouvrir">🪞 Ouvrir le miroir sur cet écran</button>
          <button className="btn btn--ghost" onClick={() => navigator.clipboard?.writeText(adresse).then(() => setMsg(`Adresse copiée : ${adresse} — ouvre-la sur l'écran du miroir (en plein écran / mode kiosque), connecté avec un compte de la famille.`))}>📋 Adresse pour l'écran dédié</button>
        </div>
        {msg && <p className="page__sub" role="status">{msg}</p>}
        {err && <p className="page__warn" role="alert">{err}</p>}
      </div>
      {e.modeles_prets && (
        <div className="card">
          <h3>Visages appris</h3>
          {e.personnes.length ? (
            <ul className="pj-trash__list">{e.personnes.map((p) => (
              <li key={p.qui} className="pj-row"><span>🙂 <b>{p.qui}</b> · {p.photos} photo(s)</span>
                {(admin || p.qui.toLowerCase() === (e.moi || "").toLowerCase()) && <button className="btn btn--ghost" onClick={() => oublier(p.qui)}>Effacer</button>}</li>
            ))}</ul>
          ) : <p className="page__sub">Aucun pour l'instant.</p>}
          <span className="card__label" style={{ marginTop: 10 }}>Apprendre un visage</span>
          <p className="page__sub">Seul(e) face à la caméra, bien éclairé(e) ; tourne un peu la tête pendant les 6 photos.</p>
          <div className="pj-row">
            {admin && <select value={qui} onChange={(x) => setQui(x.target.value)} data-testid="miroir-qui"><option value="">Moi</option>{e.comptes.map((c) => <option key={c} value={c}>{c}</option>)}</select>}
            <button className="btn btn--primary" onClick={apprendre} disabled={!!prise} data-testid="miroir-apprendre">{prise ? `Photo ${prise} / 6…` : "📷 Apprendre"}</button>
          </div>
          <video ref={videoRef} muted playsInline style={{ display: prise ? "block" : "none", maxWidth: 320, borderRadius: 12, marginTop: 8, transform: "scaleX(-1)" }} />
        </div>
      )}
    </div>
  );
}

function SatellitesTab() {
  const [st, setSt] = useState(null); const [f, setF] = useState(null); const [installer, setInstaller] = useState(null); const [retire, setRetire] = useState(null); const [diag, setDiag] = useState(null);
  const { call, Notice } = useCall();
  const [erreur, setErreur] = useState("");
  const load = useCallback(() => api("/api/home/admin/satellites").then((r) => { setSt(r); setErreur(""); })
    .catch((x) => setErreur(x.status === 404 ? "Cette fonction n'est pas encore disponible sur le serveur : eva-core n'a pas été reconstruit avec la dernière mise à jour (docker compose up -d --build eva-core)." : x.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);
  const creer = async (e) => { e.preventDefault(); const r = await call(() => api("/api/home/admin/satellites", { method: "POST", body: JSON.stringify(f) })); if (r) { setInstaller(r); setF(null); load(); } };
  if (!st) return erreur ? <p className="page__warn" role="alert">{erreur}</p> : <p className="page__sub">Chargement…</p>;
  const date = (s) => (s ? new Date(s * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "jamais");
  return (
    <div className="pj-grid">
      <div className="card sat-carte" data-testid="satellites">
        <h3>Satellites vocaux</h3>
        <p className="page__sub">Un micro et un haut-parleur par pièce (Raspberry Pi, vieux PC, portable) ou sur ton ordinateur (Windows, Mac, Linux) : on dit « EVA, allume la lumière » sans ouvrir l'application. EVA peut y faire des annonces, piloter l'ordinateur, regarder l'écran et prendre la main avec ton accord. Chaque satellite connaît sa pièce et agit avec les droits du compte choisi.</p>
        {st.satellites.length ? (
          <ul className="pj-trash__list">{st.satellites.map((s) => (
            <li key={s.id} className="pj-row"><span>{s.en_ligne ? "🟢" : "⚪"} <b>{s.nom}</b>{s.piece ? ` · ${s.piece}` : ""} · compte {s.compte || "—"} · {s.en_ligne ? "en ligne" : <span className="sat-horsligne">hors ligne{s.dernier ? ` depuis ${date(s.dernier)}` : " (jamais connecté)"} : sur la machine, lance le raccourci « EVA démarrer », puis 🩺 Diagnostic si ça ne revient pas</span>}
              {s.a_l_ecoute && <span className="page__sub"> · 🔊 annonces{s.capacites?.includes("pc") ? ` · 🖥️ ${s.systeme} pilotable (${s.applis.length} applis)` : ""}{s.capacites?.includes("ecran") ? " · 👁️ écran" : ""}{s.capacites?.includes("gestes") ? " · ✋ gestes" : ""}{s.capacites?.includes("tableau") ? " · 🗂️ tableau" : ""}{s.capacites?.includes("telephone") ? " · 📱 téléphone" : ""}</span>}
              {(s.pause || s.pause_locale) && <span className="page__warn"> · ⏸ écoute en pause{s.pause ? " (depuis EVA)" : " (sur l'appareil)"}</span>}
              {s.a_l_ecoute && st.version && (s.version && !plusAncienne(s.version, st.version)
                ? <span className="page__sub"> · v{s.version} à jour</span>
                : <span className="page__warn"> · version {s.version || "ancienne"} : réinstalle-le une fois (ensuite il se mettra à jour tout seul)</span>)}</span>
              <span className="sat-actions">
                <button className={`btn ${s.pause ? "btn--primary" : "btn--ghost"}`} title={s.pause ? "Rétablir l'écoute « EVA… »" : "Couper l'écoute : il n'entend plus « EVA… » (les annonces passent toujours)"}
                  onClick={() => call(() => api(`/api/home/admin/satellites/${s.id}/ecoute`, { method: "POST", body: JSON.stringify({ actif: !!s.pause }) })).then(load)}
                  data-testid={`sat-pause-${s.id}`}>{s.pause ? "▶ Activer l'écoute" : "⏸ Pause"}</button>
                {s.a_l_ecoute && <button className="btn btn--ghost" title="Écoute ta phrase suivante, sans dire « EVA »"
                  onClick={() => call(() => api(`/api/home/admin/satellites/${s.id}/controle`, { method: "POST", body: JSON.stringify({ action: "parler" }) }), "Parle maintenant au satellite.")}>🎙 Parler</button>}
                {s.a_l_ecoute && <button className="btn btn--ghost" title="Relance le programme du satellite"
                  onClick={() => call(() => api(`/api/home/admin/satellites/${s.id}/controle`, { method: "POST", body: JSON.stringify({ action: "redemarrer" }) }), "Le satellite redémarre (quelques secondes).").then(() => setTimeout(load, 8000))}
                  data-testid={`sat-redemarrer-${s.id}`}>↻ Redémarrer</button>}
                {s.a_l_ecoute && <button className="btn btn--ghost" title="Arrête le programme : il repartira à la prochaine ouverture de session (ou raccourci « EVA démarrer »)"
                  onClick={() => confirmer(`Arrêter « ${s.nom} » ? Il ne pourra pas être rallumé depuis EVA : il repartira à la prochaine ouverture de session, ou avec le raccourci « EVA démarrer » sur la machine.`).then((ok) => ok && (call(() => api(`/api/home/admin/satellites/${s.id}/controle`, { method: "POST", body: JSON.stringify({ action: "arreter" }) }), "Satellite arrêté.").then(() => setTimeout(load, 3000))))}
                  data-testid={`sat-arreter-${s.id}`}>⏹ Arrêter</button>}
                <button className="btn btn--ghost" onClick={() => setDiag(s)} data-testid={`sat-diag-${s.id}`}>🩺 Diagnostic</button>
                <button className="btn" onClick={() => setInstaller(s)} data-testid={`sat-installer-${s.id}`}>{s.dernier ? "Réinstaller" : "Installer"}</button>
                <button className="btn btn--danger" onClick={() => confirmer(`Supprimer le satellite « ${s.nom} » ? Il n'aura plus accès à EVA${s.a_l_ecoute ? " et se désinstallera tout seul de la machine (programme, démarrage automatique, dossier)" : ""}.`).then((ok) => ok && (call(() => api(`/api/home/admin/satellites/${s.id}`, { method: "DELETE" })).then((r) => { if (r) setRetire({ ...r, nom: s.nom }); load(); })))} data-testid={`sat-suppr-${s.id}`}>Supprimer</button>
              </span></li>
          ))}</ul>
        ) : <p className="page__sub">Aucun satellite pour l'instant.</p>}
        <p className="page__sub"><button className="btn btn--ghost" onClick={() => call(() => api("/api/home/admin/satellites-desinstallation")).then((c) => c && setRetire({ commandes: c }))} data-testid="sat-desinstaller-machine">🧹 Désinstaller d'une machine</button></p>
        {f ? (
          <form className="agentform" onSubmit={creer}>
            <div className="routergrid">
              <label className="field"><span>Nom</span><input value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} placeholder="PC du bureau, Cuisine…" data-testid="sat-nom" /></label>
              <label className="field"><span>Pièce (pour « la lumière »)</span><input value={f.piece} onChange={(e) => setF({ ...f, piece: e.target.value })} placeholder="cuisine" /></label>
              <label className="field"><span>Agit avec les droits de</span><select value={f.compte} onChange={(e) => setF({ ...f, compte: e.target.value })}>{st.comptes.map((u) => <option key={u}>{u}</option>)}</select></label>
            </div>
            <div className="agentform__actions"><button className="btn btn--primary" type="submit" disabled={!f.nom.trim()} data-testid="sat-creer">Créer et installer</button><button className="btn" type="button" onClick={() => setF(null)}>Annuler</button></div>
          </form>
        ) : <div className="agentform__actions"><button className="btn btn--primary" onClick={() => setF({ nom: "", piece: "", compte: st.comptes[0] || "" })} data-testid="sat-ajouter">Ajouter un satellite</button></div>}
        <Notice />
      </div>
      {installer && <InstallerSatellite key={installer.id} sat={installer} durees={st.durees} onFermer={() => setInstaller(null)} onFait={load} />}
      {diag && <DiagnosticSatellite key={diag.id} sat={diag} onFermer={() => setDiag(null)} />}
      {retire && (
        <div className="card" data-testid="sat-retire">
          <h3>{retire.nom ? `« ${retire.nom} » supprimé` : "Désinstaller un satellite d'une machine"}</h3>
          {retire.desinstalle ? (
            <p>✅ Il s'est désinstallé lui-même : {retire.fait.join(", ")}.{retire.reste.length > 0 && <><br />⚠️ Reste à faire : {retire.reste.join(" ; ")}</>}</p>
          ) : (
            <>
              <p>{retire.nom ? "Il n'était pas allumé : il ne pouvait pas se désinstaller lui-même. " : ""}Sur la machine à nettoyer :</p>
              <Desinstallation commandes={retire.commandes} />
            </>
          )}
          <div className="agentform__actions"><button className="btn btn--ghost" onClick={() => setRetire(null)}>Fermer</button></div>
        </div>
      )}
    </div>
  );
}

export default function MaisonPage() {
  const auth = useAuth();
  const admin = !auth.required || auth.role === "admin";
  const [tab, setTab] = useState("devices");
  const tabs = [["devices", "Appareils"], ["scenes", "Scènes"], ["routines", "Routines"], ["presence", "Présence"], ["printers", "Imprimantes"], ["miroir", "Miroir"], ...(admin ? [["satellites", "Satellites"], ["network", "Réseau"]] : [])];
  return (
    <section className="page" data-testid="maison-page">
      <header className="page__header"><h1>Maison</h1><span className="page__sub">Appareils par pièce, scènes, imprimantes, réseau — EVA les pilote à la voix ou au texte.</span></header>
      <div className="page__body">
        <div className="pj-sbx__tabs">{tabs.map(([k, l]) => <button key={k} className={tab === k ? "is-on" : ""} onClick={() => setTab(k)} data-testid={`tab-${k}`}>{l}</button>)}</div>
        {tab === "devices" && <DevicesTab admin={admin} />}
        {tab === "scenes" && <><HueScenes /><ScenesTab admin={admin} /></>}
        {tab === "routines" && <RoutinesTab admin={admin} />}
        {tab === "presence" && <PresenceTab admin={admin} />}
        {tab === "printers" && <PrintersTab admin={admin} />}
        {tab === "miroir" && <MiroirTab admin={admin} />}
        {tab === "satellites" && admin && <SatellitesTab />}
        {tab === "network" && admin && <NetworkTab />}
      </div>
    </section>
  );
}
