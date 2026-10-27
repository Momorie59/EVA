"""Diffuser sur la TV et les enceintes Google (Chromecast, Google TV, Nest) : « mets la dernière vidéo de Cyprien sur la TV
du salon », « lance France Inter sur l'enceinte de la cuisine », « mets en pause la TV », « monte le son de la TV »."""
import re
from typing import Any

from ... import cast, devices
from ..permissions import Permission
from .base import Tool

ACTIONS = ["youtube", "lien", "pause", "lecture", "arreter", "suivant", "precedent", "muet", "avancer", "volume", "etat"]


async def _chercher_youtube(q: str) -> tuple[str, str] | None:
    from .web import WebSearchTool
    r = await WebSearchTool().execute(query=f"{q} site:youtube.com", max_results=8)
    for x in r.get("results") or []:
        vid = cast.id_youtube(x.get("url", ""))
        if vid:
            return vid, x.get("title", "")
    return None


class TvDiffuserTool(Tool):
    name = "tv_diffuser"
    description = ("Pilote une TV ou une enceinte Google (Chromecast, Google TV, Nest) ajoutée dans Maison : action=youtube "
                   "(valeur = lien, identifiant ou recherche, ex. « dernière vidéo de Cyprien »), lien (valeur = adresse directe d'une "
                   "radio, d'un mp3, d'une vidéo ou d'une image), pause, lecture, arreter, suivant, precedent, muet, avancer (secondes), "
                   "volume (0-100), etat. appareil = nom ou pièce (« TV du salon », « cuisine »).")
    parameters = {"type": "object", "properties": {
        "appareil": {"type": "string"}, "action": {"type": "string", "enum": ACTIONS}, "valeur": {"type": "string"}},
        "required": ["action"]}
    permission = Permission.AUTO

    async def execute(self, appareil: str = "", action: str = "", valeur: str = "", **_: Any) -> dict:
        await devices.reload()
        casts = [d for d in devices._cache if d["driver"] == "cast"]
        if not casts:
            return {"error": "Aucune TV ni enceinte Google dans Maison › Appareils (lance la détection réseau, elles s'y ajoutent)."}
        q = str(appareil or "").strip().lower()
        cibles = [d for d in casts if not q or q in d["name"].lower() or q in (d.get("room") or "").lower()] if q else casts
        if q and not cibles:
            return {"error": f"« {appareil} » introuvable.", "appareils": [d["name"] for d in casts]}
        if len(cibles) > 1:
            tv = [d for d in cibles if re.search(r"tv|t[ée]l[ée]|chromecast|shield|bravia", d["name"], re.I)]
            cibles = tv[:1] if action in ("youtube", "lien") and len(tv) >= 1 else cibles
        if len(cibles) > 1 and action not in ("pause", "arreter", "muet", "etat"):
            return {"error": "Plusieurs appareils : précise lequel.", "appareils": [d["name"] for d in cibles]}
        valeur = str(valeur or "").strip()
        titre = ""
        try:
            out = []
            for d in cibles:
                if action == "youtube":
                    vid = cast.id_youtube(valeur)
                    if not vid:
                        trouve = await _chercher_youtube(valeur)
                        if not trouve:
                            return {"error": f"Je n'ai pas trouvé de vidéo YouTube pour « {valeur} »."}
                        vid, titre = trouve
                    r = await cast.diffuser(d["config"], "youtube", vid)
                elif action == "lien":
                    if not re.match(r"https?://", valeur):
                        return {"error": "Donne une adresse directe (http…) : radio, mp3, vidéo ou image."}
                    r = await cast.diffuser(d["config"], "media", url=valeur)
                elif action == "volume":
                    r = await cast.diffuser(d["config"], "brightness", str(max(0, min(100, int(re.sub(r"\D", "", valeur) or 30)))))
                else:
                    r = await cast.diffuser(d["config"], {"pause": "pause", "lecture": "on", "arreter": "off", "suivant": "suivant",
                                                          "precedent": "precedent", "muet": "muet", "avancer": "avancer", "etat": "state"}[action],
                                            valeur or "30")
                out.append({"appareil": d["name"], **r})
        except (cast.CastError, ValueError, KeyError) as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — TV éteinte, application refusée…
            return {"error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"ok": True, **({"video": titre} if titre else {}), "resultats": out}


def all_tools() -> list[Tool]:
    return [TvDiffuserTool()]
