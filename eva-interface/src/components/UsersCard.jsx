import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "./AuthGate";
import { confirmer } from "../confirmer";

const fmt = (iso) => { try { return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); } catch { return iso || ""; } };

const PROFILES = [
  ["admin", "Administrateur", "Accès complet, réglages, autres comptes."],
  ["user", "Adulte", "Utilise EVA normalement, sans les réglages ni le réseau."],
  ["teen", "Adolescent", "Comme un adulte, sans terminal, réseau, Docker ni installation ; contenus adaptés à son âge."],
  ["child", "Enfant", "Réponses simples et rassurantes, pas d'Internet libre, pas de fichiers : jeux, histoires, devoirs, dessins."],
  ["guest", "Invité", "Accès minimal : questions simples, météo, recherche ; rien de personnel."],
];
const roleLabel = (r) => (PROFILES.find((p) => p[0] === r) || [r, r])[1];

// Utilisateurs et sessions — réservé aux administrateurs.
export default function UsersCard() {
  const auth = useAuth();
  const [users, setUsers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [role, setRole] = useState("user");
  const [reset, setReset] = useState({});
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const [u, s] = await Promise.all([api("/api/auth/users"), api("/api/auth/sessions")]);
      setUsers(u.users); setSessions(s.sessions);
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function act(fn, done) {
    setError(""); setMsg("");
    try { await fn(); if (done) setMsg(done); await load(); } catch (e) { setError(e.message); }
  }
  const add = (e) => { e.preventDefault(); act(async () => {
    await api("/api/auth/users", { method: "POST", body: JSON.stringify({ user: name.trim(), password: pw, role }) });
    setName(""); setPw(""); setRole("user");
  }, "Utilisateur créé."); };
  const patch = (u, body, done) => act(() => api(`/api/auth/users/${encodeURIComponent(u)}`, { method: "PATCH", body: JSON.stringify(body) }), done);
  const del = async (u) => { if ((await confirmer(`Supprimer l'utilisateur ${u} ? Ses sessions seront fermées.`))) act(() => api(`/api/auth/users/${encodeURIComponent(u)}`, { method: "DELETE" }), "Utilisateur supprimé."); };
  const revoke = (id) => act(() => api(`/api/auth/sessions/${id}`, { method: "DELETE" }), "Session fermée.");

  return (
    <div className="card routercard" data-testid="users-card">
      <span className="card__label">Utilisateurs</span>
      <p className="page__sub">Chaque personne a son compte. <b>Administrateur</b> : tout, y compris les comptes et le journal. <b>Utilisateur</b> : discuter, projets et bac à sable — pas de réglages sensibles (auto-évolution, sauvegardes, connecteurs, modèles, partage réseau). Les conversations et projets restent communs à tous les comptes.</p>
      <ul className="pj-trash__list" data-testid="users-list">
        {users.map((u) => (
          <li key={u.user} data-testid={`user-${u.user}`}>
            <span><b>{u.user}</b> — {roleLabel(u.role).toLowerCase()}{u.disabled ? " — désactivé" : ""}{u.user === auth.user ? " (toi)" : ""}</span>
            <select value={u.role} onChange={(e) => patch(u.user, { role: e.target.value }, "Rôle modifié.")} aria-label={`Rôle de ${u.user}`}>
              {PROFILES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <button className="btn btn--ghost" onClick={() => patch(u.user, { disabled: !u.disabled }, u.disabled ? "Compte réactivé." : "Compte désactivé.")}>{u.disabled ? "Réactiver" : "Désactiver"}</button>
            {reset[u.user] === undefined
              ? <button className="btn btn--ghost" onClick={() => setReset({ ...reset, [u.user]: "" })}>Nouveau mot de passe…</button>
              : <span className="pj-row">
                  <input type="password" value={reset[u.user]} onChange={(e) => setReset({ ...reset, [u.user]: e.target.value })} placeholder="8 caractères min." autoComplete="new-password" />
                  <button className="btn btn--primary" disabled={reset[u.user].length < 8} onClick={() => { patch(u.user, { password: reset[u.user] }, "Mot de passe réinitialisé (sessions fermées)."); const r = { ...reset }; delete r[u.user]; setReset(r); }}>Valider</button>
                </span>}
            {u.user !== auth.user && <button className="btn btn--danger" onClick={() => del(u.user)}>Supprimer</button>}
          </li>
        ))}
      </ul>
      <form className="pj-row" onSubmit={add} style={{ marginTop: 10 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Identifiant" autoComplete="off" data-testid="nu-name" />
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Mot de passe (8 min.)" autoComplete="new-password" data-testid="nu-pw" />
        <select value={role} onChange={(e) => setRole(e.target.value)} data-testid="nu-role">{PROFILES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <small className="page__sub" data-testid="nu-role-hint">{(PROFILES.find((p) => p[0] === role) || [])[2]}</small>
        <button className="btn btn--primary" type="submit" disabled={!name || pw.length < 8} data-testid="nu-add">Ajouter</button>
      </form>
      <span className="card__label" style={{ marginTop: 14 }}>Sessions actives</span>
      <ul className="pj-trash__list" data-testid="sessions-list">
        {sessions.map((s) => (
          <li key={s.id}>
            <span><b>{s.user}</b> — ouverte le {fmt(s.created)}, expire le {fmt(s.expires)}{s.current ? " — cet appareil" : ""}<br /><small>{s.agent}</small></span>
            {!s.current && <button className="btn btn--ghost" onClick={() => revoke(s.id)}>Fermer</button>}
          </li>
        ))}
      </ul>
      {error && <p className="page__warn" role="alert" data-testid="users-error">{error}</p>}
      {msg && <p className="page__sub" data-testid="users-msg">{msg}</p>}
    </div>
  );
}
