"""« C'est quoi cette musique ? » : empreinte sonore (fpcalc / Chromaprint) comparée à la base libre AcoustID + MusicBrainz.

L'extrait (10 à 30 s, enregistré par l'interface ou un satellite) n'est jamais conservé ; seule l'empreinte part sur
Internet. Il faut une clé d'application AcoustID gratuite (Paramètres › Services connectés)."""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from . import connecteurs as cx

API = "https://api.acoustid.org/v2/lookup"
FORMATS = {".wav", ".webm", ".ogg", ".mp3", ".m4a", ".mp4", ".flac", ".opus", ".aac"}


class MusiqueError(RuntimeError):
    pass


async def empreinte(donnees: bytes, ext: str) -> tuple[int, str]:
    if not shutil.which("fpcalc"):
        raise MusiqueError("fpcalc (Chromaprint) n'est pas installé : reconstruis eva-core.")
    ext = ext.lower() if ext.lower() in FORMATS else ".webm"
    with tempfile.NamedTemporaryFile(suffix=ext) as f:
        f.write(donnees)
        f.flush()
        proc = await asyncio.create_subprocess_exec("fpcalc", "-json", "-length", "30", f.name,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), 30)
    try:
        d = json.loads(out or b"{}")
        return int(d["duration"]), d["fingerprint"]
    except (ValueError, KeyError) as exc:
        raise MusiqueError("Extrait illisible : enregistre au moins 10 secondes de musique.") from exc


async def chercher(duree: int, fp: str) -> dict:
    cle = (await cx.config("acoustid")).get("cle")
    if not cle:
        raise MusiqueError("La reconnaissance musicale n'est pas configurée (clé AcoustID, Paramètres › Services connectés).")
    r = await cx._http("POST", API, data={"client": cle, "duration": str(duree), "fingerprint": fp,
                                          "meta": "recordings releasegroups compress"})
    try:
        d = r.json()
    except ValueError as exc:
        raise MusiqueError("Réponse AcoustID illisible.") from exc
    if d.get("status") != "ok":
        e = d.get("error") or {}
        raise MusiqueError("Clé AcoustID refusée." if e.get("code") == 4 else f"AcoustID : {e.get('message', 'erreur')}.")
    for res in sorted(d.get("results") or [], key=lambda x: -float(x.get("score") or 0)):
        for rec in res.get("recordings") or []:
            if not rec.get("title"):
                continue
            artistes = ", ".join(a.get("name", "") for a in rec.get("artists") or [] if a.get("name"))
            album = next((g.get("title") for g in rec.get("releasegroups") or [] if g.get("type") == "Album"), None) \
                or next((g.get("title") for g in rec.get("releasegroups") or []), "")
            return {"trouve": True, "titre": rec["title"], "artiste": artistes, "album": album or "",
                    "score": round(float(res.get("score") or 0) * 100), "lien": f"https://musicbrainz.org/recording/{rec.get('id', '')}"}
    return {"trouve": False}


async def reconnaitre(donnees: bytes, nom: str = "extrait.webm") -> dict:
    if len(donnees) < 2000:
        raise MusiqueError("Extrait trop court.")
    duree, fp = await empreinte(donnees, Path(nom).suffix)
    return await chercher(duree, fp)


def phrase(r: dict) -> str:
    if not r.get("trouve"):
        return "Je ne reconnais pas ce morceau. Rapproche le micro et réessaie pendant un passage chanté."
    t = f"C'est « {r['titre']} »"
    if r.get("artiste"):
        t += f", de {r['artiste']}"
    if r.get("album") and r["album"] != r["titre"]:
        t += f", sur l'album « {r['album']} »"
    return t + "."
