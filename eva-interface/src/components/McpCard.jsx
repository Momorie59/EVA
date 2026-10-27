import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

export default function McpCard() {
  const [servers, setServers] = useState(null);
  const [form, setForm] = useState({ name: "", url: "", auth: "", trusted: false });
  const [error, setError] = useState("");
  const load = () => api("/api/mcp").then((d) => setServers(d.servers)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function add() {
    setError("");
    const headers = form.auth.trim() ? { Authorization: form.auth.trim().startsWith("Bearer ") ? form.auth.trim() : `Bearer ${form.auth.trim()}` } : {};
    try {
      const d = await api("/api/mcp", { method: "PUT", body: JSON.stringify({ name: form.name, url: form.url, headers, trusted: form.trusted }) });
      setServers(d.servers); setForm({ name: "", url: "", auth: "", trusted: false });
    } catch (e) { setError(e.message); }
  }
  async function act(fn) { setError(""); try { await fn(); await load(); } catch (e) { setError(e.message); } }
  const toggleTrust = (s) => act(() => api("/api/mcp", { method: "PUT", body: JSON.stringify({ name: s.name, url: s.url, trusted: !s.trusted, enabled: s.enabled }) }));
  const toggleOn = (s) => act(() => api("/api/mcp", { method: "PUT", body: JSON.stringify({ name: s.name, url: s.url, trusted: s.trusted, enabled: !s.enabled }) }));
  const refresh = (s) => act(() => api(`/api/mcp/${s.name}/refresh`, { method: "POST" }));
  const remove = (s) => confirmer(`Retirer le serveur « ${s.name} » ?`).then((ok) => ok && (act(() => api(`/api/mcp/${s.name}`, { method: "DELETE" }))));

  return (
    <div className="card routercard">
      <span className="card__label">Outils externes (MCP)</span>
      <p className="page__sub">
        Branche des serveurs MCP (protocole « streamable HTTP ») : leurs outils deviennent des outils d'EVA. Par défaut, <strong>chaque appel te demande confirmation</strong> ; marque un serveur « de confiance » seulement si tu le contrôles. Leurs résultats sont traités comme du contenu externe non fiable.
      </p>
      {servers === null && !error && <p className="dash-loading">Chargement…</p>}
      {(servers || []).map((s) => (
        <div key={s.name} className="mcprow">
          <div><strong>{s.name}</strong> <span className="page__sub">{s.url}</span></div>
          <div className="page__sub">
            {s.status === "ok" ? `✅ ${s.tools.length} outil(s) : ${s.tools.map((t) => t.name).join(", ") || "—"}` : s.status === "off" ? "⏸ désactivé" : `❌ ${s.error || "non joint"}`}
          </div>
          <div className="agentform__actions">
            <button className="btn" onClick={() => refresh(s)}>Actualiser</button>
            <button className="btn" onClick={() => toggleTrust(s)}>{s.trusted ? "Retirer la confiance" : "Marquer de confiance"}</button>
            <button className="btn" onClick={() => toggleOn(s)}>{s.enabled ? "Désactiver" : "Activer"}</button>
            <button className="btn btn--danger" onClick={() => remove(s)}>Retirer</button>
          </div>
        </div>
      ))}
      <div className="routergrid">
        <label className="field"><span>Nom (lettres/chiffres)</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="notes" /></label>
        <label className="field"><span>Adresse du serveur</span><input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="http://192.168.1.50:9000/mcp" /></label>
        <label className="field"><span>Jeton (facultatif)</span><input type="password" value={form.auth} onChange={(e) => setForm({ ...form, auth: e.target.value })} /></label>
      </div>
      <div className="agentform__actions"><button className="btn btn--primary" disabled={!form.name || !form.url} onClick={add}>Ajouter et tester</button></div>
      {error && <p className="page__warn">{error}</p>}
    </div>
  );
}
