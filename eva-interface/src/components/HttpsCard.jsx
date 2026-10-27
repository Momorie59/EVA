import { useEffect, useState } from "react";
import { api } from "../api";
import { CORE_URL, authHeaders } from "../urls";
import { confirmer } from "../confirmer";

// HTTPS : nécessaire pour le micro et la caméra sur téléphone ; coupé, EVA reste utilisable en texte sur le réseau local.
export default function HttpsCard() {
  const [on, setOn] = useState(null);
  const [names, setNames] = useState("");
  const [nmsg, setNmsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const secure = window.location.protocol === "https:";
  useEffect(() => { api("/api/https").then((d) => { setOn(d.enabled); setNames((d.names || []).join("\n")); }).catch((e) => setError(e.message)); }, []);

  async function saveNames() {
    setError(""); setNmsg("");
    try { const d = await api("/api/https/names", { method: "PUT", body: JSON.stringify({ names: names.split(/[\s,;]+/).filter(Boolean) }) }); setNames(d.names.join("\n")); setNmsg("Enregistré."); }
    catch (e) { setError(e.message); }
  }

  async function cert() {
    setError("");
    try {
      const res = await fetch(`${CORE_URL}/api/https/cert`, { headers: authHeaders() });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Erreur ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a"); a.href = url; a.download = "eva-certificat.crt"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) { setError(e.message); }
  }

  async function toggle() {
    const next = !on;
    const ask = next
      ? "Réactiver le HTTPS ? Tu seras redirigé vers l'adresse sécurisée (accepte le certificat une fois)."
      : "Désactiver le HTTPS ?\n\nLe micro, la caméra et l'installation en application ne marcheront plus sur téléphone. Mot de passe et codes circuleront sans chiffrement sur ton réseau.\n\nTu seras redirigé vers l'adresse http://.";
    if (!(await confirmer(ask))) return;
    setBusy(true); setError("");
    try {
      await api("/api/https", { method: "PUT", body: JSON.stringify({ enabled: next }) });
      setOn(next);
      setTimeout(() => { window.location.href = `${next ? "https:" : "http:"}//${window.location.host}/`; }, 1500);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <div className="card routercard" data-testid="https-card">
      <span className="card__label">Connexion sécurisée (HTTPS)</span>
      <p className="card__hint">
        {on === null ? "Chargement…" : on
          ? "HTTPS activé : indispensable pour le micro, la caméra et l'installation sur téléphone. Le navigateur affiche un avertissement la première fois (certificat auto-signé) : accepte-le une fois."
          : "HTTPS désactivé : plus d'avertissement de certificat, mais micro, caméra et installation en application sont bloqués hors du NAS. À réserver au réseau local."}
      </p>
      {!secure && on === false && <p className="page__warn">Tu es connecté en HTTP : mot de passe et codes ne sont pas chiffrés.</p>}
      {error && <p className="page__warn" role="alert">{error}</p>}
      {on && (
        <details className="pageguide" data-testid="https-names">
          <summary>🌍 Accéder à EVA sous un nom de domaine (amis, accès à distance)</summary>
          <p className="card__hint">Par défaut EVA accepte l'adresse du NAS et les noms de ton réseau local. Si tu y accèdes par un nom (ex. eva.mondomaine.fr ou une redirection), ajoute-le ici (un par ligne) : sans cela la page reste blanche. Chaque appareil devra faire confiance au certificat d'EVA (voir ci-dessous). Guide : ACCES-A-DISTANCE.md.</p>
          <textarea rows={3} value={names} onChange={(e) => setNames(e.target.value)} placeholder="eva.mondomaine.fr" data-testid="https-names-input" />
          <div className="agentform__actions"><button className="btn" onClick={saveNames} data-testid="https-names-save">Enregistrer les noms</button></div>
          {nmsg && <p className="page__sub">{nmsg}</p>}
        </details>
      )}
      {on && (
        <details className="pageguide" data-testid="https-cert">
          <summary>🔓 Supprimer l'avertissement « site non sécurisé »</summary>
          <p className="card__hint">Cet avertissement est normal : EVA fabrique elle-même son certificat (rien ne sort sur Internet). Installe le certificat d'EVA une fois sur chaque appareil et il disparaît, micro et caméra restent disponibles.</p>
          <p className="card__hint"><a href="/api/https/install" target="_blank" rel="noreferrer" data-testid="https-install-link">📄 Page d'installation en un clic (Windows, Android, iPhone, Mac)</a> — à ouvrir aussi sur chaque autre appareil, elle marche avant la connexion.</p>
          <button className="btn" onClick={cert} data-testid="https-cert-dl">Télécharger le certificat d'EVA</button>
          <ul>
            <li><b>Windows :</b> double-clic sur le fichier › Installer le certificat › Ordinateur local › « Placer tous les certificats dans le magasin suivant » › Autorités de certification racines de confiance. Relance le navigateur.</li>
            <li><b>Android :</b> Paramètres › Sécurité › Plus de paramètres › Chiffrement et identifiants › Installer un certificat › Certificat d'autorité (CA).</li>
            <li><b>iPhone :</b> ouvre le fichier › Réglages › Profil téléchargé › Installer ; puis Réglages › Général › Informations › Réglages des certificats › active la confiance pour « Caddy Local Authority ».</li>
            <li><b>Mac :</b> double-clic › Trousseau d'accès › ouvre le certificat › Faire confiance › « Toujours approuver ».</li>
          </ul>
        </details>
      )}
      <div className="agentform__actions">
        <button className="btn btn--primary" onClick={toggle} disabled={busy || on === null} data-testid="https-toggle">
          {busy ? "Changement en cours…" : on ? "Désactiver le HTTPS" : "Réactiver le HTTPS"}
        </button>
      </div>
    </div>
  );
}
