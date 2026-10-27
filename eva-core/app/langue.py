"""Comprendre la personne comme le ferait un humain : langage SMS, fautes courantes, messages courts qui renvoient à ce qui précède.

Deux aides, toutes deux prudentes (jamais bloquantes) :
- `normaliser` : développe les abréviations sans ambiguïté (« pkoi », « jai », « ya », « svp »…) avant que EVA ne décide quoi faire ;
- `eclaircir` : pour un message court qui dépend de la conversation (« oui », « fais-le », « et celui-là ? », « continue »), le petit modèle
  rapide le réécrit en phrase complète à partir des derniers échanges ; ce texte est donné au modèle principal comme aide, jamais à la place du message."""
import asyncio
import logging
import re

logger = logging.getLogger("eva-core")

_ABREV = {
    r"pkoi|pourqoi|pourquio": "pourquoi", r"jai": "j'ai", r"jsuis|jsui|chuis|chui": "je suis", r"jveux|jvx": "je veux", r"jpeux|jpx": "je peux",
    r"jsais|jsai|jsé": "je sais", r"jcrois|jcrois": "je crois", r"ya|y'a": "il y a", r"yavait|y'avait": "il y avait",
    r"tt": "tout", r"tte": "toute", r"ttes": "toutes", r"tjrs|tjs|toujour": "toujours", r"jms|jamai": "jamais", r"bcp|beaucou": "beaucoup",
    r"qd|quand?d": "quand", r"cmt|comen|coment|commen": "comment", r"mtn|mnt|maintnt|maintenent": "maintenant",
    r"svp|stp|siouplait|sil vous plait|sil te plait": "s'il te plaît", r"pr": "pour", r"ds": "dans", r"avc|ac": "avec", r"sr": "sur",
    r"pb|pbm": "problème", r"pbs|pbms": "problèmes", r"prob": "problème", r"probleme|problme|probleme?s?": "problème", r"problemes|problmes": "problèmes",
    r"qqch|qqc": "quelque chose", r"qqn": "quelqu'un", r"tkt|tqt": "ne t'inquiète pas", r"dsl": "désolé", r"msg": "message",
    r"vrmt|vraiement|vraimen": "vraiment", r"aussis": "aussi", r"auci|ausi|osi": "aussi",
    r"possibke|possibe|possble|possibl": "possible", r"supprimmer|suprimer|suprime": "supprimer", r"installr|instaler": "installer",
    r"verifie|vérifi": "vérifie", r"ptit|p'tit": "petit", r"auj|ajd|aujourdhui": "aujourd'hui",
    r"demande moi": "demande-moi", r"dis moi": "dis-moi", r"donne moi": "donne-moi", r"montre moi": "montre-moi", r"rappelle moi": "rappelle-moi",
}
# Seuls les mots entiers sont remplacés ; « tous/tt » reste en l'état quand c'est « tous » : on ne touche pas aux mots corrects.
_RX = re.compile(r"(?<![\w'’-])(" + "|".join(sorted((k for k in _ABREV), key=len, reverse=True)) + r")(?![\w'’-])", re.I)
_RECETTE = {}
for _k, _v in _ABREV.items():
    for _alt in _k.split("|"):
        _RECETTE[_alt.lower()] = _v


def normaliser(texte: str) -> str:
    """Abréviations et fautes de frappe fréquentes → mots corrects. Le texte avec code, lien ou chemin n'est pas touché."""
    t = texte or ""
    if len(t) > 600 or "`" in t or "://" in t or re.search(r"[/\\]\w+\.\w{1,5}\b", t):
        return t

    def sub(m):
        mot = m.group(1)
        rep = _RECETTE.get(mot.lower())
        if rep is None:
            return mot
        if mot[:1].isupper() and rep:
            rep = rep[:1].upper() + rep[1:]
        return rep
    out = _RX.sub(sub, t)
    return re.sub(r"\s{2,}", " ", out).strip() or t


# ------------------------------------------------------------------ messages qui dépendent de ce qui précède
_ELLIPSE = re.compile(
    r"^\W*(oui|ouais|non|ok|d'accord|vas-y|go|fais[- ]le|fais ça|fais cela|continue|poursuis|et (?:ça|cela|celui|celle|ceux|alors|après|pour)|celui[- ](?:là|ci)|celle[- ](?:là|ci)|"
    r"le même|la même|pareil|aussi|encore|pourquoi|comment|c'est quoi|quoi|lequel|laquelle|combien|et si|plus de détails|détaille|développe|explique|"
    r"refais|recommence|corrige[- ](?:le|la|ça)|essaie encore|réessaie|annule|lance[- ](?:le|la|ça)|envoie[- ](?:le|la|ça)|fais[- ](?:la|les)|ajoute[- ](?:le|la|ça|aussi))\b", re.I)
_PRONOM = re.compile(r"\b(le|la|les|ça|cela|celui|celle|ceux|y|en|là|dessus|dedans|ce dernier|la dernière|le dernier|précédent\w*|tout à l'heure|tout ça)\b", re.I)


def depend_du_contexte(texte: str) -> bool:
    t = (texte or "").strip()
    mots = t.split()
    if not mots or len(mots) > 12 or len(t) > 100:
        return False
    return bool(_ELLIPSE.search(t) or (len(mots) <= 6 and _PRONOM.search(t)))


CONSIGNE = ("Tu aides à comprendre un message court dans une conversation. Réécris le DERNIER message de la personne en une phrase complète, "
            "claire et autonome, en remplaçant les pronoms et sous-entendus (« oui », « fais-le », « celui-là ») par ce à quoi ils renvoient d'après les "
            "échanges précédents. N'ajoute aucune information nouvelle. Garde la langue de la personne. Si le message est déjà clair, recopie-le tel quel. "
            "Réponds uniquement par la phrase réécrite.")


def _court(t: str, n: int = 260) -> str:
    t = " ".join((t or "").split())
    return t[:n] + ("…" if len(t) > n else "")


async def eclaircir(texte: str, historique: list[dict], modele: str | None = None, delai: float = 8.0) -> str:
    """La phrase complète que la personne veut dire, ou « » si inutile / impossible. Ne lève jamais d'exception."""
    try:
        recents = [m for m in historique if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()][-5:]
        if len(recents) < 2 or not depend_du_contexte(texte):
            return ""
        from .ollama_client import chat_once
        from . import fil
        echanges = "\n".join(f"{'Personne' if m['role'] == 'user' else 'EVA'} : {_court(m['content'])}" for m in recents)
        msg = await asyncio.wait_for(chat_once([
            {"role": "system", "content": CONSIGNE},
            {"role": "user", "content": f"Échanges précédents :\n{echanges}\n\nDernier message de la personne : {texte}"},
        ], model=modele or await fil._modele()), delai)
        out = re.sub(r"<think>.*?</think>", "", (msg.get("content") or ""), flags=re.S).strip().strip("«»\"' ")
        if not out or len(out) > 300 or out.lower() == (texte or "").strip().lower():
            return ""
        return out
    except Exception:  # noqa: BLE001 — jamais bloquant
        logger.info("Éclaircissement du message : ignoré", exc_info=True)
        return ""


def note(phrase: str) -> str:
    return (f"\n\n[Aide à la compréhension : dans le contexte de la conversation, la personne veut probablement dire : « {phrase} ». "
            "Sers-t'en seulement si c'est cohérent avec les échanges précédents ; en cas de doute réel, pose une question courte.]") if phrase else ""
