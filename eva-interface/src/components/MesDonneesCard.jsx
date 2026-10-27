import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";

// Mes données : ce qu'EVA garde sur moi, tout récupérer (ZIP) ou tout effacer.
// L'administrateur peut choisir une autre personne (et supprimer son compte).
export default function MesDonneesCard({ admin = false }) {
  const [qui, setQui] = useState("");
  const [users, setUsers] = useState([]);
  useEffect(() => { if (admin) api("/api/auth/users").then((x) => setUsers(Array.isArray(x) ? x : x.users || [])).catch(() => {}); }, [admin]);
  const [inv, setInv] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [compte, setCompte] = useState(false);
  const q = qui ? `?personne=${encodeURIComponent(qui)}` : "";
  const load = useCallback(() => api(`/api/donnees${q}`).then((x) => { setInv(x); setError(""); }).catch((e) => setError(e.message)), [q]);
  useEffect(() => { load(); }, [load]);

  const exporter = async () => {
    setBusy(true); setError(""); setMsg("");
    try {
      const { path } = await api(`/api/donnees/export${q}`, { method: "POST" });
      const r = await fetch(`${CORE_URL}/api/files/download?path=${encodeURIComponent(path)}`, { headers: authHeaders() });
      if (!r.ok) throw new Error("Téléchargement impossible.");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = path.split("/").pop(); a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setMsg("Export prêt : le fichier ZIP est téléchargé.");
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const effacer = async () => {
    const nom = qui || "toi";
    const mot = window.prompt(`Effacer définitivement toutes les données de ${nom}${compte ? " ET son compte" : ""} ? Écris EFFACER pour confirmer.`);
    if (!mot) return;
    setBusy(true); setError(""); setMsg("");
    try {
      await api(`/api/donnees/effacer${q}`, { method: "POST", body: JSON.stringify({ confirmation: mot, compte: admin && !!qui && compte }) });
      setMsg(compte && qui ? `Les données et le compte de ${qui} sont effacés.` : "Les données sont effacées.");
      if (compte && qui) { setQui(""); setCompte(false); } else await load();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const autres = users.filter((u) => u.role !== "admin");
  return (
    <div className="card" data-testid="mes-donnees">
      <span className="card__label">{qui ? `Données de ${qui}` : "Mes données"}</span>
      <p className="card__hint">Tout ce qu'EVA garde sur {qui ? "cette personne" : "toi"} : conversations, post-it, carnets, projets, fichiers, images et mémoire. Tu peux tout récupérer dans un ZIP, ou tout effacer. Les papiers de la famille ne sont pas concernés.</p>
      {admin && autres.length > 0 && (
        <label className="field"><span>Personne</span>
          <select value={qui} onChange={(e) => { setQui(e.target.value); setCompte(false); }} data-testid="donnees-personne">
            <option value="">Moi</option>
            {autres.map((u) => <option key={u.user} value={u.user}>{u.user}</option>)}
          </select>
        </label>
      )}
      {inv && (
        <ul className="access__legend">
          <li>{inv.conversations} conversation(s), {inv.messages} message(s)</li>
          <li>{inv.post_it} post-it, {inv.carnets} carnet(s), {inv.souvenirs} souvenir(s)</li>
          <li>{inv.fichiers} fichier(s), {inv.images} image(s){inv.projets.length ? `, projets : ${inv.projets.join(", ")}` : ""}</li>
        </ul>
      )}
      <div className="schedrow">
        <button className="btn btn--primary" onClick={exporter} disabled={busy} data-testid="donnees-export">Tout récupérer (ZIP)</button>
        <button className="btn btn--ghost" onClick={effacer} disabled={busy} data-testid="donnees-effacer">Tout effacer…</button>
        {admin && qui && <label className="access__f"><input type="checkbox" checked={compte} onChange={() => setCompte(!compte)} />supprimer aussi le compte</label>}
      </div>
      {error && <p className="page__warn" role="alert">{error}</p>}
      {msg && <p className="page__sub">{msg}</p>}
    </div>
  );
}
