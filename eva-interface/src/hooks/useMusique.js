import { useCallback, useRef, useState } from "react";
import { api } from "../api";

const DUREE_MS = 12000;
export const QUESTION_MUSIQUE = /(quel(?:le)?|c.?est quoi|qu.?est.?ce que c.?est|reconna\w+|trouve).{0,25}(musique|chanson|morceau|titre)\b/i;

// « C'est quoi cette musique ? » : 12 s de micro → empreinte sonore côté EVA (AcoustID). L'extrait n'est pas conservé.
export function useMusique() {
  const [etat, setEtat] = useState("off");          // off | ecoute | analyse | fini | erreur
  const [resultat, setResultat] = useState(null);
  const [reste, setReste] = useState(0);
  const enCours = useRef(false);

  const ecouter = useCallback(async () => {
    if (enCours.current) return null;
    enCours.current = true; setResultat(null); setEtat("ecoute");
    let flux;
    try {
      flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
      const rec = new MediaRecorder(flux, type ? { mimeType: type } : undefined);
      const morceaux = [];
      rec.ondataavailable = (e) => e.data.size && morceaux.push(e.data);
      const fin = new Promise((ok) => { rec.onstop = ok; });
      rec.start();
      const debut = Date.now();
      const t = setInterval(() => setReste(Math.max(0, Math.ceil((DUREE_MS - (Date.now() - debut)) / 1000))), 250);
      await new Promise((ok) => setTimeout(ok, DUREE_MS));
      clearInterval(t); rec.stop(); await fin;
      setEtat("analyse");
      const blob = new Blob(morceaux, { type: rec.mimeType || "audio/webm" });
      const ext = (rec.mimeType || "").includes("mp4") ? "m4a" : (rec.mimeType || "").includes("ogg") ? "ogg" : "webm";
      const r = await api(`/api/musique/reconnaitre?nom=extrait.${ext}`, { method: "POST", body: blob, headers: { "Content-Type": "application/octet-stream" } });
      setResultat(r); setEtat("fini");
      return r;
    } catch (e) {
      const r = { trouve: false, phrase: e?.name === "NotAllowedError" ? "Micro refusé : autorise-le dans le navigateur." : e.message || "Reconnaissance impossible." };
      setResultat(r); setEtat("erreur");
      return r;
    } finally {
      flux?.getTracks().forEach((x) => x.stop());
      enCours.current = false;
    }
  }, []);

  const fermer = useCallback(() => { setEtat("off"); setResultat(null); }, []);
  return { etat, resultat, reste, ecouter, fermer };
}
