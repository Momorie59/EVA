import { useCallback, useEffect, useState } from "react";
import { useAuth } from "./AuthGate";
import { api } from "../api";
import { GUIDE } from "../PageGuide";

const FEAT = {
  voice: ["🎙️", "Voix", "Parle à EVA et écoute ses réponses."],
  web: ["🌐", "Internet", "EVA cherche des infos sur le web pour toi."],
  images: ["🖼️", "Images", "Crée et retouche des images : « dessine un dragon bleu »."],
  files: ["📁", "Fichiers", "Documents, projets, impression."],
  home: ["🏠", "Maison", "Lumières, prises et scènes de la maison."],
  google: ["📅", "Google", "Ton agenda et tes e-mails."],
  notify: ["💬", "Messages", "Notifications Telegram."],
  carnets: ["📓", "Carnets", "Des notes en sections et pages, à partager avec d'autres."],
  salon: ["👥", "Salon", "Voir qui est connecté, discuter, appeler en voix ou en vidéo."],
  code: ["🛠️", "Code & système", "Terminal, Docker, réseau : pour les personnes de confiance."],
};
const ALL = Object.keys(FEAT);
const ROLE_NAME = { admin: "administrateur", user: "adulte", teen: "adolescent", child: "enfant", guest: "invité" };

// Visite guidée : 3 à 5 étapes selon la personne (son profil et les fonctionnalités qu'on lui a ouvertes).
export function tourSteps(role, features, name) {
  const f = role === "admin" ? ALL : features;
  const has = (x) => f.includes(x);
  const list = f.filter((x) => FEAT[x] && x !== "code" && x !== "notify").map((x) => `${FEAT[x][0]} ${FEAT[x][1]}`).join(" · ");
  const hi = name ? `Bienvenue ${name} !` : "Bienvenue !";
  const aide = { icon: "❓", title: "Besoin d'aide ?", body: "Le bouton ? en haut à droite est toujours là : il explique ce que tu peux faire dans l'onglet où tu es, rappelle tes fonctionnalités et relance cette visite quand tu veux. Tu peux fermer cette visite à tout moment." };
  if (role === "child") {
    return [
      { icon: "👋", title: hi, body: "Moi, c'est EVA, ton assistante. Je vis dans la maison : ce que tu me dis reste ici, rien ne part sur Internet." },
      { icon: "💬", title: "Parle-moi", body: has("voice") ? "Écris-moi ou appuie sur « Parler » pour me parler. Pose-moi des questions, demande-moi une histoire ou de l'aide pour tes devoirs." : "Écris-moi une question, demande-moi une histoire ou de l'aide pour tes devoirs." },
      { icon: "🎨", title: "Mes pouvoirs pour toi", body: has("images") ? "Je sais dessiner ! Dis par exemple « dessine un chat astronaute » et regarde dans l'onglet Images." : "Je peux répondre à tes questions, raconter des histoires et t'aider à apprendre." },
      aide,
    ];
  }
  if (role === "guest") {
    return [
      { icon: "👋", title: hi, body: "EVA est un assistant qui fonctionne entièrement chez son propriétaire : tes messages ne partent pas chez un grand service en ligne." },
      { icon: "💬", title: "Écris ta question", body: "Dans l'onglet Conversation, pose ta question en français. EVA te répond et, quand elle doit faire une action, elle te le dit." },
      { icon: "🔎", title: "Ce que tu peux utiliser", body: list ? `Pour toi : ${list}. Pour en avoir plus, demande à la personne qui t'a invité(e).` : "Ton accès est limité ; demande à la personne qui t'a invité(e) d'ouvrir d'autres fonctions." },
      aide,
    ];
  }
  if (role === "admin") {
    return [
      { icon: "👋", title: hi, body: "EVA est ton assistante personnelle 100 % locale : modèles IA sur ton serveur, données chez toi. Cette visite rapide fait le tour de ce que tu peux régler." },
      { icon: "💬", title: "Parle ou écris", body: "Conversation, micro, images, fichiers : demande-lui la météo, des rappels, de contrôler la maison. Toute action sensible te demande ton accord avant de s'exécuter." },
      { icon: "🧰", title: "Ton atelier", body: "Tableau de bord (état du NAS et du serveur IA), Agents (décris-en un en une phrase), Skills, Sources, Maison, Images, Salon pour discuter et appeler les autres." },
      { icon: "🔐", title: "Les personnes et la sécurité", body: "Dans Paramètres › Sécurité & données : un compte par personne, profils (adulte, ado, enfant, invité), groupes, fonctionnalités à activer par personne, double authentification, HTTPS. Pour des amis chez eux : guide ACCES-A-DISTANCE.md." },
      aide,
    ];
  }
  const who = role === "teen" ? "EVA adapte ses réponses à ton âge." : "EVA tourne chez son propriétaire : tes messages restent à la maison.";
  return [
    { icon: "👋", title: hi, body: `${who} Voici en 5 étapes comment t'en servir.` },
    { icon: "💬", title: "Parle ou écris", body: has("voice") ? "Dans Conversation, écris ta demande ou appuie sur « Parler ». Tu peux lui demander de t'expliquer, d'écrire, de résumer, de te rappeler quelque chose." : "Dans Conversation, écris ta demande : explique-moi, écris, résume, rappelle-moi." },
    { icon: "✨", title: "Ce que tu peux faire", body: list ? `Tes fonctionnalités : ${list}.` : "Pose-lui des questions et laisse-la t'aider." },
    { icon: "🗂️", title: "S'organiser et partager", body: `Les Listes servent aux courses et aux tâches${has("carnets") ? ", les Carnets à écrire et partager des notes" : ""}${has("salon") ? ", le Salon à discuter ou appeler les autres personnes connectées (écrit, voix, vidéo)" : ""}${has("files") ? ", les Projets à ranger tes documents" : ""}.` },
    aide,
  ];
}

export function Tour({ role, features, name, onClose, onDone }) {
  const steps = tourSteps(role, features, name);
  const [i, setI] = useState(0);
  const s = steps[i];
  const last = i === steps.length - 1;
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape") onClose(); if (e.key === "ArrowRight" && !last) setI((n) => n + 1); if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1)); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [last, onClose]);
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label="Visite guidée d'EVA" data-testid="tour">
      <div className="tour__card">
        <button className="tour__x" onClick={onClose} aria-label="Fermer la visite" data-testid="tour-close">✕</button>
        <div className="tour__icon" aria-hidden="true">{s.icon}</div>
        <h2 className="tour__title">{s.title}</h2>
        <p className="tour__body" data-testid="tour-body">{s.body}</p>
        <div className="tour__dots" aria-hidden="true">{steps.map((_, n) => <i key={n} className={n === i ? "is-on" : n < i ? "is-done" : ""} />)}</div>
        <div className="tour__nav">
          <button className="btn btn--ghost" onClick={onClose} data-testid="tour-skip">Passer</button>
          <span className="tour__step">{i + 1} / {steps.length}</span>
          {i > 0 && <button className="btn" onClick={() => setI(i - 1)}>Précédent</button>}
          {!last ? <button className="btn btn--primary" onClick={() => setI(i + 1)} data-testid="tour-next" autoFocus>Suivant</button>
            : <button className="btn btn--primary" onClick={onDone} data-testid="tour-done" autoFocus>C'est parti !</button>}
        </div>
      </div>
    </div>
  );
}

const SEEN_LS = "eva.tour.seen";

// Bouton « ? » en haut à droite + visite guidée de première connexion (une fois par personne, enregistrée côté serveur).
export default function HelpLayer({ view }) {
  const auth = useAuth();
  const [tour, setTour] = useState(false);
  const [panel, setPanel] = useState(false);
  const role = auth.required ? auth.role || "user" : "admin";
  const features = auth.required ? auth.features || [] : ALL;
  const key = auth.required ? auth.user || "" : "";

  useEffect(() => {
    let off = false;
    // les navigateurs pilotés par des tests automatiques ne reçoivent pas la visite d'office (sauf demande explicite)
    try { if (navigator.webdriver && !localStorage.getItem("eva.tour.force")) return undefined; } catch { /* ignoré */ }
    if (auth.required) api("/api/tour").then((d) => { if (!off && !d.seen) setTour(true); }).catch(() => {});
    else { try { if (!localStorage.getItem(SEEN_LS)) setTour(true); } catch { /* stockage indisponible */ } }
    return () => { off = true; };
  }, [auth.required, key]);

  const finish = useCallback(async () => {
    setTour(false);
    if (auth.required) await api("/api/tour/seen", { method: "POST" }).catch(() => {});
    else { try { localStorage.setItem(SEEN_LS, "1"); } catch { /* ignoré */ } }
  }, [auth.required]);

  useEffect(() => {
    if (!panel) return undefined;
    const k = (e) => { if (e.key === "Escape") setPanel(false); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [panel]);

  const here = GUIDE[view];
  const mine = (role === "admin" ? ALL : features).filter((x) => FEAT[x]);
  return (
    <>
      <button className="helpbtn" onClick={() => setPanel((v) => !v)} aria-label="Aide" aria-expanded={panel} title="Aide" data-testid="help-btn">?</button>
      {panel && (
        <>
          <div className="helppanel__shade" onClick={() => setPanel(false)} />
          <aside className="helppanel" role="dialog" aria-label="Aide" data-testid="help-panel">
            <h3>Aide <small>profil {ROLE_NAME[role] || role}</small></h3>
            <button className="btn btn--primary" onClick={() => { setPanel(false); setTour(true); }} data-testid="help-tour">▶ Revoir la visite guidée</button>
            {here && (<><h4>Ce que tu peux faire ici</h4><ul>{here.map((t) => <li key={t}>{t}</li>)}</ul></>)}
            <h4>Tes fonctionnalités</h4>
            <ul className="helppanel__feats">{mine.map((x) => <li key={x}><span aria-hidden="true">{FEAT[x][0]}</span> <b>{FEAT[x][1]}</b> — {FEAT[x][2]}</li>)}</ul>
            <p className="card__hint">Il manque quelque chose ? Demande à l'administrateur d'ouvrir la fonctionnalité pour toi.</p>
          </aside>
        </>
      )}
      {tour && <Tour role={role} features={features} name={auth.user || ""} onClose={finish} onDone={finish} />}
    </>
  );
}
