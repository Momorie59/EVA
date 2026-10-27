"""Sélection des outils proposés au modèle pour un tour de conversation.

Avec une quarantaine d'outils, un petit modèle local (8B) se trompe plus souvent et chaque tour coûte
~2000 tokens de description. On propose donc toujours un noyau d'outils, et les familles spécialisées
seulement si la demande (ou la précédente) les évoque. Le modèle peut toujours appeler un outil hors
sélection, mais seulement un outil de LECTURE : un outil qui change quelque chose doit avoir été proposé pour ce tour.

Règles de prudence (après un appel de papiers_corriger sur un simple « je m'appelle Paul ») :
- les messages précédents n'apportent que des outils de lecture ; un outil d'action n'est proposé que si le message
  ACTUEL l'évoque ;
- la description de chaque outil d'action rappelle au modèle qu'il ne s'en sert que sur demande explicite."""
import re

CORE = {
    "fs_list", "fs_read", "fs_write", "fs_append", "docs_search", "skill_list", "skill_read",
    "web_search", "web_fetch", "system_stats", "weather_get", "present", "poser_question", "plan_taches", "recherche_approfondie",
    "evolution_demander",
}

# Outils qui ne changent rien (consultation). Tout autre outil — y compris un outil MCP ou inconnu — est une ACTION.
LECTURE = {
    "ai_server_stats", "api_get", "api_search", "calendar_list", "dev_check", "device_list", "docker_logs", "docker_ps",
    "docs_search", "fs_grep", "fs_list", "fs_read", "fs_tree", "git_diff", "git_log", "git_status", "github_info", "gmail_read", "gmail_search",
    "ha_get", "ha_states", "list_show", "memoire_lister", "net_hosts", "net_probe", "note_list", "papiers_a_verifier",
    "papiers_echeances", "papiers_question", "present", "printer_list", "self_read", "role_run", "skill_list", "skill_read", "system_stats",
    "weather_get", "web_fetch", "web_search", "device_presence", "wiki_chercher", "wiki_lire", "recette_chercher", "recette_lire",
    "obs_etat", "instagram_stats", "poser_question", "plan_taches", "recherche_approfondie", "spotify_en_cours", "agenda_ics", "finances_resume", "finances_operations", "contenu_lister", "gmail_colis", "rappel_lister", "routine_lister", "agent_lister", "carnet_lister", "carnet_lire", "pc_ecran_voir", "navigateur_ouvrir", "navigateur_lire", "navigateur_capture",
}
# Écrire un fichier : seulement si le message actuel parle de fichier, d'écrire ou d'enregistrer.
_ECRITURE_FICHIER = re.compile(r"\b(fichiers?|[ée]cri\w*|enregistr\w*|sauvegard\w*|cr[ée]e\w*|r[ée]dige\w*|g[ée]n[èe]re\w*|"
                               r"ajoute\w*|compl[èe]te\w*|modifie\w*|note\w*|markdown|\.md|\.txt|\.csv|\.json|document\w*|rapport|fs_\w+)\b", re.I)
_PARLE_FICHIERS = re.compile(r"\b(fichiers?|dossiers?|r[ée]pertoires?|documents?|pdf|docx?|xlsx?|pptx?|csv|txt|workspace|uploads?|pi[èe]ces? jointes?|"
                             r"t[ée]l[ée]vers\w*|projets?|code|zip|fs_\w+)\b", re.I)
_DOMAINES = ("recette_", "wiki_", "carnet_", "rappel_", "list_", "note_", "papiers_", "calendar_", "agenda_", "finances_", "contenu_",
             "agent_", "routine_", "memoire_", "gmail_", "spotify_", "device_", "scene_", "tv_", "telephone_")
AVERTISSEMENT = " ACTION : n'utilise cet outil que si la personne le demande dans son dernier message, jamais de ta propre initiative."


def est_lecture(name: str) -> bool:
    return name in LECTURE

GROUPS: list[tuple[set[str], re.Pattern]] = [
    ({"ai_server_stats"}, re.compile(r"\b(serveur ia|serveur d.ia|gpu|vram|carte graphique|temp[ée]rature|consommation|watts?|[ée]lectricit[ée]|stat\w*|dashboard|ai_server_stats)\b", re.I)),
    ({"code_run"}, re.compile(r"\b(code|coder|python|script|calcul\w*|compt\w*|additionn\w*|multipli\w*|somme|moyenne|pourcentage|ex[ée]cut\w*|programme|algorithme|stat\w*|convert\w*|code_run)\b|\d\s*[*+/x×-]\s*\d", re.I)),
    ({"gmail_search", "gmail_read", "gmail_send"}, re.compile(r"\b(mails?|e-?mails?|courriel\w*|gmail|bo[iî]te de r[ée]ception|inbox|message[s]? non lus?)\b", re.I)),
    ({"agent_planifier", "agent_lister", "agent_gerer"}, re.compile(r"\b(agents?|t[âa]ches? automatiques?|chaque (?:matin|soir|jour|semaine|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|heure)|tous les (?:jours|matins|soirs|lundis|mardis|mercredis|jeudis|vendredis|samedis|dimanches)|toutes les (?:\d+ )?(?:heures|semaines)|automatiquement|surveille\w*|agent_\w+)\b", re.I)),
    ({"carnet_lister", "carnet_lire", "carnet_ecrire"}, re.compile(r"\b(carnets?|onenote|cahiers?|bloc[- ]notes|carnet_\w+)\b", re.I)),
    ({"rappel_creer", "rappel_lister", "rappel_annuler"}, re.compile(r"\b(rappel\w*|rappelle[- ]?moi|minuteurs?|chronos?|timer|alarmes?|r[ée]veil|pr[ée]viens[- ]moi|n.oublie pas de|dans \d+ ?(?:min|minutes?|h|heures?|secondes?)|rappel_\w+)\b", re.I)),
    ({"gmail_colis"}, re.compile(r"\b(colis|paquets?|livraisons?|livr[ée]\w*|exp[ée]di\w*|point relais|ma commande|mes commandes|gmail_colis)\b", re.I)),
    ({"pc_ecran_voir", "pc_ecran_cliquer", "pc_operateur"}, re.compile(r"\b(prends? (?:la main|le contr[ôo]le)|fais[- ]le (?:pour moi|toi)|à ma place|pilote mon (?:pc|ordi\w*)|mode op[ée]rateur|[ée]cran|affich[ée]\w* (?:sur|à) l.[ée]cran|ce que je vois|clique\w*|appuie sur le bouton|bouton|pc_ecran\w*)\b", re.I)),
    ({"calendar_list", "calendar_create", "calendar_modifier", "calendar_supprimer"}, re.compile(r"\b(agenda|calendrier|calendar|rendez-?vous|rdv|r[ée]union|[ée]v[ée]nement|planning|demain|semaine|d[ée]plac\w*|d[ée]cal\w*|annul\w*|report\w*)\b", re.I)),
    ({"ha_states", "ha_get", "ha_call"}, re.compile(r"\b(maison|lumi[èe]res?|lampes?|[ée]clairage|prises?|chauffage|thermostat|temp[ée]rature|volets?|salon|chambre|cuisine|home ?assistant|capteurs?|allume\w*|[ée]teins?|[ée]teindre|ha_\w+)\b", re.I)),
    ({"device_presence"}, re.compile(r"\b(qui est (?:l[àa]|[àa] la maison|rentr\w*)|est (?:l[àa]|rentr\w*|[àa] la maison)|pr[ée]sen\w*|absent\w*|parti\w*|device_presence)\b", re.I)),
    ({"telephone_sonner"}, re.compile(r"\b(o[uù] est mon (?:t[ée]l[ée]phone|portable|smartphone)|(?:fais|faire) sonner|retrouve\w* mon (?:t[ée]l[ée]phone|portable)|j.ai perdu mon (?:t[ée]l[ée]phone|portable)|telephone_\w+)", re.I)),
    ({"tv_diffuser"}, re.compile(r"\b(t[ée]l[ée]|tv|chromecast|google tv|youtube|vid[ée]o|radio|enceinte|nest|google home|caster|diffuse\w*|tv_\w+)\b", re.I)),
    ({"routine_creer", "routine_lister", "routine_gerer", "scene_run", "device_list"}, re.compile(r"\b(routines?|automatis\w*|tous les (?:soirs|matins|jours)|chaque (?:soir|matin|jour)|en semaine|le week-?end|quand (?:la|le|il) .{0,30}(?:temp[ée]rature|capteur|porte|mouvement|nuit|ouvr|d[ée]tect)|si la temp[ée]rature|d[ée]passe|capteurs?|routine_\w+)\b", re.I)),
    ({"device_list", "device_control", "scene_run", "device_hue_scene"}, re.compile(r"\b(hue|philips|allume\w*|[ée]teins?|[ée]teindre|lumi[èe]res?|lampes?|ampoules?|[ée]clairage|prises?|interrupteurs?|ventilat\w*|volets?|stores?|sc[èe]nes?|ambiance|th[ée]rmostat|chauffage|clim\w*|t[ée]l[ée]|r[ée]veille\w*|wake|luminosit\w*|intensit[ée]|couleur|salon|chambre|cuisine|bureau|salle de bain|garage|jardin|appareils?|maison|device_\w+|scene_\w+)\b", re.I)),
    ({"list_show", "list_add", "list_check", "list_remove"}, re.compile(r"\b(listes?|courses|ajoute\w*|[àa] acheter|acheter|achet[ée]\w*|t[âa]ches?|[àa] faire|todo|coche\w*|raye\w*|rature\w*|retire\w* de la|supprime\w* de la|list_\w+)\b", re.I)),
    ({"printer_list", "print_text", "print_file", "print_list"}, re.compile(r"\b(imprim\w*|impression|imprimante|papier|print\w*|photocop\w*)\b", re.I)),
    ({"video_generate"}, re.compile(r"\b(vid[ée]os?|clips?|animation|anime[rz]?|film court|video_generate)\b", re.I)),
    ({"image_generate", "image_edit"}, re.compile(r"\b(colori\w*|mandalas?|bande dessin[ée]e|images?|illustrations?|dessin\w*|dessine\w*|logo|affiche|visuel|peins|peindre|peinture|portrait|wallpaper|fond d.[ée]cran|g[ée]n[èe]re\w*|cr[ée]e\w* (une|un) (image|photo)|image_generate|image_edit|retouche\w*|recadre\w*|photos?)\b", re.I)),
    ({"net_hosts", "net_scan", "net_discover", "net_probe", "net_http", "net_ssh", "net_inspect"}, re.compile(r"\b(r[ée]seau|scan\w*|analyse\w* le r[ée]seau|appareils? connect[ée]s?|qui est connect[ée]|adresses? ip|ports?|ssh|root|inspect\w*|fouille\w*|d[ée]couv\w*|d[ée]tect\w*|appareils? du r[ée]seau|nmap|ping\w*|machines?|serveurs?|routeur|box|net_\w+)\b", re.I)),
    ({"docker_ps", "docker_logs", "docker_restart", "docker_stop", "docker_start"}, re.compile(r"\b(docker|conteneurs?|container|logs?|red[ée]marre\w*|service[s]?)\b", re.I)),
    ({"github_info", "git_status", "git_log", "git_diff", "git_commit"}, re.compile(r"\b(git|github|commit\w*|d[ée]p[ôo]t|repo|branche|diff)\b", re.I)),
    ({"fs_tree", "fs_grep", "fs_edit", "dev_check", "zip_make", "file_deliver", "terminal_run", "code_run", "git_status", "git_diff"},
     re.compile(r"\b(code|coder|modifi\w*|corrig\w*|r[ée]par\w*|refactor\w*|d[ée]bug\w*|bug|fonction|classe|script|zip|archive|projet|dossier|fichier\w*|repo|d[ée]p[ôo]t|application|appli|programme|test\w*|fs_\w+|dev_check|zip_make|file_deliver|shell|bash|\.sh|t[ée]l[ée]charg\w*|batch|powershell)\b", re.I)),
    ({"sandbox_run", "sandbox_install", "sandbox_db", "project_init", "fs_tree", "fs_edit", "dev_check"},
     re.compile(r"\b(bac [àa] sable|sandbox|pip|pytest|postgres\w*|sql|bdd|base de donn[ée]es?|base de test|tables?|python|projet\w*|test\w*|sandbox_\w+)\b", re.I)),
    ({"api_search", "api_get"}, re.compile(r"\b(apis?|api publiques?|jours? f[ée]ri[ée]s?|taux de change|recettes?|cocktails?|blagues?|wikip[ée]dia|station spatiale|lever du soleil|coucher du soleil|api_\w+)\b", re.I)),
    ({"fs_delete"}, re.compile(r"\b(supprim\w*|efface\w* (le|ce|les) fichier\w*|delete|fs_delete)\b", re.I)),
    ({"terminal_run"}, re.compile(r"\b(terminal|commande[s]?|shell|bash|ligne de commande|apt|pip|npm|ls|grep)\b", re.I)),
    ({"project_init", "project_log_decision", "project_log_change"}, re.compile(r"\b(projet[s]?|d[ée]cision|journal|changelog|readme|documente\w*)\b", re.I)),
    ({"role_run"}, re.compile(r"\b(agents?|r[ôo]les?|relecteur|relis|relire|relecture|revue de code|code review|reviewer|audit\w*|architecte|planifi\w*|planner|role_run)\b", re.I)),
    ({"skill_save", "skill_install"}, re.compile(r"\b(skills?|comp[ée]tence[s]?|installe\w*)\b", re.I)),
    ({"papiers_echeances", "papiers_a_verifier", "papiers_question", "papiers_marquer", "papiers_corriger", "papiers_deposer"},
     re.compile(r"\b([ée]ch[ée]ances?|pr[ée]avis|r[ée]sili\w*|renouvel\w*|reconduction|reconduit\w*|garanties?|assurances?|contrats?|abonnements?|"
                r"factures?|imp[ôo]ts?|taxes?|fonci[èe]re|tari|imu|scadenz\w*|disdett\w*|bollett\w*|expire\w*|expiration|passeport|carte grise|"
                r"contr[ôo]le technique|revisione|papiers?|paperasse|administratif\w*|majordome|paperless|[àa] payer|date limite|papiers_\w+)\b", re.I)),
    ({"code_agent", "project_init"},
     re.compile(r"\b(agent de code|aider|programm\w*|cod(?:e|er|es|ez)|d[ée]velopp\w*|bug\w*|refactor\w*|tests? unitaires?|code_agent)\b", re.I)),
    ({"recette_chercher", "recette_lire", "recette_courses", "recette_creer", "recette_modifier", "recette_partager", "print_list"},
     re.compile(r"\b(recettes?|cuisin\w*|pr[ée]par\w*|ingr[ée]dients?|plats?|desserts?|g[âa]teaux?|tartes?|cr[êe]pes?|soupes?|"
                r"g[ée]noise|quiche|lasagnes?|pizzas?|menu|repas|d[îi]ner|d[ée]jeuner|go[ûu]ter|liste de courses|recette_\w+)\b", re.I)),
    ({"wiki_chercher", "wiki_lire", "wiki_ecrire"},
     re.compile(r"\b(wiki|page\w*|proc[ée]dure\w*|mode d.emploi|notic\w*|comment (?:on|faire|marche|fonctionne)|o[uù] (?:est|sont|se trouve)|"
                r"code (?:wifi|du portail|alarme)|wifi|plombier|[ée]lectricien|artisans?|contacts?|num[ée]ro de|r[ée]glage\w*|wiki_\w+)\b", re.I)),
    ({"memoire_retenir", "memoire_lister", "memoire_oublier"},
     re.compile(r"\b(retiens|souviens|rappelle-toi|m[ée]moire|oublie|n'oublie pas|souvenirs?|remember|forget|memoire_\w+)\b", re.I)),
    ({"note_create", "note_list", "note_update", "note_delete"}, re.compile(r"\b(post-?its?|pense-?b[eê]tes?|note_\w+)\b", re.I)),
    ({"obs_etat", "obs_action"}, re.compile(r"\b(obs|stream\w*|live|en direct|enregistr\w*|replay|sc[èe]ne\w*|twitch|youtube|obs_\w+)\b", re.I)),
    ({"navigateur_ouvrir", "navigateur_lire", "navigateur_capture", "navigateur_cliquer", "navigateur_remplir"},
     re.compile(r"\b(navigateur|navigue\w*|site\w*|page web|clique\w*|formulaire\w*|rempli\w*|capture d.[ée]cran|screenshot|"
                r"va sur|ouvre (?:le site|la page)|r[ée]serv\w*|commande\w* en ligne|inscri\w*|https?://\S+|www\.\S+|navigateur_\w+)\b", re.I)),
    ({"document_creer", "document_modifier"},
     re.compile(r"\b(word|docx?|pdf|excel|xlsx?|tableur|powerpoint|pptx?|pr[ée]sentation|diaporama|diapos?|slides?|"
                r"document|fichier|rapport|compte.rendu|lettre|courrier|cv|devis|facture|tableau|budget|contrat|"
                r"modifie\w*|remplace\w*|corrige\w*|t[ée]l[ée]charg\w*|imprimable|document_\w+)\b", re.I)),
    ({"tache_de_fond", "plan_taches", "recherche_approfondie", "document_creer"},
     re.compile(r"\b(en fond|en t[âa]che de fond|en arri[èe]re.plan|pr[ée]viens.moi quand|quand (?:ce sera|c.est) fini|prends ton temps|"
                r"pendant que je|tranquillement|longue t[âa]che|tache_de_fond)\b", re.I)),
    ({"spotify_en_cours", "spotify_jouer", "spotify_commande"},
     re.compile(r"\b(spotify|musique|chanson|morceau|playlist|album|artiste|mets (?:du|de la|des|un peu)|joue\w*|[ée]coute\w*|"
                r"pause|suivant\w*|pr[ée]c[ée]dent\w*|volume|monte le son|baisse le son|c.est quoi (?:ce|cette) (?:son|titre)|spotify_\w+)\b", re.I)),
    ({"annonce"}, re.compile(r"\b(annonce\w*|dis (?:dans|[àa] (?:la|tout))|pr[ée]viens (?:tout le monde|les enfants|dans)|appelle (?:les enfants|tout le monde) (?:pour|[àa])|annonce)\b", re.I)),
    ({"pc_commande"}, re.compile(r"\b(pc|ordi\w*|ordinateur|bureau|portable|[ée]cran|lance (?:l.appli|le logiciel)|ouvre (?:l.appli|le logiciel|spotify|chrome|firefox|word|excel)|"
                                 r"verrouill\w*|[ée]teins? (?:le|l.)(?:pc|ordi\w*)|red[ée]marr\w*|volume|son|pc_commande)\b", re.I)),
    ({"chrome_pc"}, re.compile(r"\b(chrome|onglets?|mon navigateur|page (?:ouverte|affich[ée]e|actuelle)|r[ée]sume (?:cette|la) page|traduis (?:cette|la) page|chrome_pc)\b", re.I)),
    ({"agenda_ics"}, re.compile(r"\b(agenda\w*|calendrier|planning|rendez-vous|rdv|vacances|f[ée]ri[ée]\w*|semaine|week-end|demain|aujourd.hui|"
                                 r"ce soir|j.ai quoi|qu.est-ce que j.ai|programme|[ée]v[ée]nements?|r[ée]union\w*|match|entra[îi]nement|agenda_ics)\b", re.I)),
    ({"finances_resume", "finances_operations", "finances_noter", "finances_budget"},
     re.compile(r"\b(d[ée]pens\w*|budget\w*|finances?|argent|compte (?:courant|bancaire|joint)|solde|banque|[ée]conomi\w*|combien j.ai (?:pay|d[ée]pens)|"
                r"j.ai pay[ée]|en (?:liquide|esp[èe]ces)|\d+ ?euros?|"
                r"revenus?|salaire|pr[ée]l[èe]vements?|op[ée]rations? bancaires?|relev[ée]s?|finances_\w+)\b", re.I)),
    ({"contenu_idee", "contenu_lister", "contenu_avancer"},
     re.compile(r"\b(contenus?|vid[ée]os?|cha[îi]ne|youtube|tiktok|twitch|reels?|shorts?|publications?|post[eé]?s?|tournage|montage|script|"
                r"id[ée]e de (?:vid[ée]o|post|contenu|live)|programm[ée]\w*|publi[ée]\w*|contenu_\w+)\b", re.I)),
    ({"discord_envoyer"}, re.compile(r"\b(discord|serveur discord|salon|discord_\w+)\b", re.I)),
    ({"instagram_stats"}, re.compile(r"\b(instagram|insta|abonn[ée]\w*|followers?|likes?|j.aime|publications?|instagram_\w+)\b", re.I)),
    ({"appel_telephone"}, re.compile(r"\b(appel\w*|t[ée]l[ée]phon\w*|sms|texto|appelle|appel_telephone)\b", re.I)),
    ({"telegram_notify"}, re.compile(r"\b(telegram|pr[ée]viens-?moi|notifi\w*|alerte-?moi|envoie-?moi un message|telegram_\w+)\b", re.I)),
    ({"self_read", "self_propose"}, re.compile(r"\b(ton code|ton propre code|toi-m[êe]me|t'am[ée]liorer|am[ée]liore-toi|auto-?modif\w*|self_\w+|ta propre)\b", re.I)),
]


# Demandes vocales qui ont besoin d'outils (recherche web, fichiers, domotique, etc.).
VOICE_TOOLISH = re.compile(
    r"\b(cherche\w*|recherche\w*|internet|web|site|lien|url|fichier\w*|dossier\w*|document\w*|lis|lire|[ée]cris|[ée]crire|"
    r"sauvegarde\w*|enregistre\w*|cr[ée]e\w*|pr[ée]sente\w*|affiche\w*|montre\w*|diaporama|slides?|"
    r"m[ée]t[ée]o|actualit\w*|infos?|nouvelles|syst[èe]me|cpu|ram|disque|m[ée]moire vive|skills?|comp[ée]tences?)\b", re.I)


def text_needs_tools(text: str) -> bool:
    """La demande touche-t-elle un outil (maison, listes, fichiers, web, réseau…) ? Un tout petit modèle s'y trompe : on l'évite alors."""
    t = text or ""
    return bool(VOICE_TOOLISH.search(t) or any(p.search(t) for _n, p in GROUPS))


def voice_needs_tools(texts: list[str], all_names: list[str]) -> bool:
    """Un tour vocal court et conversationnel n'a pas besoin des schémas d'outils (~2000 tokens à lire)."""
    if VOICE_TOOLISH.search(texts[0] if texts else ""):
        return True
    names = select_tool_names(texts[:1], all_names)
    return bool(set(names) - CORE)


def group_match(text: str) -> set:
    """Outils d'action visés par la demande (maison, listes, fichiers…), hors outils de base."""
    out: set = set()
    for names, pattern in GROUPS:
        if pattern.search(text or ""):
            out |= names
    return out


def select_tool_names(texts: list[str], all_names: list[str]) -> list[str]:
    """Noms d'outils à proposer. `texts` : le message courant, puis les messages utilisateur précédents."""
    haystack = "\n".join(texts)
    actuel = texts[0] if texts else ""
    chosen = {n for n in CORE if est_lecture(n)}
    if _ECRITURE_FICHIER.search(actuel):
        chosen |= CORE
    for names, pattern in GROUPS:
        if pattern.search(actuel):
            chosen |= names                                   # demandé maintenant : toute la famille
        elif pattern.search(haystack):
            chosen |= {n for n in names if est_lecture(n)}    # évoqué plus tôt : seulement la consultation
    # Outils MCP : tous si peu nombreux, sinon seulement ceux du serveur nommé (ou si « mcp » est évoqué).
    mcp_names = [n for n in all_names if n.startswith("mcp_")]
    if mcp_names:
        low = haystack.lower()
        few = len(mcp_names) <= 6
        for n in mcp_names:
            server = n.split("_")[1]
            if few or server in low or "mcp" in low:
                chosen.add(n)
    # « Liste mes recettes », « montre mes rappels »… : la demande vise un domaine d'EVA, pas les fichiers. Sans mot de fichier,
    # les outils de fichiers ne sont pas proposés (sinon un petit modèle liste le dossier de travail au lieu des recettes).
    if not _PARLE_FICHIERS.search(actuel):
        domaine = {n for names, pattern in GROUPS if pattern.search(actuel) for n in names if n.startswith(_DOMAINES)}
        if domaine:
            chosen -= {n for n in chosen if n.startswith(("fs_", "zip_", "file_deliver", "project_"))}
    # Un outil cité par son nom dans la demande actuelle est toujours proposé.
    for n in all_names:
        if n in actuel:
            chosen.add(n)
    return [n for n in all_names if n in chosen]


class SubsetRegistry:
    """Même registre, mais n'annonce au modèle que les outils sélectionnés."""

    def __init__(self, base, names: list[str], interdits: set[str] | None = None):
        self._base = base
        self._names = names
        self._interdits = set(interdits or ())          # retirés pour ce tour : refusés même si le modèle les écrit

    def get(self, name):
        if name in self._interdits:
            return None
        if name not in self._names and not est_lecture(name):
            return None                                       # action non proposée pour ce tour : refusée (« outil inconnu »)
        return self._base.get(name)

    def names(self):
        return list(self._names)

    def schemas(self):
        out = []
        for n in self._names:
            t = self._base.get(n)
            if not t:
                continue
            sch = t.schema()
            if not est_lecture(n):
                sch = {**sch, "function": {**sch["function"], "description": sch["function"]["description"] + AVERTISSEMENT}}
            out.append(sch)
        return out
