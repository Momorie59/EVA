import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { postBinary } from "../hooks/useIdentity";

const TEXT = {
  center: "Regarde droit vers la caméra",
  no_face: "Je ne te vois pas : place ton visage dans l'ovale",
  multiple: "Une seule personne devant la caméra, s'il te plaît",
  unknown: "Je ne te reconnais pas… rapproche-toi, regarde de face",
};
const TURN = { left: "Tourne doucement la tête vers TA GAUCHE ←", right: "Tourne doucement la tête vers TA DROITE →" };

// Vérification « visage vivant » en direct : EVA te demande de tourner la tête (gauche/droite, ordre aléatoire).
export default function LiveCheck({ open, onClose, onVerified }) {
  const videoRef = useRef(null);
  const [msg, setMsg] = useState("Démarrage de la caméra…");
  const [steps, setSteps] = useState([]);
  const [done, setDone] = useState(0);
  const [state, setState] = useState("run"); // run | ok | failed
  const [round, setRound] = useState(0);
  // Les fonctions passées par App changent à chaque rendu : on les garde en référence pour ne pas relancer la caméra.
  const cb = useRef({});
  cb.current = { onClose, onVerified };

  useEffect(() => {
    if (!open) return undefined;
    let stopped = false, stream = null, timer = null, challenge = null;
    setState("run"); setDone(0); setSteps([]); setMsg("Démarrage de la caméra…");
    const finish = (st, text) => { setState(st); setMsg(text); stopped = true; stream?.getTracks().forEach((t) => t.stop()); };

    async function tick() {
      if (stopped) return;
      const v = videoRef.current;
      try {
        if (v?.videoWidth) {
          const sc = Math.min(1, 480 / v.videoWidth);
          const c = document.createElement("canvas");
          c.width = Math.round(v.videoWidth * sc); c.height = Math.round(v.videoHeight * sc);
          c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
          const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.8));
          const r = await postBinary(`/api/identity/liveness/frame?challenge=${challenge.challenge}`, blob, 6000);
          if (stopped) return;
          if (r.status === "ok") { cb.current.onVerified(r.name, r.token); finish("ok", `Bonjour ${r.name} ✓ vérifié en direct`); setDone(2); setTimeout(() => cb.current.onClose(), 1400); return; }
          if (r.status === "failed") { finish("failed", r.reason || "Vérification échouée."); return; }
          if (r.status === "turn") { setDone(r.index); setMsg(TURN[r.step]); }
          else if (r.status === "center") { setDone(r.index || 0); setMsg(r.index > 0 ? "Bien ! Reviens face à la caméra…" : TEXT.center); }
          else setMsg(TEXT[r.status] || "…");
        }
      } catch (e) {
        if (!stopped) { finish("failed", e.message); return; }
      }
      if (!stopped) timer = setTimeout(tick, 350);
    }

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        challenge = await api("/api/identity/liveness/start", { method: "POST" });
        setSteps(challenge.steps);
        setMsg(TEXT.center);
        tick();
      } catch (e) { finish("failed", e.message.includes("Permission") ? "Caméra refusée." : e.message); }
    })();
    return () => { stopped = true; clearTimeout(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, [open, round]);

  if (!open) return null;
  return (
    <div className="stage" role="dialog" aria-label="Vérification du visage" data-testid="livecheck">
      <div className="stage__panel live">
        <header className="stage__head">
          <span className="stage__title">Vérification du visage en direct</span>
          <span className="stage__tools"><button type="button" onClick={onClose} aria-label="Fermer">✕</button></span>
        </header>
        <div className="live__body">
          <div className={`live__video ${state === "ok" ? "is-ok" : state === "failed" ? "is-bad" : ""}`}>
            <video ref={videoRef} playsInline muted />
            <i className="live__oval" />
          </div>
          <p className="live__msg" data-testid="live-msg">{msg}</p>
          <div className="live__steps">{[0, 1].map((i) => <span key={i} className={i < done ? "is-on" : ""}>{i < done ? "✓" : i + 1}</span>)}</div>
          {state === "failed" && <button type="button" className="btn btn--primary" onClick={() => setRound((n) => n + 1)}>Réessayer</button>}
        </div>
      </div>
    </div>
  );
}
