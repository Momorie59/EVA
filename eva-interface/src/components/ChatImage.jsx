import { useEffect, useState } from "react";
import { api } from "../api";

// Image créée par EVA, affichée dans la conversation (comme dans ChatGPT) : clic = agrandir, bouton = enregistrer.
export default function ChatImage({ m }) {
  const [src, setSrc] = useState(m.src || "");
  const [error, setError] = useState("");
  const [big, setBig] = useState(false);
  useEffect(() => {
    if (src || !m.name) return;
    let off = false;
    api(`/api/images/item/${m.name}`).then((r) => { if (!off) setSrc(r.image); }).catch(() => { if (!off) setError("Image supprimée (purge automatique ou suppression manuelle)."); });
    return () => { off = true; };
  }, [m.name, src]);
  function save() {
    const a = document.createElement("a"); a.href = src; a.download = m.name || "image-eva.png"; document.body.appendChild(a); a.click(); a.remove();
  }
  if (error) return <div className="bubble bubble--eva chatimg__err">{error}</div>;
  if (!src) return <div className="bubble bubble--eva chatimg__wait">Chargement de l'image…</div>;
  return (
    <div className="chatimg" data-testid="chat-image">
      <img src={src} alt={m.prompt || "Image créée par EVA"} onClick={() => setBig(true)} />
      <button type="button" className="btn" onClick={save} data-testid="chat-image-save">Enregistrer</button>
      {big && (
        <div className="chatimg__overlay" onClick={() => setBig(false)} role="dialog" aria-label="Image agrandie">
          <img src={src} alt={m.prompt || "Image créée par EVA"} />
        </div>
      )}
    </div>
  );
}
