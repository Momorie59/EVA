import { useEffect, useState } from "react";
import { api } from "../api";

// Raccourcis iPhone / Android : « Dis Siri, dis à EVA… » envoie la phrase à EVA et lit la réponse.
export default function RaccourcisCard() {
  const [lst, setLst] = useState(null); const [nom, setNom] = useState(""); const [nouveau, setNouveau] = useState(null); const [error, setError] = useState("");
  const load = () => api("/api/raccourcis").then((d) => setLst(d.jetons)).catch((e) => setError(e.status === 404 ? "Pas encore disponible : eva-core n'a pas été reconstruit." : e.message));
  useEffect(() => { load(); }, []);
  const url = `${window.location.origin}/api/raccourci`;
  const creer = async () => { setError(""); try { setNouveau(await api("/api/raccourcis", { method: "POST", body: JSON.stringify({ nom }) })); setNom(""); load(); } catch (e) { setError(e.message); } };
  return (
    <div className="card routercard" data-testid="raccourcis-card">
      <span className="card__label">📱 Raccourcis du téléphone</span>
      <p className="page__sub">« Dis Siri, dis à EVA : ajoute du lait aux courses » — une idée, une note ou une question dictée sur l'iPhone (ou Android avec Tasker) part vers EVA, qui répond à voix haute. Comme chez Jarvis, seules les actions sans demande d'accord sont faites ainsi.</p>
      {lst?.map((j) => (
        <div className="pj-row" key={j.id}><span>📱 <b>{j.nom}</b> <span className="page__sub">{j.dernier ? `utilisé le ${new Date(j.dernier * 1000).toLocaleString("fr-FR")}` : "jamais utilisé"}</span></span>
          <button className="btn btn--ghost" onClick={() => api(`/api/raccourcis/${j.id}`, { method: "DELETE" }).then(load)}>Retirer</button></div>
      ))}
      {nouveau ? (
        <div className="mcpsrv__nouveau">
          <p><b>Jeton de « {nouveau.nom} »</b> (affiché une seule fois) :</p>
          <pre className="mcpsrv__pre">{nouveau.jeton}</pre>
          <ol className="page__sub">
            <li>App <b>Raccourcis</b> › <b>+</b> › action <b>Dicter le texte</b> (langue : français).</li>
            <li>Action <b>Obtenir le contenu de l'URL</b> : adresse <code>{url}</code>, méthode <b>POST</b>, en-tête <code>Authorization</code> = <code>Bearer {nouveau.jeton.slice(0, 12)}…</code> (le jeton entier), corps <b>JSON</b> : clé <code>texte</code> = <i>Texte dicté</i>.</li>
            <li>Action <b>Énoncer le texte</b> (ou Afficher la notification) avec <i>Contenu de l'URL</i>.</li>
            <li>Nomme le raccourci <b>Dis à EVA</b> : « Dis Siri, dis à EVA ». Le téléphone doit joindre EVA (wifi de la maison ou accès à distance) et faire confiance à son certificat.</li>
          </ol>
          <button className="btn btn--ghost" onClick={() => setNouveau(null)}>C'est noté</button>
        </div>
      ) : (
        <div className="pj-row"><input value={nom} onChange={(e) => setNom(e.target.value)} placeholder="Nom du téléphone (ex. iPhone de Léa)" /><button className="btn btn--primary" onClick={creer} data-testid="raccourci-creer">Créer un jeton</button></div>
      )}
      {error && <p className="page__warn">{error}</p>}
    </div>
  );
}
