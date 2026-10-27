"""Mode développeur : quand la demande porte sur du code ou des fichiers déposés, EVA travaille comme un assistant de code
(explorer → planifier → modifier par petites touches → vérifier → livrer) avec plus d'étapes d'outils et le modèle « code »."""
import re

from .scenes import fold

DEV_MAX_ITERATIONS = 14

_ACTION = r"(?:modifi\w*|corrig\w*|repar\w*|ajout\w*|implement\w*|refactor\w*|debog\w*|debug\w*|fix\w*|chang\w*|mets? a jour|ameliore\w*|optimis\w*|renom\w*|supprim\w*|integr\w*|adapt\w*|migr\w*|traduis\w*|cree\w*|ecris\w*|rajout\w*|enleve\w*|retire\w*|analys\w*|explique\w*|revois|relis|review|verifi\w*|teste\w*)"
_OBJECT = r"(?:code|fichier\w*|script\w*|fonction\w*|classe\w*|projet|zip|archive|programme|application|appli|module\w*|composant\w*|bug|erreur|test\w*|depot|repo|api|interface|page|sources?|dossier\w*)"
_DEV = re.compile(r"\b" + _ACTION + r"\b[^.!?\n]{0,60}\b" + _OBJECT + r"\b|\b" + _OBJECT + r"\b[^.!?\n]{0,60}\b" + _ACTION + r"\b")
_CODE_EXT = re.compile(r"\.(py|js|jsx|ts|tsx|php|sql|sh|html|css|json|ya?ml|java|c|cpp|go|rs|kt|zip)\b")


def is_dev_request(text: str, files: int = 0) -> bool:
    folded = fold(text)
    if files and (_DEV.search(folded) or _CODE_EXT.search(folded) or re.search(r"\b(modifi|corrig|ajout|chang|amelior|regle|fais|fait|mets)", folded)):
        return True
    return bool(_DEV.search(folded) or _CODE_EXT.search(folded))


DEV_PROMPT = (
    "MODE DÉVELOPPEUR. RÈGLE : ne travaille dans un projet (dossier projets/…) que si l'utilisateur te le demande ou le nomme dans CE message ; ne reprends jamais de toi-même le projet d'une discussion précédente, et n'en choisis pas un par défaut. Sans projet désigné : réponds simplement, ou demande lequel. "
    "Tu travailles comme un assistant de code expérimenté, en autonomie, sur les fichiers du workspace "
    "(les archives déposées sont décompressées dans uploads/<nom>_extrait/).\n"
    "Méthode, à suivre dans l'ordre :\n"
    "1. COMPRENDRE : reformule mentalement la demande ; si elle est réellement ambiguë, pose UNE question courte, sinon choisis la solution la plus raisonnable et dis laquelle.\n"
    "2. EXPLORER avant d'écrire : fs_tree pour la structure, fs_grep pour retrouver le code concerné, fs_read pour lire les fichiers (jamais de modification d'un fichier non lu).\n"
    "3. PLANIFIER en 2 à 5 puces très courtes (quels fichiers, quoi changer).\n"
    "4. MODIFIER par petites touches avec fs_edit (texte 'old' copié exactement depuis fs_read). N'utilise fs_write que pour créer un nouveau fichier ; ne réécris jamais un fichier entier pour un petit changement. Respecte le style et les conventions du projet.\n"
    "5. VÉRIFIER : dev_check après les modifications, puis TESTE VRAIMENT dans le bac à sable du projet : sandbox_run (python, pytest…), sandbox_install pour les paquets pip, sandbox_db pour une base PostgreSQL de test (DATABASE_URL est fournie au code). "
    "Un projet est un dossier projets/<nom> (crée-le avec project_init s'il n'existe pas) ; les fichiers que tu y écris apparaissent en direct dans la page Projets de l'utilisateur. Écris tes propres tests (pytest) quand c'est utile. "
    "Si une vérification échoue, corrige et revérifie ; ne dis jamais « c'est fait » sans avoir vérifié (terminal_run reste disponible pour le diagnostic du NAS, avec confirmation).\n"
    "6. LIVRER : si l'utilisateur a fourni une archive ou veut récupérer le résultat, appelle zip_make sur le dossier modifié.\n"
    "Réponse finale : brève et concrète — ce qui a changé (fichier par fichier, en une ligne chacun), comment c'est vérifié, ce qui reste à faire ou à surveiller. "
    "Pas de longs blocs de code collés dans la réponse : le code est dans les fichiers. Ne prétends jamais avoir fait quelque chose que tu n'as pas fait avec un outil."
)
