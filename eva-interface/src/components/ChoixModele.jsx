import { useEffect, useState } from "react";
import { api } from "../api";
import ModelPicker from "./ModelPicker";

// Choix de l'IA pour la conversation en cours (même réglage partout : page Conversation et accueil EVA).
export default function ChoixModele({ sessionId, lastModel }) {
  const [installed, setInstalled] = useState([]);
  const [forced, setForced] = useState("");
  useEffect(() => { api("/api/models").then((d) => setInstalled((d.installed || []).filter((m) => !m.embedding))).catch(() => {}); }, []);
  useEffect(() => {
    setForced("");
    if (!sessionId) return;
    api(`/api/sessions/${encodeURIComponent(sessionId)}/model`).then((d) => setForced(d?.model || "")).catch(() => {});
  }, [sessionId]);
  useEffect(() => {
    const f = (e) => { if (e.detail?.sessionId === sessionId) setForced(e.detail.model || ""); };
    window.addEventListener("eva-modele", f);
    return () => window.removeEventListener("eva-modele", f);
  }, [sessionId]);
  async function choisir(name) {
    const avant = forced;
    setForced(name);
    try {
      await api(`/api/sessions/${encodeURIComponent(sessionId)}/model`, { method: "PUT", body: JSON.stringify({ model: name }) });
      window.dispatchEvent(new CustomEvent("eva-modele", { detail: { sessionId, model: name } }));
    } catch { setForced(avant); }
  }
  if (!installed.length) return null;
  return <ModelPicker modeles={installed} valeur={forced} onChange={choisir} dernier={lastModel} />;
}
