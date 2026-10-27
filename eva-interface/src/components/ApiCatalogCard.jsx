import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const fmt = (t) => { try { return new Date(t * 1000).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }); } catch { return ""; } };

// Catalogue d'API publiques : se met à jour seul une fois par semaine ; EVA annonce les nouveautés.
export default function ApiCatalogCard() {
  const [st, setSt] = useState(null); const [busy, setBusy] = useState(false); const [msg, setMsg] = useState("");
  const load = useCallback(async () => { try { setSt(await api("/api/apis/status")); } catch { /* ignoré */ } }, []);
  useEffect(() => { load(); }, [load]);
  async function update() {
    setBusy(true); setMsg("");
    try { const r = await api("/api/apis/update", { method: "POST" }); setMsg(r.error ? `Échec : ${r.error}` : `Terminé : ${r.new} nouvelle(s) API.`); } catch (e) { setMsg(e.message); }
    setBusy(false); load();
  }
  if (!st) return null;
  return (
    <section className="card" data-testid="api-catalog-card">
      <span className="card__label">API publiques</span>
      <p className="page__sub">{st.total} API connues dont {st.keyless} sans clé — mise à jour automatique chaque semaine depuis le dépôt public-apis.{st.updated_at ? ` Dernière mise à jour : ${fmt(st.updated_at)}.` : " Pas encore mise à jour : catalogue fourni avec EVA."}</p>
      {st.last_error && <p className="page__warn">Dernière vérification en échec : {st.last_error}</p>}
      {st.recent.length > 0 && <ul className="pj-trash__list" data-testid="api-recent">{st.recent.slice(0, 8).map((a) => <li key={a.u}><span><b>{a.n}</b> <small>{a.c}{a.a ? ` · clé ${a.a}` : ""} · {a.date}</small></span></li>)}</ul>}
      <div className="pj-row"><button className="btn" onClick={update} disabled={busy} data-testid="api-update">{busy ? "Mise à jour…" : "Mettre à jour maintenant"}</button></div>
      {msg && <p className="page__sub" data-testid="api-msg">{msg}</p>}
    </section>
  );
}
