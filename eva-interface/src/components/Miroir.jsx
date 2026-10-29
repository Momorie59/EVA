import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import MessageText from "./MessageText";

// Mode miroir : plein écran noir (sous un miroir sans tain, seul le texte clair se voit). La caméra regarde toutes
// les 1,5 s ; EVA (sur le NAS) dit qui est là. Quelqu'un arrive : l'écran s'allume, salue la personne et affiche
// ses tuiles (heure, météo, agenda, colis, post-it). Plusieurs personnes ou un inconnu : mode discret (rien de
// personnel). Personne pendant 45 s : l'écran redevient noir. On parle à EVA avec le mot d'éveil, ou en touchant l'écran.
const PREFS = "eva.miroir";
const lirePrefs = () => { try { return { saluer: true, ecouter: false, ...(JSON.parse(localStorage.getItem(PREFS) || "{}")) }; } catch { return { saluer: true, ecouter: false }; } };
const ABSENCE_MS = 45000;
const SALUT_MS = 2 * 3600 * 1000;

export default function Miroir({ onQuitter, onMicro, onDire, ecoute, parle, etat, derniereReponse, connecte }) {
  const videoRef = useRef(null); const canvasRef = useRef(null);
  const [camera, setCamera] = useState("");                  // "" | "ok" | message d'erreur
  const [vu, setVu] = useState(null);                        // dernier résultat de /api/miroir/regarder
  const [present, setPresent] = useState(false);
  const [cartes, setCartes] = useState([]);
  const [heure, setHeure] = useState(new Date());
  const [prefs, setPrefs] = useState(lirePrefs);
  const [reglages, setReglages] = useState(false);
  const dejaLaRef = useRef(derniereReponse?.id);              // réponse déjà à l'écran avant le miroir : pas affichée
  const dernierVuRef = useRef(0); const salutsRef = useRef({}); const quiRef = useRef("");

  const regler = (chg) => setPrefs((p) => { const n = { ...p, ...chg }; try { localStorage.setItem(PREFS, JSON.stringify(n)); } catch { /* ignoré */ } return n; });

  useEffect(() => { const t = setInterval(() => setHeure(new Date()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { document.documentElement.requestFullscreen?.().catch(() => {}); return () => { if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {}); }; }, []);
  useEffect(() => {                                          // Échap : quitter
    const k = (e) => { if (e.key === "Escape") onQuitter(); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [onQuitter]);

  // Caméra
  useEffect(() => {
    let flux = null;
    navigator.mediaDevices?.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false })
      .then((s) => { flux = s; if (videoRef.current) { videoRef.current.srcObject = s; videoRef.current.play().catch(() => {}); } setCamera("ok"); })
      .catch((e) => setCamera(e?.name === "NotAllowedError" ? "Caméra refusée : autorise-la pour que le miroir reconnaisse la famille." : "Pas de caméra : le miroir reste allumé."));
    return () => flux?.getTracks().forEach((t) => t.stop());
  }, []);

  // Regarder toutes les 1,5 s (seulement une petite image, jamais gardée)
  useEffect(() => {
    if (camera !== "ok") return undefined;
    let stop = false; let occupe = false;
    const t = setInterval(async () => {
      const v = videoRef.current; const c = canvasRef.current;
      if (stop || occupe || !v || !c || !v.videoWidth) return;
      occupe = true;
      c.width = 320; c.height = Math.round(320 * v.videoHeight / v.videoWidth);
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      try {
        const r = await api("/api/miroir/regarder", { method: "POST", body: JSON.stringify({ image: c.toDataURL("image/jpeg", 0.7) }) });
        setVu(r);
        if (r.visages > 0) dernierVuRef.current = Date.now();
      } catch (e) { setVu({ erreur: e.message }); }
      occupe = false;
    }, 1500);
    return () => { stop = true; clearInterval(t); };
  }, [camera]);

  // Présence : allumé tant que quelqu'un a été vu il y a moins de 45 s (toujours allumé sans caméra)
  useEffect(() => {
    const t = setInterval(() => setPresent(camera !== "ok" || Date.now() - dernierVuRef.current < ABSENCE_MS || ecoute || parle), 500);
    return () => clearInterval(t);
  }, [camera, ecoute, parle]);

  const qui = vu && !vu.discret && vu.personnes?.length === 1 ? vu.personnes[0].qui : "";

  // Tuiles : celles de la personne reconnue, sinon générales ; rafraîchies toutes les 5 min
  const chargerCartes = useCallback((q) => api(`/api/miroir/cartes${q ? `?qui=${encodeURIComponent(q)}` : ""}`).then((d) => setCartes(d.tuiles || [])).catch(() => {}), []);
  useEffect(() => { if (!present) return undefined; chargerCartes(qui); const t = setInterval(() => chargerCartes(qui), 300000); return () => clearInterval(t); }, [present, qui, chargerCartes]);

  // Arrivée d'une personne reconnue : salut (une fois toutes les 2 h), écoute si demandé
  useEffect(() => {
    if (!qui || qui === quiRef.current) { if (!qui && vu?.visages === 0) quiRef.current = ""; return; }
    quiRef.current = qui;
    const avant = salutsRef.current[qui] || 0;
    if (Date.now() - avant < SALUT_MS) return;
    salutsRef.current[qui] = Date.now();
    const h = new Date().getHours();
    if (prefs.saluer) onDire?.(`${h < 18 ? "Bonjour" : "Bonsoir"} ${qui} !`);
    if (prefs.ecouter) setTimeout(() => onMicro?.(), prefs.saluer ? 1800 : 0);
  }, [qui]); // eslint-disable-line react-hooks/exhaustive-deps

  const h = heure.getHours();
  const salutation = qui ? `${h < 5 || h >= 18 ? "Bonsoir" : "Bonjour"} ${qui}` : vu?.discret && vu.visages > 1 ? "Bonjour à tous" : "";
  const statut = !connecte ? "EVA hors ligne" : ecoute ? "Je t'écoute…" : etat === "thinking" || etat === "acting" ? "Je réfléchis…" : parle ? "" : "Dis « EVA… » ou touche l'écran";

  return (
    <div className={`miroir ${present ? "is-on" : "is-off"}`} data-testid="miroir" onClick={(e) => { if (e.target === e.currentTarget || e.target.closest(".miroir__centre")) onMicro?.(); }}>
      <video ref={videoRef} muted playsInline className="miroir__video" />
      <canvas ref={canvasRef} hidden />
      <div className="miroir__haut">
        <div>
          <div className="miroir__heure">{heure.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</div>
          <div className="miroir__date">{heure.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}</div>
        </div>
        <div className="miroir__outils">
          <button onClick={() => setReglages((v) => !v)} aria-label="Réglages du miroir">⚙</button>
          <button onClick={onQuitter} aria-label="Quitter le miroir" data-testid="miroir-quitter">✕</button>
        </div>
      </div>
      {reglages && (
        <div className="miroir__reglages" onClick={(e) => e.stopPropagation()}>
          <label><input type="checkbox" checked={prefs.saluer} onChange={(e) => regler({ saluer: e.target.checked })} /> Saluer à voix haute la personne reconnue</label>
          <label><input type="checkbox" checked={prefs.ecouter} onChange={(e) => regler({ ecouter: e.target.checked })} /> Écouter tout de suite quand quelqu'un de la famille arrive</label>
          <small>Visages : Maison › Miroir. Aucune image n'est gardée ; seules les empreintes des visages appris le sont, sur le NAS.</small>
        </div>
      )}
      <div className="miroir__centre">
        {salutation && <div className="miroir__salut" data-testid="miroir-salut">{salutation}</div>}
        {derniereReponse && derniereReponse.id !== dejaLaRef.current && present && <div className="miroir__reponse"><MessageText text={derniereReponse.text} /></div>}
        <div className={`miroir__statut ${ecoute ? "is-ecoute" : ""}`}>{statut}</div>
      </div>
      <div className="miroir__cartes">
        {cartes.map((t, i) => (
          <div key={i} className="miroir__carte">
            <span className="miroir__carte-titre">{t.icone} {t.titre}</span>
            {(t.lignes || []).map((l, j) => <span key={j}>{l}</span>)}
          </div>
        ))}
        {vu?.discret && vu.visages > 1 && <div className="miroir__carte miroir__discret">🔒 Plusieurs personnes : mode discret</div>}
      </div>
      {camera && camera !== "ok" && <div className="miroir__note">{camera}</div>}
      {vu?.erreur && <div className="miroir__note">{vu.erreur}</div>}
    </div>
  );
}
