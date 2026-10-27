from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import https_switch, install_cert


class Body(BaseModel):
    enabled: bool


class Names(BaseModel):
    names: list[str] = []


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/https")

    @router.get("")
    async def get():
        return {"enabled": await https_switch.enabled(), "names": await https_switch.names()}

    @router.put("/names")
    async def put_names(b: Names):
        try:
            return {"names": await https_switch.set_names(b.names)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/cert")
    async def cert():
        """Certificat racine d'EVA : à installer une fois par appareil pour supprimer l'avertissement « site non sécurisé »."""
        try:
            data = await https_switch.root_cert()
        except ValueError as exc:
            raise HTTPException(502, str(exc)) from exc
        return Response(data, media_type="application/x-x509-ca-cert", headers={"Content-Disposition": 'attachment; filename="eva-certificat.crt"'})

    @router.put("")
    async def put(b: Body):
        try:
            return await https_switch.set_enabled(b.enabled)
        except ValueError as exc:
            raise HTTPException(502, str(exc)) from exc

    return router


def make_public_router() -> APIRouter:
    """Sans identifiant : la page d'installation du certificat doit marcher avant la connexion."""
    router = APIRouter(prefix="/api/https")
    async def _pem() -> bytes:
        try:
            return await https_switch.root_cert()
        except ValueError as exc:
            raise HTTPException(502, str(exc)) from exc

    @router.get("/install")
    async def install_page():
        """Public (avant connexion) : explique comment installer le certificat sur chaque type d'appareil."""
        try:
            await https_switch.root_cert()
            return Response(install_cert.page(True), media_type="text/html; charset=utf-8")
        except ValueError as exc:
            return Response(install_cert.page(False, str(exc)), media_type="text/html; charset=utf-8")

    @router.get("/install/eva-certificat.crt")
    async def install_crt():
        return Response(await _pem(), media_type="application/x-x509-ca-cert", headers={"Content-Disposition": 'attachment; filename="eva-certificat.crt"'})

    @router.get("/install/installer-windows.bat")
    async def install_bat():
        return Response(install_cert.windows_bat(await _pem()), media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="installer-certificat-eva.bat"'})

    return router
