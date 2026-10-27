import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

// Fonctionnalités par personne et par groupe : on coche ce que chacun peut utiliser (voix, internet, images…).
export default function AccessCard() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [label, setLabel] = useState("");
  const load = useCallback(() => api("/api/access").then((x) => { setD(x); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn, done) => { setError(""); setMsg(""); try { await fn(); if (done) setMsg(done); await load(); } catch (e) { setError(e.message); } };
  if (!d) return <div className="card"><span className="card__label">Fonctionnalités</span>{error ? <p className="page__warn">{error}</p> : <p className="card__hint">Chargement…</p>}</div>;

  const F = d.features;
  const toggleGroupFeat = (g, f) => run(() => api(`/api/access/groups/${g.id}`, { method: "PUT", body: JSON.stringify({ label: g.label, features: g.features.includes(f) ? g.features.filter((x) => x !== f) : [...g.features, f] }) }));
  const addGroup = (e) => { e.preventDefault(); run(async () => { await api("/api/access/groups", { method: "POST", body: JSON.stringify({ label, features: [] }) }); setLabel(""); }, "Groupe créé : coche ce qu'il peut faire."); };
  const delGroup = async (g) => { if ((await confirmer(`Supprimer le groupe « ${g.label} » ?`))) run(() => api(`/api/access/groups/${g.id}`, { method: "DELETE" })); };

  const saveUser = (u, patch) => run(() => api(`/api/access/users/${encodeURIComponent(u.user)}`, { method: "PUT", body: JSON.stringify({ groups: u.groups, extra: u.extra, blocked: u.blocked, ...patch }) }));
  const inherited = (u, f) => u.base.includes(f) || d.groups.some((g) => u.groups.includes(g.id) && g.features.includes(f));
  const toggleUserFeat = (u, f) => {
    const on = u.effective.includes(f);
    let extra = u.extra.filter((x) => x !== f), blocked = u.blocked.filter((x) => x !== f);
    if (!on && !inherited(u, f)) extra = [...extra, f];
    if (on && inherited(u, f)) blocked = [...blocked, f];
    saveUser(u, { extra, blocked });
  };
  const toggleUserGroup = (u, gid) => saveUser(u, { groups: u.groups.includes(gid) ? u.groups.filter((x) => x !== gid) : [...u.groups, gid] });
  const people = d.users.filter((u) => u.role !== "admin");

  return (
    <div className="card routercard" data-testid="access-card">
      <span className="card__label">Fonctionnalités par personne et par groupe</span>
      <p className="card__hint">Chaque profil (adulte, adolescent, enfant, invité) a des fonctionnalités de base. Tu peux en ajouter ou en retirer pour une personne, ou créer des groupes (ex. « Famille », « Enfants ») et y rattacher des comptes. L'administrateur a toujours tout.</p>
      <ul className="access__legend">
        {F.map((f) => <li key={f.id}><span aria-hidden="true">{f.icon}</span> <b>{f.label}</b> — {f.hint}</li>)}
      </ul>

      <b>Groupes</b>
      {d.groups.length === 0 && <p className="card__hint">Aucun groupe pour l'instant.</p>}
      {d.groups.map((g) => (
        <div key={g.id} className="access__row" data-testid="access-group">
          <strong>{g.label}</strong>
          <div className="access__feats">
            {F.map((f) => <label key={f.id} className="access__f"><input type="checkbox" checked={g.features.includes(f.id)} onChange={() => toggleGroupFeat(g, f.id)} data-testid={`g-${g.id}-${f.id}`} />{f.icon} {f.label}</label>)}
          </div>
          <button className="btn btn--ghost" onClick={() => delGroup(g)}>Supprimer</button>
        </div>
      ))}
      <form className="schedrow" onSubmit={addGroup}>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Nouveau groupe (ex. Enfants)" data-testid="group-name" />
        <button className="btn btn--primary" type="submit" disabled={!label.trim()} data-testid="group-add">Créer le groupe</button>
      </form>

      <b>Personnes</b>
      {people.length === 0 && <p className="card__hint">Crée d'abord un compte non administrateur (carte « Utilisateurs »).</p>}
      {people.map((u) => (
        <div key={u.user} className="access__row" data-testid="access-user">
          <strong>{u.user}</strong> <small className="card__hint">{({ user: "adulte", teen: "adolescent", child: "enfant", guest: "invité" })[u.role] || u.role}</small>
          {d.groups.length > 0 && (
            <div className="aisrv__chips">
              {d.groups.map((g) => <button key={g.id} className={`chip chip--btn ${u.groups.includes(g.id) ? "chip--up" : ""}`} onClick={() => toggleUserGroup(u, g.id)} title="Rattacher / détacher du groupe">{g.label}</button>)}
            </div>
          )}
          <div className="access__feats">
            {F.map((f) => (
              <label key={f.id} className={`access__f ${u.extra.includes(f.id) ? "is-extra" : ""} ${u.blocked.includes(f.id) ? "is-blocked" : ""}`}>
                <input type="checkbox" checked={u.effective.includes(f.id)} onChange={() => toggleUserFeat(u, f.id)} data-testid={`u-${u.user}-${f.id}`} />{f.icon} {f.label}
              </label>
            ))}
          </div>
        </div>
      ))}
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
