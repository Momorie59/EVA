import { useState } from "react";
import { CORE_URL, authHeaders } from "../urls";

// Fichier prêt (ZIP livré par EVA) : téléchargement avec le jeton d'accès, sans ouvrir de nouvel onglet.
export default function DownloadBubble({ m }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = m.path.split("/").pop();
  async function download() {
    setBusy(true); setError("");
    try {
      const res = await fetch(`${CORE_URL}/api/files/download?path=${encodeURIComponent(m.path)}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) { setError(e.message); }
    setBusy(false);
  }
  return (
    <div className="bubble bubble--download" data-testid="download-bubble">
      <span>{({ docx: "📝", pdf: "📕", pptx: "📊", xlsx: "📗" })[name.split(".").pop().toLowerCase()] || "📦"} {name} — {name.toLowerCase().endsWith('.zip') ? `${m.count} fichier(s), ` : ""}{Math.max(1, Math.round((m.size || 0) / 1024))} Ko</span>
      <button type="button" className="btn btn--primary" onClick={download} disabled={busy} data-testid="download-btn">{busy ? "…" : "Télécharger"}</button>
      {error && <span className="page__warn">{error}</span>}
    </div>
  );
}
