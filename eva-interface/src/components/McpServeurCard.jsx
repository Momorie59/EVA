import { useEffect, useState } from "react";
import { api } from "../api";
import { confirmer } from "../confirmer";

const date = (s) => (s ? new Date(s * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "jamais");

function ChoixOutils({ outils, choix, setChoix }) {
  const [q, setQ] = useState("");
  const vis = outils.filter((o) => !q || `${o.nom} ${o.description}`.toLowerCase().includes(q.toLowerCase()));
  const groupe = (action) => vis.filter((o) => o.action === action);
  const ligne = (o) => (
    <li key={o.nom}><label title={o.description}><input type="checkbox" checked={choix.includes(o.nom)} onChange={(e) => setChoix(e.target.checked ? [...choix, o.nom] : choix.filter((x) => x !== o.nom))} /> <code>{o.nom}</code> <span className="page__sub">{o.description.slice(0, 80)}</span></label></li>
  );
  return (
    <div>
      <div className="pj-row"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrer les outils…" />
        <button className="btn btn--ghost" type="button" onClick={() => setChoix([...new Set([...choix, ...groupe(false).map((o) => o.nom)])])}>Cocher toute la consultation</button></div>
      <span className="card__label">Consultation (ne change rien)</span>
      <ul className="pj-trash__list mcpsrv__liste">{groupe(false).map(ligne)}</ul>
      <span className="card__label">⚠️ Actions — s'exécuteront sans te demander</span>
      <ul className="pj-trash__list mcpsrv__liste">{groupe(true).map(ligne)}</ul>
    </div>
  );
}

export default function McpServeurCard() {
  const [st, setSt] = useState(null); const [error, setError] = useState(""); const [msg, setMsg] = useState("");
  const [f, setF] = useState(null); const [nouveau, setNouveau] = useState(null); const [edit, setEdit] = useState(null);
  const load = () => api("/api/mcp/serveur").then(setSt).catch((e) => setError(e.status === 404 ? "Pas encore disponible : eva-core n'a pas été reconstruit avec la dernière mise à jour." : e.message));
  useEffect(() => { load(); }, []);
  const url = `${window.location.origin}/api/serveur-mcp`;
  const run = async (fn, ok) => { setError(""); setMsg(""); try { const r = await fn(); if (ok) setMsg(ok); await load(); return r; } catch (e) { setError(e.message); return null; } };
  const creer = async () => { const r = await run(() => api("/api/mcp/serveur/jetons", { method: "POST", body: JSON.stringify(f) })); if (r) { setNouveau(r); setF(null); } };
  const conf = (jeton) => JSON.stringify({ mcpServers: { eva: { command: "npx", args: ["-y", "mcp-remote", url, "--header", `Authorization: Bearer ${jeton}`] } } }, null, 2);

  if (!st) return <div className="card"><span className="card__label">EVA comme serveur MCP</span>{error ? <p className="page__warn">{error}</p> : <p className="dash-loading">Chargement…</p>}</div>;
  return (
    <div className="card routercard" data-testid="mcp-serveur-card">
      <span className="card__label">EVA comme serveur MCP</span>
      <p className="page__sub">D'autres assistants (Claude Desktop, Cursor, un autre EVA…) peuvent utiliser les outils d'EVA. Chaque client a son jeton, rattaché à un compte EVA dont les droits s'appliquent, et ne voit que les outils cochés. Chaque appel est noté dans le journal d'accès. Adresse : <code>{url}</code></p>
      {st.jetons.map((j) => (
        <div key={j.id} className="pj-row mcpsrv__jeton">
          <span>🔑 <b>{j.nom}</b> · compte {j.compte || "(sans compte)"} · {j.outils.length} outil(s) · {j.appels} appel(s), dernier : {date(j.dernier)}</span>
          <button className="btn btn--ghost" onClick={() => setEdit(edit?.id === j.id ? null : { id: j.id, outils: j.outils })}>Outils</button>
          <button className="btn btn--danger" onClick={() => confirmer(`Révoquer le jeton « ${j.nom} » ? Ce client ne pourra plus rien faire.`).then((ok) => ok && (run(() => api(`/api/mcp/serveur/jetons/${j.id}`, { method: "DELETE" }), "Jeton révoqué.")))}>Révoquer</button>
          {edit?.id === j.id && (
            <div style={{ width: "100%" }}>
              <ChoixOutils outils={st.outils} choix={edit.outils} setChoix={(o) => setEdit({ ...edit, outils: o })} />
              <button className="btn btn--primary" onClick={async () => { if (await run(() => api(`/api/mcp/serveur/jetons/${j.id}`, { method: "PUT", body: JSON.stringify({ outils: edit.outils }) }), "Outils mis à jour.")) setEdit(null); }}>Enregistrer</button>
            </div>
          )}
        </div>
      ))}
      {nouveau && (
        <div className="mcpsrv__nouveau" data-testid="mcp-nouveau-jeton">
          <p><b>Jeton de « {nouveau.nom} »</b> — copie-le maintenant, il ne sera plus affiché :</p>
          <pre className="mcpsrv__pre">{nouveau.jeton}</pre>
          <p className="page__sub">Pour Claude Desktop (fichier <code>claude_desktop_config.json</code>). Si EVA utilise son propre certificat, ajoute <code>"env": {"{"}"NODE_EXTRA_CA_CERTS": "chemin/vers/eva-ca.crt"{"}"}</code>.</p>
          <pre className="mcpsrv__pre">{conf(nouveau.jeton)}</pre>
          <div className="agentform__actions"><button className="btn" onClick={() => navigator.clipboard?.writeText(conf(nouveau.jeton))}>Copier la configuration</button><button className="btn btn--ghost" onClick={() => setNouveau(null)}>C'est noté</button></div>
        </div>
      )}
      {f ? (
        <div className="mcpsrv__form">
          <div className="routergrid">
            <label className="field"><span>Nom du client</span><input value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} placeholder="Claude sur le portable" data-testid="mcp-nom" /></label>
            <label className="field"><span>Agit avec les droits de</span><select value={f.compte} onChange={(e) => setF({ ...f, compte: e.target.value })}>{st.comptes.map((u) => <option key={u}>{u}</option>)}</select></label>
          </div>
          <ChoixOutils outils={st.outils} choix={f.outils} setChoix={(o) => setF({ ...f, outils: o })} />
          <div className="agentform__actions"><button className="btn btn--primary" disabled={!f.nom.trim() || !f.outils.length} onClick={creer} data-testid="mcp-creer">Créer le jeton</button><button className="btn" onClick={() => setF(null)}>Annuler</button></div>
        </div>
      ) : <div className="agentform__actions"><button className="btn btn--primary" onClick={() => setF({ nom: "", compte: st.comptes[0] || "", outils: [] })} data-testid="mcp-ajouter">Nouveau client</button></div>}
      {error && <p className="page__warn">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
