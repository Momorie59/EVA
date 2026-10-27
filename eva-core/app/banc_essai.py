"""Banc d'essai des outils : des phrases types sont envoyées au VRAI modèle avec les outils qu'EVA lui proposerait,
et on regarde quel outil il choisit — sans rien exécuter. Montre, pour chaque modèle, ce qu'il comprend bien ou mal :
  - « pas proposé » : la sélection d'outils d'EVA (selection.py) n'a pas mis le bon outil dans la liste → à corriger côté EVA ;
  - « mauvais outil » / « aucun outil » : le modèle s'est trompé → essayer un autre modèle.
Les résultats sont gardés (kv « banc_essai ») pour comparer les modèles."""
import asyncio
import json
import time

from .db import get_pool

KV = "banc_essai"
AUCUN = "(aucun)"

# phrase → outils acceptés (le premier appel du modèle doit être l'un d'eux)
CAS: list[tuple[str, set[str]]] = [
    ("Quel temps fait-il demain à Lille ?", {"weather_get"}),
    ("Allume la lumière du salon", {"device_control", "ha_call", "device_list"}),
    ("Lance la scène film", {"scene_run"}),
    ("Qui est à la maison ?", {"device_presence"}),
    ("Ajoute du lait et des œufs à la liste de courses", {"list_add"}),
    ("Qu'est-ce qu'il reste sur la liste de courses ?", {"list_show"}),
    ("Rappelle-moi de sortir le gâteau dans 10 minutes", {"rappel_creer"}),
    ("Quels rappels j'ai en cours ?", {"rappel_lister"}),
    ("Chaque matin à 7h30, donne-moi la météo et mes rendez-vous", {"agent_planifier"}),
    ("Qu'est-ce que j'ai dans mon agenda demain ?", {"calendar_list", "agenda_ics"}),
    ("Ajoute un rendez-vous chez le dentiste jeudi à 15h", {"calendar_create"}),
    ("Déplace le rendez-vous du dentiste à vendredi 10h", {"calendar_list", "calendar_modifier"}),
    ("Ai-je reçu des mails importants aujourd'hui ?", {"gmail_search", "gmail_read"}),
    ("Où en sont mes colis ?", {"gmail_colis"}),
    ("Quand se termine mon contrat d'assurance habitation ?", {"papiers_question", "papiers_echeances"}),
    ("Quelles échéances de papiers ce mois-ci ?", {"papiers_echeances"}),
    ("Crée une recette de paella pour 4 personnes avec une photo", {"recette_creer"}),
    ("Liste moi mes recettes", {"recette_chercher"}),
    ("Crée-moi un coloriage de banane", {"image_generate"}),
    ("Dans la recette de paella, remplace les moules par des crevettes", {"recette_modifier", "recette_chercher", "recette_lire"}),
    ("Fais-moi la liste de courses pour la recette des crêpes", {"recette_courses", "recette_chercher"}),
    ("Note dans le carnet Vacances, section Bretagne : crème solaire", {"carnet_ecrire"}),
    ("Crée une page wiki sur l'entretien de la piscine", {"wiki_ecrire"}),
    ("Note une dépense de 12,50 euros au marché", {"finances_noter"}),
    ("Combien j'ai dépensé ce mois-ci ?", {"finances_resume", "finances_operations"}),
    ("Mets du Daft Punk", {"spotify_jouer", "spotify_commande"}),
    ("C'est quoi la musique qui passe ?", {"spotify_en_cours", "pc_commande"}),
    ("Annonce dans la cuisine que le dîner est prêt", {"annonce"}),
    ("Ouvre Spotify sur le PC", {"pc_commande"}),
    ("Qu'est-ce qu'il y a sur mon écran ?", {"pc_ecran_voir"}),
    ("Prends la main sur mon PC et ouvre le bloc-notes pour écrire la liste de courses", {"pc_operateur"}),
    ("Dessine un chalet sous la neige", {"image_generate"}),
    ("Cherche sur internet les horaires de la déchetterie de Roubaix", {"web_search", "web_fetch"}),
    ("Fais un comparatif détaillé des pompes à chaleur air-eau avec les sources", {"recherche_approfondie", "web_search", "plan_taches"}),
    ("Fais-moi un document Word avec le compte rendu de la réunion", {"document_creer", "poser_question"}),
    ("Montre-moi les fichiers du projet EVA", {"fs_list", "fs_tree"}),
    ("Quels conteneurs Docker tournent ?", {"docker_ps"}),
    ("Comment va le serveur ? CPU, mémoire, disque", {"system_stats", "ai_server_stats"}),
    ("Quelles machines sont sur le réseau ?", {"net_hosts", "net_discover", "net_scan"}),
    ("Imprime la liste de courses", {"print_list", "print_text"}),
    ("Souviens-toi que ma fille fait de la danse le mercredi", {"memoire_retenir"}),
    ("Envoie-moi un message Telegram quand c'est fini", {"telegram_notify"}),
    ("Réserve-moi une table au restaurant samedi soir", {"evolution_demander", "web_search", "appel_telephone", "poser_question"}),
    ("Bonjour EVA, comment ça va ?", {AUCUN}),
    ("Raconte-moi une blague", {AUCUN}),
    ("Explique-moi la photosynthèse simplement", {AUCUN}),
]

_etat: dict = {"en_cours": False}


def _noms_appels(rep: dict) -> list[str]:
    msg = rep.get("message") or rep
    out = []
    for tc in msg.get("tool_calls") or []:
        f = tc.get("function") or tc
        if f.get("name"):
            out.append(str(f["name"]))
    return out


async def essayer(phrase: str, attendus: set[str], modele: str, registry) -> dict:
    from . import modules, ollama_client
    from .config import settings
    from .harness.selection import SubsetRegistry, select_tool_names
    tous = registry.names()
    noms = [n for n in select_tool_names([phrase], tous) if not modules.outil_coupe(n)]
    propose = AUCUN in attendus or bool(set(noms) & attendus)
    sub = SubsetRegistry(registry, noms)
    messages = [{"role": "system", "content": settings.system_prompt + f"\nFuseau horaire : {settings.timezone}."},
                {"role": "user", "content": phrase}]
    t0 = time.monotonic()
    try:
        rep = await asyncio.wait_for(ollama_client.chat_once(messages, tools=sub.schemas() or None, model=modele), 240)
        appels = _noms_appels(rep)
        erreur = ""
    except Exception as exc:  # noqa: BLE001
        appels, erreur = [], str(exc)[:200]
    choisi = appels[0] if appels else AUCUN
    if erreur:
        verdict = "erreur"
    elif choisi in attendus:
        verdict = "ok"
    elif not propose:
        verdict = "pas_propose"
    elif choisi == AUCUN:
        verdict = "aucun_outil"
    else:
        verdict = "mauvais_outil"
    return {"phrase": phrase, "attendus": sorted(attendus), "choisi": choisi, "autres": appels[1:4], "verdict": verdict,
            "proposes": len(noms), "duree_s": round(time.monotonic() - t0, 1), **({"erreur": erreur} if erreur else {})}


async def _sauver(resultat: dict) -> None:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
        d = (json.loads(raw) if isinstance(raw, str) else raw) or {} if raw else {}
        d.setdefault("passages", {})[resultat["modele"]] = resultat
        await conn.execute("INSERT INTO kv (key, value) VALUES ($1,$2::jsonb) ON CONFLICT (key) DO UPDATE SET value=$2::jsonb", KV, json.dumps(d))


async def lancer(modele: str, registry, filtre: str = "") -> dict:
    """Passe tous les cas (ou ceux qui contiennent `filtre`) ; résultat gardé par modèle."""
    if _etat.get("en_cours"):
        raise RuntimeError("Un banc d'essai tourne déjà.")
    cas = [(p, a) for p, a in CAS if not filtre or filtre.lower() in p.lower()]
    _etat.update(en_cours=True, modele=modele, fait=0, total=len(cas), debut=time.time())
    lignes = []
    try:
        for phrase, attendus in cas:
            lignes.append(await essayer(phrase, attendus, modele, registry))
            _etat["fait"] = len(lignes)
        bons = sum(1 for x in lignes if x["verdict"] == "ok")
        res = {"modele": modele, "date": int(time.time()), "score": bons, "total": len(lignes), "lignes": lignes,
               "duree_moyenne_s": round(sum(x["duree_s"] for x in lignes) / max(1, len(lignes)), 1),
               "pas_proposes": sum(1 for x in lignes if x["verdict"] == "pas_propose")}
        await _sauver(res)
        return res
    finally:
        _etat["en_cours"] = False


async def resultats() -> dict:
    async with get_pool().acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM kv WHERE key=$1", KV)
    d = ((json.loads(raw) if isinstance(raw, str) else raw) or {}) if raw else {}
    return {"passages": sorted((d.get("passages") or {}).values(), key=lambda p: -p.get("date", 0)), "etat": dict(_etat), "cas": len(CAS)}
