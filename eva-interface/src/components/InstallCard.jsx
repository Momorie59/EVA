import { useEffect, useState } from "react";

// Installation d'EVA comme application (Android/Chrome, ordinateur) — page d'accueil de ton téléphone.
export default function InstallCard() {
  const [evt, setEvt] = useState(null);
  const [done, setDone] = useState(false);
  const standalone = typeof window !== "undefined" && (window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone);
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setEvt(e); };
    const onInstalled = () => { setDone(true); setEvt(null); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);
  async function install() { if (!evt) return; evt.prompt(); await evt.userChoice.catch(() => {}); setEvt(null); }
  const secure = typeof window !== "undefined" && window.isSecureContext;
  return (
    <section className="card" data-testid="install-card">
      <span className="card__label">Application (téléphone, ordinateur)</span>
      {standalone || done ? <p className="page__sub">EVA est installée sur cet appareil.</p> : (
        <>
          <p className="page__sub">Installe EVA comme une application : icône sur l'écran d'accueil, plein écran, ouverture instantanée.</p>
          {evt && <div className="pj-row"><button className="btn" onClick={install} data-testid="install-btn">Installer EVA sur cet appareil</button></div>}
          {!evt && (
            <ul className="pj-trash__list">
              <li><span><b>Android (Chrome)</b> : menu ⋮ › « Installer l'application » (ou « Ajouter à l'écran d'accueil »).</span></li>
              <li><span><b>iPhone (Safari)</b> : bouton Partager › « Sur l'écran d'accueil ».</span></li>
              <li><span><b>Ordinateur (Chrome/Edge)</b> : icône d'installation dans la barre d'adresse.</span></li>
            </ul>
          )}
          {!secure && <p className="page__warn">Cette page n'est pas en HTTPS : l'installation n'est proposée qu'en HTTPS (adresse en https://…:8443). Sur téléphone, le certificat local de Caddy doit aussi être installé comme certificat de confiance (voir MANUEL-INSTALLATION.md, §6.2).</p>}
        </>
      )}
    </section>
  );
}
