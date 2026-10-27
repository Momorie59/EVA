"""Réponses instantanées : des demandes simples et sans ambiguïté traitées sans le modèle (réponse en une fraction de seconde).

- l'heure et la date (« quelle heure est-il ? ») ;
- ajouter à une liste (« ajoute du lait et des œufs à la liste de courses ») ;
- lire une liste (« qu'est-ce qu'il y a sur la liste de courses ? »).
Dès qu'une phrase sort de ces formes simples, c'est le modèle qui répond, comme avant."""
import re

from . import lists, scenes

_LISTE = r"(?:la|ma|notre)\s+liste(?:\s+(?:des\s+|du\s+|de\s+la\s+|de\s+l'|de\s+|d')(?P<liste>[\w'À-ÿ -]{2,30}?))?"
_AJOUT = re.compile(r"^\s*(?:eva[\s,]+)?(?:ajoute|rajoute|mets|met|inscris|note)\s+(?P<items>.{2,160}?)\s+(?:à|a|sur|dans)\s+" + _LISTE + r"\s*[.!]*\s*$", re.I)
_VOIR = re.compile(r"^\s*(?:eva[\s,]+)?(?:qu'est[- ]ce qu'il y a|qu'y a[- ]t[- ]il|qu'est[- ]ce qui reste|que reste[- ]t[- ]il|"
                   r"montre[- ]moi|lis[- ]moi|affiche|c'est quoi|donne[- ]moi)\s+(?:sur|dans)?\s*" + _LISTE + r"\s*\??\s*$", re.I)
_PRESENCE = re.compile(r"^\s*(?:eva[\s,]+)?(?:qui est (?:l[àa]|[àa] la maison|chez nous|rentr[ée]e?s?)|il y a qui (?:[àa] la maison|ici)|"
                       r"qui est pr[ée]sent)\s*\??\s*$", re.I)
_PAS_UNE_LISTE = re.compile(r"post[- ]?it|papiers?|m[ée]moire|projet|fichier|agenda|calendrier", re.I)


def _nom_liste(brut: str | None) -> str:
    return (brut or "courses").strip(" '") or "courses"


def _elements(brut: str) -> list[str]:
    morceaux = re.split(r"\s*,\s*|\s+et\s+|\s+puis\s+", brut.strip())
    return [m.strip(" .") for m in morceaux if m.strip(" .")][:lists.MAX_ITEMS_PER_CALL]


def detect(texte: str) -> dict | None:
    t = (texte or "").strip()
    if not t or len(t) > 220:
        return None
    m = _AJOUT.match(t)
    if m and not _PAS_UNE_LISTE.search(m.group("items")):
        items = _elements(m.group("items"))
        if items:
            return {"kind": "liste_ajout", "liste": _nom_liste(m.group("liste")), "items": items}
    m = _VOIR.match(t)
    if m:
        return {"kind": "liste_voir", "liste": _nom_liste(m.group("liste"))}
    if _PRESENCE.match(t):
        return {"kind": "presence"}
    if len(t.split()) <= 8 and scenes.wants_time(t) and not scenes.wants_news(t):
        return {"kind": "heure"}
    return None


def _joindre(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " et " + xs[-1]


async def repondre(cmd: dict, fuseau: str, qui: str = "") -> tuple[str, str, dict | None]:
    """(réponse, outil affiché, scène à afficher ou None)."""
    if cmd["kind"] == "presence":
        from . import presence
        return presence.phrase(await presence.etat()), "device_presence", None
    if cmd["kind"] == "heure":
        sc = scenes.clock_scene(fuseau)
        return f"Il est {sc['time']}, nous sommes le {sc['date']}.", "horloge", sc
    if cmd["kind"] == "liste_ajout":
        lst = await lists.find(cmd["liste"], create=True)
        r = await lists.add(lst["id"], cmd["items"], by=qui or "eva")
        ajoutes = r.get("added") or []
        deja = r.get("already_there") or []
        morceaux = []
        if ajoutes:
            morceaux.append(f"J'ai ajouté {_joindre(ajoutes)} à la liste « {lst['name']} ».")
        if deja:
            morceaux.append(f"Déjà sur la liste : {_joindre(deja)}.")
        return " ".join(morceaux) or f"C'est noté sur la liste « {lst['name']} ».", "list_add", None
    if cmd["kind"] == "liste_voir":
        lst = await lists.find(cmd["liste"])
        if lst is None:
            return f"Je n'ai pas de liste « {cmd['liste']} ».", "list_show", None
        restants = [i["text"] for i in await lists.items(lst["id"], include_done=False)]
        if not restants:
            return f"La liste « {lst['name']} » est vide.", "list_show", None
        return f"Sur la liste « {lst['name']} » ({len(restants)}) :\n" + "\n".join(f"- {x}" for x in restants), "list_show", None
    return "", "", None
