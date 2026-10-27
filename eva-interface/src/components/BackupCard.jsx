import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";
import { confirmer } from "../confirmer";

const fmt = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1024))} Ko`);

export default function BackupCard() {
  const [list, setList] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const load = () => api("/api/backup").then((d) => setList(d.backups)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function create() {
    setBusy(true); setError(""); setMsg("");
    try { const r = await api("/api/backup", { method: "POST" }); setMsg(`Sauvegarde créée : ${r.name} (${fmt(r.size)}).`); await load(); }
    catch (e) { setError(e.message); }
    setBusy(false);
  }
  async function download(name) {
    setError("");
    try {
      const res = await fetch(`${CORE_URL}/api/backup/file/${name}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) { setError(e.message); }
  }
  async function restore(file) {
    if (!file) return;
    if (!(await confirmer("Restaurer cette sauvegarde REMPLACE les conversations, avis, agents, réglages et traces actuels (les fichiers du workspace sont écrasés par ceux de l'archive). Continuer ?"))) { fileRef.current.value = ""; return; }
    setBusy(true); setError(""); setMsg("");
    try {
      const res = await fetch(`${CORE_URL}/api/backup/restore`, { method: "POST", headers: { "Content-Type": "application/zip", ...authHeaders() }, body: file });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
      setMsg(`Restauré : ${Object.values(data.tables).reduce((a, b) => a + b, 0)} enregistrements, ${data.files} fichier(s). Recharge la page.`);
      await load();
    } catch (e) { setError(e.message); }
    fileRef.current.value = ""; setBusy(false);
  }

  return (
    <div className="card routercard">
      <span className="card__label">Sauvegarde</span>
      <p className="page__sub">
        Une sauvegarde automatique est faite chaque jour (7 conservées dans le workspace, dossier <code>backups</code>). Elle contient conversations, avis, agents, réglages et fichiers du workspace —
        <strong> aussi tes jetons (Google, Telegram…)</strong> : garde-la en lieu sûr. Pense à la copier hors du NAS.
      </p>
      <div className="agentform__actions">
        <button className="btn btn--primary" disabled={busy} onClick={create}>Sauvegarder maintenant</button>
        <label className="btn">Restaurer un fichier…<input ref={fileRef} type="file" accept=".zip" hidden disabled={busy} onChange={(e) => restore(e.target.files[0])} /></label>
      </div>
      {list && list.length > 0 && (
        <ul className="backuplist">
          {list.map((b) => (
            <li key={b.name}><span>{b.created.replace("T", " ")} · {fmt(b.size)}</span> <button className="btn" onClick={() => download(b.name)}>Télécharger</button></li>
          ))}
        </ul>
      )}
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
