import { useEffect, useMemo, useState } from "react";
import ModelRouterCard from "../ModelRouterCard";
import ModelManagerCard from "../ModelManagerCard";
import ImageGenCard from "../ImageGenCard";
import ImageModelsCard from "../ImageModelsCard";
import LlmOptionsCard from "../LlmOptionsCard";
import PersonalityCard from "../PersonalityCard";
import ThemeCard from "../ThemeCard";
import GoogleCard from "../GoogleCard";
import HomeAssistantCard from "../HomeAssistantCard";
import TelegramCard from "../TelegramCard";
import ConnecteursCard from "../ConnecteursCard";
import SpotifyCard from "../SpotifyCard";
import AgendasCard from "../AgendasCard";
import RaccourcisCard from "../RaccourcisCard";
import McpServeurCard from "../McpServeurCard";
import VoiceCard from "../VoiceCard";
import McpCard from "../McpCard";
import BackupCard from "../BackupCard";
import IdentityCard from "../IdentityCard";
import Nis2Card from "../Nis2Card";
import AiServerCard from "../AiServerCard";
import CitiesCard from "../CitiesCard";
import PratiqueCard from "../PratiqueCard";
import AccessCard from "../AccessCard";
import QuotasCard from "../QuotasCard";
import MesDonneesCard from "../MesDonneesCard";
import AutorisationsCard from "../AutorisationsCard";
import GitHubCard from "../GitHubCard";
import CodeAgentCard from "../CodeAgentCard";
import VitesseCard from "../VitesseCard";
import CompilationCard from "../CompilationCard";
import ModulesCard from "../ModulesCard";
import HttpsCard from "../HttpsCard";
import MindCard from "../MindCard";
import { CORE_URL, WS_URL, authHeaders } from "../../urls";
import { useAuth } from "../AuthGate";
import SecurityCard from "../SecurityCard";
import UsersCard from "../UsersCard";
import AuditCard from "../AuditCard";
import ApiCatalogCard from "../ApiCatalogCard";
import CloudAiCard from "../CloudAiCard";
import AirLLMCard from "../AirLLMCard";
import InstallCard from "../InstallCard";

export default function SettingsPage({ connected, offlineReason }) {
  const [health, setHealth] = useState(null);
  const auth = useAuth();

  useEffect(() => {
    fetch(`${CORE_URL}/api/health`, { headers: authHeaders() })
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ error: true }));
  }, []);

  const rows = [
    ["Connexion à EVA CORE", connected ? "connecté" : `déconnecté — ${offlineReason || ""}`],
    ["Modèle", health?.model || "—"],
    ["Serveur IA (Ollama)", health?.ollama_host || "—"],
    ["Workspace", health?.workspace || "—"],
    ["Adresse WebSocket", WS_URL],
    ["Authentification", auth.required ? `connexion activée (${auth.user || "—"})` : "aucune (réseau local de confiance) — à activer ci-dessous"],
  ];

  const admin = !auth.required || auth.role === "admin";
  const overview = (
    <>
      <div className="card">
        <span className="card__label">État d'EVA</span>
        <dl className="kv">
          {rows.map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
          ))}
        </dl>
      </div>
      <div className="card">
        <span className="card__label">Outils disponibles ({health?.tools?.length ?? 0})</span>
        <div className="chips">
          {(health?.tools || []).map((t) => <span key={t} className="chip">{t}</span>)}
        </div>
      </div>
    </>
  );

  // Catégories : un seul groupe de cartes affiché à la fois ; la recherche trouve la bonne catégorie par mot-clé.
  const cats = useMemo(() => [
    { id: "overview", icon: "◎", label: "Vue d'ensemble", hint: "État de la connexion, outils d'EVA.", words: "état connexion outils serveur workspace websocket", body: overview },
    { id: "ia", icon: "🧠", label: "Intelligence", hint: "Modèles de langage, choix automatique, personnalité, compréhension.",
      words: "compilation compiler conversations résumé fil nuit vitesse lent lenteur rechargement mémoire vidéo vram agent de code aider programmation modèle modèles ollama llm router choix automatique personnalité compréhension mémoire précision hugging face cloud marché télécharger airllm air llm gros modèle repli",
      body: <><VitesseCard />{admin && <CompilationCard />}<ModelRouterCard /><ModelManagerCard /><LlmOptionsCard /><PersonalityCard />{admin && <CodeAgentCard />}{admin && <CloudAiCard />}{admin && <AirLLMCard />}</> },
    { id: "mind", icon: "🧠", label: "Apprentissage", hint: "Règles proposées d'après tes avis, sujets appris du net.",
      words: "apprendre apprentissage règles avis pouce sujet apprend toute seule étudier internet", body: <MindCard /> },
    { id: "images", icon: "🎨", label: "Images", hint: "Serveur d'images, choix et téléchargement des modèles. Créer et retoucher : onglet Images.",
      words: "image images dessin stable diffusion serveur jeton modèle sd turbo sdxl purge", body: <><ImageGenCard /><ImageModelsCard /></> },
    { id: "voice", icon: "🎙️", label: "Voix & personnes", hint: "Voix d'EVA, micro, reconnaissance des personnes.",
      words: "voix micro whisper piper reconnaissance visage personnes identité parole", body: <><VoiceCard /><IdentityCard /></> },
    { id: "services", icon: "🔌", label: "Services connectés", hint: "Google, Home Assistant, Telegram, OBS, Discord, Instagram, appels, outils externes, API publiques.",
      words: "poubelles poubelle ramassage déchets vacances scolaires zone jours fériés carburant essence gazole actualités rss journal éphéméride infos pratiques raccourci raccourcis iphone siri android tasker agenda agendas ical ics webcal calendrier vacances spotify musique playlist serveur mcp jeton claude desktop cursor obs stream live discord instagram twilio appel sms téléphone diffusion github git dépôt dépôts jeton ville villes météo ville par défaut serveur ia dashboard gpu google gmail agenda home assistant telegram mcp outils externes api maison connecteur",
      body: <><CitiesCard /><PratiqueCard /><GoogleCard /><AgendasCard /><RaccourcisCard />{admin && <GitHubCard />}<HomeAssistantCard /><TelegramCard />{admin && <SpotifyCard />}{admin && <ConnecteursCard />}<McpCard />{admin && <McpServeurCard />}{admin && <AiServerCard />}{admin && <ApiCatalogCard />}</> },
    { id: "security", icon: "🔒", label: "Sécurité & données", hint: "Connexion, utilisateurs, journal d'accès, sauvegarde.",
      words: "autorisations toujours autoriser accord confirmation mes données export exporter effacer rgpd supprimer mes données https tls certificat http fonctionnalités groupes droits voix autorisations nis2 conformité incident sécurité mot de passe connexion utilisateur utilisateurs administrateur journal audit sauvegarde backup restauration compte",
      body: <><SecurityCard /><AutorisationsCard />{admin && <HttpsCard />}{admin && <Nis2Card />}{auth.required && auth.role === "admin" && <><UsersCard /><AccessCard /><QuotasCard /><AuditCard /></>}<MesDonneesCard admin={auth.required && auth.role === "admin"} /><BackupCard /></> },
    { id: "modules", icon: "🧩", label: "Modules", hint: "Fonctions en plus à activer : wiki, livre de recettes.",
      words: "modules module wiki recettes recette livre cuisine inventaire prêts plugins activer désactiver", body: admin ? <ModulesCard /> : <div className="card"><p className="card__hint">Seul l'administrateur active les modules.</p></div> },
    { id: "look", icon: "✨", label: "Apparence & application", hint: "Thème, couleurs, installation sur téléphone ou ordinateur.",
      words: "apparence thème couleur application installer téléphone pwa", body: <><ThemeCard /><InstallCard /></> },
  ], [admin, auth.required, auth.role, auth.user, health, connected, offlineReason]); // eslint-disable-line react-hooks/exhaustive-deps

  const [cat, setCat] = useState(() => { try { return window.localStorage.getItem("eva.settings.cat") || "overview"; } catch { return "overview"; } });
  const [q, setQ] = useState("");
  const norm = (t) => t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const found = q.trim() ? cats.filter((c) => norm(`${c.label} ${c.words}`).includes(norm(q.trim()))) : null;
  const current = cats.find((c) => c.id === cat) || cats[0];
  function pick(id) { setCat(id); setQ(""); try { window.localStorage.setItem("eva.settings.cat", id); } catch { /* stockage indisponible */ } }

  return (
    <section className="page" data-testid="settings-page">
      <header className="page__header">
        <h1>Paramètres</h1>
        <span className="page__sub">{current.hint}</span>
      </header>
      <div className="settings">
        <aside className="settings__nav">
          <input className="settings__search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un réglage…" aria-label="Rechercher un réglage" data-testid="settings-search" />
          <nav aria-label="Catégories de réglages">
            {cats.map((c) => (
              <button key={c.id} className={`settings__cat ${!found && c.id === current.id ? "is-on" : ""} ${found && found.some((f) => f.id === c.id) ? "is-hit" : ""}`}
                onClick={() => pick(c.id)} data-testid={`settings-cat-${c.id}`}>
                <span className="settings__ico" aria-hidden="true">{c.icon}</span><span>{c.label}</span>
              </button>
            ))}
          </nav>
        </aside>
        <div className="settings__body">
          {found ? (
            found.length ? <p className="page__sub" data-testid="settings-found">Résultats pour « {q} » — clique sur une catégorie surlignée : {found.map((c) => c.label).join(", ")}.</p>
              : <p className="page__sub">Aucun réglage ne correspond à « {q} ».</p>
          ) : <div className="settings__cards" key={current.id}>{current.body}</div>}
        </div>
      </div>
    </section>
  );
}
