import csv
import io

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, features


class Creds(BaseModel):
    user: str
    password: str
    code: str = ""


class CodeBody(BaseModel):
    code: str


class PwBody(BaseModel):
    current: str
    new: str


class PassBody(BaseModel):
    password: str


class NewUser(BaseModel):
    user: str
    password: str
    role: str = "user"


class UserPatch(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    password: str | None = None


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/auth")

    def ip(request: Request) -> str:
        return (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else ""))

    async def who(authorization: str | None) -> tuple[str | None, dict]:
        tok = auth.bearer(authorization)
        me = await auth.identify(tok)
        if me is None:
            raise HTTPException(status_code=401, detail="Connexion requise.")
        return tok, me

    async def admin(authorization: str | None) -> tuple[str | None, dict]:
        tok, me = await who(authorization)
        if me["role"] != "admin":
            raise HTTPException(status_code=403, detail="Réservé à un administrateur.")
        if not auth.login_required():
            raise HTTPException(status_code=400, detail="Active d'abord la connexion (premier compte).")
        return tok, me

    def wrap(exc: auth.AuthError) -> HTTPException:
        return HTTPException(status_code=exc.status, detail=str(exc))

    @router.get("/status")
    async def status(authorization: str | None = Header(default=None)):
        me = await auth.identify(auth.bearer(authorization))
        return {"login_required": auth.login_required(), "protected": auth.protected(), "authenticated": me is not None,
                "user": (me["user"] or None) if me else None, "role": me["role"] if me and auth.protected() else None,
                "mfa": bool(me and me["user"] and auth._users.get(me["user"].lower(), {}).get("totp")), "min_password": auth.MIN_PASSWORD,
                "features": sorted(await features.effective(me["role"], me["user"] or "")) if me else []}

    @router.get("/profiles")
    async def profiles_list():
        from . import profiles
        return {"profiles": [{"role": k, "label": v["label"], "hint": v["hint"]} for k, v in profiles.PROFILES.items()]}

    @router.get("/verify")
    async def verify(authorization: str | None = Header(default=None)):
        """Utilisé par le service voix : 200 si la requête est autorisée (et la voix activée pour ce compte), 401 / 403 sinon."""
        from . import satellites, voix_interne
        if voix_interne.est_cle(auth.bearer(authorization)):                 # eva-core lui-même (annonce sur une enceinte)
            return {"ok": True}
        if (auth.bearer(authorization) or "").startswith(satellites.PREFIXE):          # satellite vocal d'une pièce
            if await satellites.qui(auth.bearer(authorization)) is None:
                raise HTTPException(status_code=401, detail="Satellite inconnu ou supprimé.")
            return {"ok": True}
        _, me = await who(authorization)
        if me["role"] != "admin" and "voice" not in await features.effective(me["role"], me["user"]):
            raise HTTPException(status_code=403, detail="La voix n'est pas activée pour ton compte.")
        return {"ok": True}

    @router.post("/setup")
    async def setup(body: Creds, request: Request, authorization: str | None = Header(default=None)):
        _, me = await who(authorization)       # si un jeton d'environnement existe, il faut l'avoir ; sinon EVA est ouverte
        try:
            r = await auth.setup(body.user.strip(), body.password, request.headers.get("user-agent", ""))
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", body.user.strip(), ip(request), "Connexion activée", "premier compte (administrateur)", 200)
        return {**r, "user": body.user.strip()}

    @router.post("/login")
    async def login(body: Creds, request: Request):
        try:
            return await auth.login(body.user.strip(), body.password, ip(request), request.headers.get("user-agent", ""), body.code)
        except auth.AuthError as exc:
            raise wrap(exc) from exc

    @router.post("/mfa/begin")
    async def mfa_begin(authorization: str | None = Header(default=None)):
        _, me = await who(authorization)
        try:
            return await auth.mfa_begin(me["user"])
        except auth.AuthError as exc:
            raise wrap(exc) from exc

    @router.post("/mfa/enable")
    async def mfa_enable(body: CodeBody, request: Request, authorization: str | None = Header(default=None)):
        _, me = await who(authorization)
        try:
            await auth.mfa_enable(me["user"], body.code)
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Double authentification activée", "", 200)
        return {"ok": True}

    @router.post("/mfa/disable")
    async def mfa_disable(body: PassBody, request: Request, authorization: str | None = Header(default=None)):
        _, me = await who(authorization)
        try:
            await auth.mfa_disable(me["user"], body.password, ip(request))
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Double authentification désactivée", "", 200)
        return {"ok": True}

    @router.post("/logout")
    async def logout(request: Request, authorization: str | None = Header(default=None)):
        me = await auth.identify(auth.bearer(authorization))
        await auth.logout(auth.bearer(authorization))
        if me and me["user"]:
            await auth.audit("logout", me["user"], ip(request), "Déconnexion", "", 200)
        return {"ok": True}

    @router.post("/logout-all")
    async def logout_all(request: Request, authorization: str | None = Header(default=None)):
        tok, me = await who(authorization)
        n = await auth.logout_all(me["user"], keep=tok)
        await auth.audit("session", me["user"], ip(request), "Autres appareils déconnectés", f"{n} session(s)", 200)
        return {"revoked": n}

    @router.post("/password")
    async def password(body: PwBody, request: Request, authorization: str | None = Header(default=None)):
        tok, me = await who(authorization)
        try:
            n = await auth.change_password(me["user"], body.current, body.new, tok, ip(request))
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Mot de passe changé", f"{n} autre(s) session(s) fermée(s)", 200)
        return {"revoked": n}

    @router.post("/disable")
    async def disable(body: PassBody, request: Request, authorization: str | None = Header(default=None)):
        _, me = await who(authorization)
        try:
            await auth.disable(me["user"], body.password, ip(request))
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Connexion désactivée", "tous les comptes supprimés", 200)
        return {"ok": True}

    # ---------- administration ----------

    @router.get("/users")
    async def users(authorization: str | None = Header(default=None)):
        await admin(authorization)
        return {"users": auth.list_users()}

    @router.post("/users")
    async def add_user(body: NewUser, request: Request, authorization: str | None = Header(default=None)):
        _, me = await admin(authorization)
        try:
            u = await auth.add_user(body.user.strip(), body.password, body.role)
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Utilisateur créé", f"{u['user']} ({u['role']})", 200)
        return u

    @router.patch("/users/{name}")
    async def patch_user(name: str, body: UserPatch, request: Request, authorization: str | None = Header(default=None)):
        _, me = await admin(authorization)
        try:
            u = await auth.update_user(name, body.role, body.disabled, body.password)
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        what = [x for x, v in (("rôle", body.role), ("état", body.disabled), ("mot de passe réinitialisé", body.password)) if v is not None]
        await auth.audit("admin", me["user"], ip(request), "Utilisateur modifié", f"{u['user']} : {', '.join(what)}", 200)
        return u

    @router.delete("/users/{name}")
    async def del_user(name: str, request: Request, authorization: str | None = Header(default=None)):
        _, me = await admin(authorization)
        try:
            await auth.delete_user(name, me["user"])
            await features.user_forget(name)
        except auth.AuthError as exc:
            raise wrap(exc) from exc
        await auth.audit("admin", me["user"], ip(request), "Utilisateur supprimé", name, 200)
        return {"ok": True}

    @router.get("/sessions")
    async def sessions(authorization: str | None = Header(default=None)):
        tok, _ = await admin(authorization)
        mine = auth._digest(tok) if tok else ""
        return {"sessions": [{**s, "current": s["id"] == mine} for s in await auth.sessions_list()]}

    @router.delete("/sessions/{sid}")
    async def revoke(sid: str, request: Request, authorization: str | None = Header(default=None)):
        _, me = await admin(authorization)
        ok = await auth.revoke_session(sid)
        if ok:
            await auth.audit("session", me["user"], ip(request), "Session révoquée", sid[:10], 200)
        return {"ok": ok}

    @router.get("/audit")
    async def audit_log(user: str = "", kind: str = "", q: str = "", limit: int = 200, before: int = 0, authorization: str | None = Header(default=None)):
        await admin(authorization)
        return {"events": await auth.audit_list(user, kind, q, limit, before)}

    @router.get("/audit.csv")
    async def audit_csv(user: str = "", kind: str = "", q: str = "", authorization: str | None = Header(default=None)):
        await admin(authorization)
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id", "date", "utilisateur", "ip", "type", "action", "détail", "statut"])
        for e in await auth.audit_list(user, kind, q, 1000):
            w.writerow([e["id"], e["ts"], e["username"], e["ip"], e["kind"], e["action"], e["detail"], e["status"]])
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="eva-journal.csv"'})

    return router
