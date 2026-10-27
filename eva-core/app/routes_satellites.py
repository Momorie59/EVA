"""Satellites vocaux (jeton de satellite) et reconnaissance musicale."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import auth as auth_mod, installateurs, musique, profiles, satellites as sat

DOSSIER = Path(__file__).parent / "data" / "satellite"
FICHIERS = {"satellite.py": "text/x-python", "gestes.py": "text/x-python", "installer-linux.sh": "text/x-shellscript", "installer-windows.ps1": "text/plain", "installer-mac.sh": "text/x-shellscript", "LISEZMOI.txt": "text/plain",
            "desinstaller-linux.sh": "text/x-shellscript", "desinstaller-mac.sh": "text/x-shellscript", "desinstaller-windows.cmd": "text/plain",
            "eva-satellite.apk": "application/vnd.android.package-archive"}
MAX_EXTRAIT = 8 * 1024 * 1024


async def _sat(request: Request) -> tuple[str, dict]:
    q = await sat.qui(auth_mod.bearer(request.headers.get("authorization")))
    if q is None:
        raise HTTPException(401, "Satellite inconnu ou supprimé (Maison › Satellites).")
    await sat.signe_de_vie(q[0])
    return q


def _origine(request: Request) -> str:
    """Adresse d'EVA telle que la voit le navigateur (https://192.168.1.10:8443) : derrière Caddy, eva-core reçoit du http
    interne, il ne faut donc pas se fier à request.base_url."""
    import re
    o = request.headers.get("origin") or ""
    if re.fullmatch(r"https?://[A-Za-z0-9.\-\[\]:]+", o):
        return o.rstrip("/")
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    hote = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{hote}"


async def _admin(request: Request) -> None:
    if not auth_mod.protected():
        return
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    if me is None:
        raise HTTPException(401, "Connexion requise.")
    if me["role"] != "admin":
        raise HTTPException(403, "Réservé à un administrateur.")


async def _extrait(request: Request) -> bytes:
    donnees = b""
    async for morceau in request.stream():
        donnees += morceau
        if len(donnees) > MAX_EXTRAIT:
            raise HTTPException(413, "Extrait trop long (30 secondes suffisent).")
    return donnees


async def _musique(donnees: bytes, nom: str) -> dict:
    try:
        r = await musique.reconnaitre(donnees, nom)
    except musique.MusiqueError as exc:
        raise HTTPException(400, str(exc)) from exc
    phrase = musique.phrase(r)
    if r.get("trouve"):                                  # comme Jarvis : rangé dans une playlist Spotify (si relié et l'option active)
        from . import spotify
        try:
            sp = await spotify.ajouter_reconnu(r["titre"], r.get("artiste", ""))
        except spotify.SpotifyError:
            sp = None
        if sp:
            r["spotify"] = sp
            phrase += " Je l'ai ajouté à ta playlist « Reconnu par EVA »." if sp.get("ajoute") else " Il est déjà dans ta playlist « Reconnu par EVA »."
    return {**r, "phrase": phrase}


def make_router() -> APIRouter:
    r = APIRouter()

    # ---- côté satellite (jeton evasat_…)
    @r.post("/api/satellite/bonjour")
    async def bonjour(request: Request, body: dict | None = None):
        sid, s = await _sat(request)
        if body:
            sat.noter_infos(sid, body, s.get("nom", ""))
        return {"nom": s["nom"], "piece": s.get("piece", ""), "mot": "EVA", "pause": bool(s.get("pause"))}

    @r.post("/api/satellite/ordres")
    async def ordres(request: Request):
        sid, _s = await _sat(request)
        return {"ordres": await sat.attendre_ordres(sid)}

    @r.post("/api/satellite/resultat")
    async def resultat(request: Request, body: dict):
        await _sat(request)
        return {"ok": sat.recevoir_resultat(str((body or {}).get("id", "")), body.get("resultat") or {})}

    @r.post("/api/satellite/demander")
    async def demander(request: Request, body: dict):
        sid, s = await _sat(request)
        return await sat.demander(sid, s, str((body or {}).get("texte", "")))

    @r.post("/api/satellite/demander_flux")
    async def demander_flux(request: Request, body: dict):
        """Satellite récent : phrases d'attente puis réponse phrase par phrase (une ligne JSON chacune), pour parler sans attendre la fin.
        Type « event-stream » : Caddy transmet alors chaque ligne aussitôt, sans la garder en tampon."""
        sid, s = await _sat(request)
        return StreamingResponse(sat.demander_flux(sid, s, str((body or {}).get("texte", ""))), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @r.post("/api/satellite/repondre_flux")
    async def repondre_flux(request: Request, body: dict):
        sid, _s = await _sat(request)
        return StreamingResponse(sat.repondre_flux(sid, str((body or {}).get("texte", ""))), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @r.post("/api/satellite/eveil")
    async def eveil(request: Request, body: dict | None = None):
        """Plusieurs satellites ont entendu la même phrase : seul celui qui l'entend le mieux répond."""
        sid, _s = await _sat(request)
        b = body or {}
        try:
            score = float(b.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        return {"repondre": await sat.eveil(sid, score, bool(b.get("suite")))}

    @r.get("/api/satellite/tableau")
    async def tableau(request: Request):
        """Tuiles de la fenêtre flottante au repos (météo, agenda, colis, musique, post-its), selon les droits du compte du satellite."""
        sid, s = await _sat(request)
        from . import tableau as tableau_mod
        u = next((x for x in auth_mod.list_users() if x["user"].lower() == s.get("compte", "").lower()), None)
        role, user = (u["role"], u["user"]) if u else ("admin", "")
        ctx = (profiles.user_var.set(user), profiles.role_var.set(role))
        try:
            return await tableau_mod.composer(sid, role, user)
        finally:
            profiles.user_var.reset(ctx[0])
            profiles.role_var.reset(ctx[1])

    @r.post("/api/satellite/repondre")
    async def repondre(request: Request, body: dict):
        sid, _s = await _sat(request)
        return await sat.repondre(sid, str((body or {}).get("texte", "")))

    @r.post("/api/satellite/musique")
    async def musique_sat(request: Request, nom: str = Query("extrait.wav")):
        await _sat(request)
        return await _musique(await _extrait(request), nom)

    @r.get("/api/public/satellite/version")
    async def version_satellite():
        return {"version": installateurs.version(), "android": installateurs.version_android()}

    @r.get("/api/public/satellite/{fichier}")
    async def telecharger(fichier: str):
        if fichier not in FICHIERS or not (DOSSIER / fichier).is_file():
            raise HTTPException(404, "Fichier introuvable.")
        if fichier.endswith(".ps1"):                # Windows PowerShell 5 lit les accents correctement seulement avec la marque UTF-8
            contenu = (DOSSIER / fichier).read_bytes()
            return Response(contenu if contenu.startswith(b"\xef\xbb\xbf") else b"\xef\xbb\xbf" + contenu, media_type="text/plain; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{fichier}"'})
        return FileResponse(DOSSIER / fichier, media_type=FICHIERS[fichier], filename=fichier)

    @r.get("/api/home/admin/satellites-desinstallation")
    async def desinstallation(request: Request):
        """Fichiers et commandes pour désinstaller un satellite d'une machine (même s'il n'est plus dans la liste)."""
        await _admin(request)
        return installateurs.desinstallation(_origine(request))

    @r.post("/api/home/admin/satellites/{sid}/diagnostic")
    async def diagnostic(sid: str, request: Request, body: dict | None = None):
        """État du satellite vu de l'intérieur (micro, ce qu'il a entendu, erreurs, journal) ; test=true : il parle puis écoute 4 s."""
        await _admin(request)
        s = next((x for x in await sat.lister() if x["id"] == sid), None)
        if s is None:
            raise HTTPException(404, "Satellite introuvable.")
        if not sat.ecoute(sid):
            return {"connecte": False, "satellite": s}
        test = bool((body or {}).get("test"))
        r = await sat.ordonner(sid, {"type": "test_micro" if test else "diagnostic"}, delai=40 if test else 15)
        if r.get("error") and "pris en charge" in str(r["error"]):
            r = {"error": "Programme du satellite trop ancien pour le diagnostic : réinstalle-le (Réinstaller)."}
        return {"connecte": True, "satellite": s, **({"test": r} if test else {"diag": r})}

    @r.post("/api/home/admin/satellites/{sid}/controle")
    async def controle(sid: str, request: Request, body: dict):
        """Redémarrer, arrêter, ou « parler maintenant » (écoute la phrase suivante sans « EVA ») sur un satellite allumé."""
        await _admin(request)
        action = str((body or {}).get("action", ""))
        if action not in ("redemarrer", "arreter", "parler"):
            raise HTTPException(400, "Action : redemarrer, arreter ou parler.")
        if not sat.ecoute(sid):
            raise HTTPException(409, "Ce satellite n'est pas allumé (ou trop ancien) : démarre-le sur la machine (raccourci « EVA démarrer »).")
        return await sat.ordonner(sid, {"type": "controle", "action": action}, delai=15)

    @r.post("/api/home/admin/satellites/{sid}/ecoute")
    async def ecoute(sid: str, request: Request, body: dict):
        """Active ou met en pause l'écoute d'un satellite (il n'écoute plus « EVA… », mais reste joignable pour les annonces)."""
        await _admin(request)
        try:
            return await sat.regler_pause(sid, not bool((body or {}).get("actif", True)))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @r.post("/api/home/admin/satellites/{sid}/installateur")
    async def installateur(sid: str, request: Request, body: dict):
        """Nouveau jeton + installateur prêt pour le système choisi (l'ancien jeton du satellite cesse de marcher)."""
        await _admin(request)
        b = body or {}
        eva = str(b.get("eva") or "").strip() or _origine(request)
        try:
            s = await sat.renouveler(sid)
            systeme, options = str(b.get("systeme", "")), list(b.get("options") or [])
            return {"satellite": {k: v for k, v in s.items() if k != "jeton"}, "version": installateurs.version(),
                    "duree": installateurs.duree(systeme, options), **installateurs.generer(systeme, eva, s["jeton"], s["nom"], options)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ---- gestion (administrateur)
    @r.get("/api/home/admin/satellites")
    async def lister(request: Request):
        await _admin(request)
        return {"satellites": await sat.lister(), "comptes": [u["user"] for u in auth_mod.list_users()], "version": installateurs.version(),
                "version_android": installateurs.version_android(),
                "durees": {sy: installateurs.duree(sy, []) for sy in installateurs.SYSTEMES}}

    @r.post("/api/home/admin/satellites")
    async def creer(request: Request, body: dict):
        await _admin(request)
        try:
            return await sat.creer(body.get("nom", ""), body.get("piece", ""), body.get("compte", ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.delete("/api/home/admin/satellites/{sid}")
    async def supprimer(sid: str, request: Request, garder_programme: bool = False):
        """Supprime le satellite. S'il est en ligne, EVA lui demande d'abord de se désinstaller lui-même (programme,
        lancement automatique, dossier) ; sinon (ou en cas d'échec) on rend les commandes de désinstallation à lancer."""
        await _admin(request)
        infos = sat._infos.get(sid, {})
        res: dict = {}
        if not garder_programme and sat.ecoute(sid):
            res = await sat.ordonner(sid, {"type": "desinstaller"}, delai=20)
        await sat.supprimer(sid)
        auto = bool(res.get("ok"))
        return {"ok": True, "desinstalle": auto, "fait": res.get("fait", []), "reste": res.get("reste", []) or ([res["error"]] if res.get("error") else []),
                "systeme": infos.get("systeme", ""), "commandes": installateurs.desinstallation(_origine(request))}

    # ---- interface : « quelle est cette musique ? »
    @r.post("/api/musique/reconnaitre")
    async def musique_ui(request: Request, nom: str = Query("extrait.webm")):
        if auth_mod.protected() and await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization"))) is None:
            raise HTTPException(401, "Connexion requise.")
        return await _musique(await _extrait(request), nom)

    return r
