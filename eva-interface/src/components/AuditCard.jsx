import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";

const KINDS = [["", "Tout"], ["login", "Connexions"], ["login_fail", "Échecs de connexion"], ["denied", "Refus"], ["action", "Actions"], ["admin", "Administration"], ["session", "Sessions"], ["logout", "Déconnexions"], ["ws", "Chat ouvert"]];
const fmt = (iso) => { try { return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" }); } catch { return iso || ""; } };
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v)).toString();

// Journal d'accès, façon bastion — réservé aux administrateurs. Conservé 90 jours.
export default function AuditCard() {
  const [events, setEvents] = useState([]);
  const [user, setUser] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (before) => {
    try {
      const d = await api(`/api/auth/audit?${qs({ user, kind, q, limit: 100, before })}`);
      setEvents((cur) => (before ? [...cur, ...d.events] : d.events)); setMore(d.events.length === 100); setError("");
    } catch (e) { setError(e.message); }
  }, [user, kind, q]);
  useEffect(() => { const t = setTimeout(() => load(), 250); return () => clearTimeout(t); }, [load]);

  async function exportCsv() {
    const res = await fetch(`${CORE_URL}/api/auth/audit.csv?${qs({ user, kind, q })}`, { headers: authHeaders() });
    if (!res.ok) return setError(`Export impossible (${res.status})`);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = "eva-journal.csv"; a.click(); URL.revokeObjectURL(url);
  }

  return (
    <div className="card routercard" data-testid="audit-card">
      <span className="card__label">Journal d'accès</span>
      <p className="page__sub">Qui s'est connecté, qui a échoué, ce qui a été refusé et chaque action qui modifie quelque chose (réglages, projets, fichiers…). Conservé 90 jours. Les mots de passe n'y figurent jamais.</p>
      <div className="pj-row">
        <input value={user} onChange={(e) => setUser(e.target.value)} placeholder="Utilisateur" data-testid="audit-user" />
        <select value={kind} onChange={(e) => setKind(e.target.value)} data-testid="audit-kind">{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (action, adresse IP…)" data-testid="audit-q" />
        <button className="btn btn--ghost" onClick={() => load()}>Actualiser</button>
        <button className="btn btn--ghost" onClick={exportCsv} data-testid="audit-csv">Exporter (CSV)</button>
      </div>
      <div className="pj-table" style={{ maxHeight: 360, marginTop: 8 }}>
        <table data-testid="audit-table">
          <thead><tr><th>Date</th><th>Utilisateur</th><th>Adresse</th><th>Type</th><th>Action</th><th>Détail</th><th>Statut</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}><td>{fmt(e.ts)}</td><td>{e.username || "—"}</td><td>{e.ip}</td><td>{e.kind}</td><td>{e.action}</td><td>{e.detail}</td><td>{e.status || ""}</td></tr>
            ))}
            {!events.length && <tr><td colSpan={7}>Aucun évènement.</td></tr>}
          </tbody>
        </table>
      </div>
      {more && <button className="btn btn--ghost" onClick={() => load(events[events.length - 1]?.id)}>Plus ancien…</button>}
      {error && <p className="page__warn" role="alert">{error}</p>}
    </div>
  );
}
