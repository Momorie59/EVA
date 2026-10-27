"""Suivi de colis à partir des mails d'expédition et de livraison (comme tools/colis.py de Jarvis), en lecture seule.

EVA lit seulement l'expéditeur, l'objet et la date des mails récents de Gmail (déjà relié dans Paramètres), sans service
de transporteur ni cloud. Pour chaque colis (un marchand + un numéro de commande ou de suivi s'il y en a un), l'étape la
plus avancée est retenue : en route, en point relais, en livraison aujourd'hui, livré (gardé un jour et demi)."""
import datetime as dt
import re
import unicodedata
from email.utils import parseaddr, parsedate_to_datetime

JOURS = 10
REQUETE = ("newer_than:{j}d (colis OR commande OR livraison OR livré OR livrée OR expédié OR expédiée OR \"point relais\" OR "
           "shipped OR delivered OR \"out for delivery\" OR order OR package OR parcel)")

_ETAPES = (
    ("expedie", "est en route", re.compile(r"expedie|expedition|en route|en chemin|en transit|pris en charge|a ete envoye"
                                           r"|shipped|on its way|dispatched")),
    ("relais", "t'attend en point relais", re.compile(r"point relais|point retrait|disponible (en|au|dans)|a retirer|pret a etre retire"
                                                     r"|ready for pickup|consigne|locker")),
    ("livraison", "arrive aujourd'hui", re.compile(r"en cours de livraison|livree?s? aujourd'hui|livraison (prevue )?aujourd'hui"
                                                  r"|arrive aujourd'hui|out for delivery|en tournee|arriving today")),
    ("livre", "a été livré", re.compile(r"(a ete|ont ete|est|sont|bien|vient d'etre|colis) livres?\b|\blivrees?\b|^livres?\b"
                                        r"|\bdelivered\b|a ete distribue|a ete remis")),
)
NOMS = {"expedie": "En route", "relais": "En point relais", "livraison": "Livraison aujourd'hui", "livre": "Livré"}
_RANG = {cle: rang for rang, (cle, _, _) in enumerate(_ETAPES)}
_FUTUR = re.compile(r"sera livre|livre demain|livraison prevue|estimated|prevue le|prevue pour")
_INDICE = re.compile(r"colis|commande|livraison|paquet|envoi|order|package|shipment|parcel|suivi|tracking")
_PUB = re.compile(r"livraison (offerte|gratuite)|free (shipping|delivery)|frais de port|promo|soldes|reduction|-\s?\d+\s?%|code promo"
                  r"|newsletter|black friday|donnez votre avis|laissez un avis|evaluez|notez|satisfaction|enquete|comment s'est passe")
_IDENT = re.compile(r"\b\d{3}-\d{7}-\d{7}\b|\b[A-Z]{2}\d{9}[A-Z]{2}\b|\b1Z[0-9A-Z]{16}\b"
                    r"|(?:commande|order|colis|n°|no\.?)\s*[:#°]?\s*#?((?=[A-Z-]*\d)[A-Z0-9][A-Z0-9-]{4,})", re.I)
_GENERIQUE = re.compile(r"no-?reply|ne-?pas-?repondre|notification|info|service", re.I)
DEMANDE = re.compile(r"\b(colis|paquets?)\b|\b(mes|ma) livraisons?\b|\b(mes|ma) commandes?\b.*\b(arriv\w*|livr\w*|en route|exp[ée]di\w*|suivi|o[uù] en)\b"
                     r"|\b(suivi|suivre|o[uù] en (est|sont)|quand arriv\w*)\b.*\b(mes|ma) commandes?\b", re.I)


def _plat(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower().replace("’", "'")) if unicodedata.category(c) != "Mn")


def marchand(expediteur: str) -> str:
    nom, adresse = parseaddr(expediteur or "")
    nom = re.sub(r"\s*\(.*?\)|[\"']", "", nom).strip()
    if nom and not _GENERIQUE.fullmatch(nom):
        return nom[:40]
    dom = (adresse.split("@")[-1] if "@" in adresse else "").split(".")
    principal = dom[-2] if len(dom) >= 2 else (dom[0] if dom else "")
    return principal.capitalize() or "Un marchand"


def etape(sujet: str) -> str | None:
    p = _plat(sujet)
    if _PUB.search(p) or not _INDICE.search(p):
        return None
    for cle, _l, motif in reversed(_ETAPES):
        if cle == "livre" and _FUTUR.search(p):
            continue
        if motif.search(p):
            return cle
    return None


def _date(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.astimezone()
    try:
        d = parsedate_to_datetime(v)
        return d if d.tzinfo else d.astimezone()
    except (TypeError, ValueError):
        return None


def analyser(entetes: list[dict], maintenant: dt.datetime | None = None) -> list[dict]:
    """Colis en cours à partir d'en-têtes {de, objet, date}. Fonction pure."""
    maintenant = maintenant or dt.datetime.now().astimezone()
    colis: dict[tuple, dict] = {}
    for e in entetes:
        et, date = etape(e.get("objet", "")), _date(e.get("date"))
        if et is None or date is None:
            continue
        ident = _IDENT.search(e.get("objet") or "")
        cle = (marchand(e.get("de", "")), (ident.group(1) or ident.group(0)).upper() if ident else "")
        actuel = colis.get(cle)
        if actuel is None or (date, _RANG[et]) > (actuel["_date"], _RANG[actuel["etape"]]):
            colis[cle] = {"marchand": cle[0], "numero": cle[1], "etape": et, "_date": date, "objet": (e.get("objet") or "")[:140]}
    for (m, ident), suivi in list(colis.items()):           # « livré » sans numéro après « expédié, commande 123 » : même colis
        if ident:
            continue
        numerotes = [c for c in colis if c[0] == m and c[1]]
        if len(numerotes) == 1:
            ancien = colis[numerotes[0]]
            if (suivi["_date"], _RANG[suivi["etape"]]) >= (ancien["_date"], _RANG[ancien["etape"]]):
                del colis[numerotes[0]]
            else:
                del colis[(m, ident)]
    garde = [c for c in colis.values() if not (c["etape"] == "livre" and maintenant - c["_date"] > dt.timedelta(hours=36))]
    garde.sort(key=lambda c: (-_RANG[c["etape"]], c["marchand"].lower()))
    for c in garde:
        d = c.pop("_date")
        c["date"], c["statut"] = d.isoformat(), NOMS[c["etape"]]
        c["phrase"] = f"{c['marchand']} {dict((k, t) for k, t, _m in _ETAPES)[c['etape']]}"
    return garde


async def en_cours(jours: int = JOURS) -> dict:
    from . import google
    jours = max(1, min(int(jours or JOURS), 30))
    r = await google.gmail_search(REQUETE.format(j=jours), 20)
    colis = analyser(r.get("messages", []))
    if not colis:
        return {"colis": [], "resume": f"Aucun colis en cours d'après tes mails des {jours} derniers jours."}
    return {"colis": colis, "resume": " ; ".join(c["phrase"] for c in colis) + "."}
