import { useState } from "react";

// « Ce que tu peux faire ici » : toutes les fonctions d'un onglet, repliable, pour s'y retrouver.
export const GUIDE = {
  chat: ["Parler ou écrire à EVA : questions, météo, actualités, rappels, notes", "Envoyer une image ou des fichiers à analyser (trombone)", "Demander « donne-moi les stats » : état du NAS et du serveur IA", "Dire « crée une image de… » pour dessiner", "Valider ou refuser les actions sensibles avant qu'elles s'exécutent"],
  overview: ["Voir d'un coup d'œil la santé du NAS et du serveur IA", "Changer de ville pour la météo (puces de villes)", "Suivre les conteneurs Docker et les jauges processeur, mémoire, disque", "Ouvrir le tableau de bord complet du serveur IA"],
  agents: ["Décrire en une phrase l'agent voulu : EVA le conçoit", "Choisir les outils qu'un agent peut utiliser", "Planifier un agent (tous les jours, toutes les semaines…)", "Lancer, mettre en pause ou supprimer un agent"],
  skills: ["Parcourir les compétences installées", "Installer depuis un dépôt GitHub entier, avec cases à cocher", "Lire le détail d'une compétence avant de l'activer"],
  sources: ["Ajouter des documents que EVA peut consulter", "Rechercher dans tes sources", "Retirer une source"],
  traces: ["Revoir pas à pas ce que EVA a fait et quels outils elle a utilisés", "Repérer une erreur ou une réponse lente"],
  learning: ["Voir ce qu'EVA a appris de tes évaluations", "Corriger ou effacer un apprentissage"],
  evolution: ["Suivre les améliorations proposées à EVA", "Accepter ou refuser une évolution"],
  projects: ["Parcourir et ouvrir les fichiers de tes projets", "Demander à EVA de les lire, résumer ou modifier"],
  salon: ["Voir qui est connecté à EVA en ce moment", "Discuter à l'écrit avec tout le monde (l'historique est gardé)", "Lancer ou rejoindre un appel vocal ou vidéo jusqu'à 6 personnes, sur ton réseau, sans Internet", "Couper ton micro ou ta caméra, raccrocher", "Les appels demandent HTTPS (micro et caméra)"],
  carnets: ["Écrire des notes en sections et en pages, comme dans un classeur", "Partager un carnet avec une personne, un groupe ou tout le monde, en lecture seule ou en modification", "Modifier à plusieurs : les changements des autres apparaissent tout seuls", "Un carnet non partagé reste privé (seul l'administrateur peut tout voir)"],
  maison: ["Piloter lumières, prises et scènes de la maison", "Créer et lancer des scènes"],
  images: ["Voir toutes les images créées", "Retoucher une image avec une phrase", "Supprimer ou télécharger une image"],
  lists: ["Créer des listes (courses, tâches…)", "Cocher, ajouter ou retirer des éléments"],
  papiers: ["Voir les échéances à venir : préavis de résiliation, renouvellements, paiements, impôts France et Italie, fins de garantie", "Déposer des dizaines de papiers d'un coup par glisser-déposer", "Vérifier et corriger ce qu'EVA n'a pas compris avec certitude", "Choisir les dossiers du NAS qu'EVA surveille et ce qu'elle fait des fichiers (Réglages)", "Dans la conversation : « quelles sont mes échéances ? », ou joindre un papier avec « range ça dans mes papiers »"],
  memory: ["Voir ce qu'EVA retient de toi", "Ajouter, corriger ou oublier un souvenir"],
  logs: ["Suivre en direct ce qui se passe dans EVA", "Chercher un message précis"],
  settings: ["Intelligence : choix automatique des modèles et suggestions Hugging Face", "Apparence, popups et thème", "Villes pour la météo", "Utilisateurs, profils, groupes et fonctionnalités autorisées", "Sécurité : double authentification, HTTPS, NIS2, journal d'audit", "Services : serveur IA, images, voix, Google, notifications"],
};

export default function PageGuide({ id }) {
  const [open, setOpen] = useState(false);
  const items = GUIDE[id];
  if (!items) return null;
  return (
    <details className="pageguide" open={open} onToggle={(e) => setOpen(e.currentTarget.open)} data-testid="page-guide">
      <summary>✨ Ce que tu peux faire ici</summary>
      <ul>{items.map((t) => <li key={t}>{t}</li>)}</ul>
    </details>
  );
}
