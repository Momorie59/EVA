"""Webhooks Twilio d'un appel où EVA converse (publics : jeton d'appel dans l'adresse + signature Twilio vérifiée)."""
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import appels, connecteurs as cx


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api/public/appel")

    async def _verifier(request: Request, jeton: str, etape: str) -> tuple[dict, dict]:
        a = appels.appel(jeton)
        params = dict(parse_qsl((await request.body()).decode(errors="ignore"), keep_blank_values=True))
        c = await cx.config("twilio")
        url = f"{a['base'] if a else ''}/api/public/appel/{jeton}/{etape}"
        if not a or not c or not appels.signature_valide(c.get("token", ""), url, params, request.headers.get("x-twilio-signature", "")):
            raise HTTPException(403, "Requête refusée.")
        return a, params

    def xml(texte: str) -> Response:
        return Response(texte, media_type="application/xml")

    @r.post("/{jeton}/debut")
    async def debut(jeton: str, request: Request):
        a, _p = await _verifier(request, jeton, "debut")
        return xml(appels.debut(a, jeton))

    @r.post("/{jeton}/tour")
    async def tour(jeton: str, request: Request):
        a, p = await _verifier(request, jeton, "tour")
        return xml(await appels.tour(a, jeton, p.get("SpeechResult", "")))

    @r.post("/{jeton}/attendre")
    async def attendre(jeton: str, request: Request):
        a, _p = await _verifier(request, jeton, "attendre")
        return xml(await appels.attendre(a, jeton))

    @r.post("/{jeton}/fin")
    async def fin(jeton: str, request: Request):
        _a, p = await _verifier(request, jeton, "fin")
        if p.get("CallStatus") in ("completed", "busy", "no-answer", "failed", "canceled"):
            await appels.terminer(jeton, p["CallStatus"])
        return xml(appels.twiml(""))

    return r
