from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import cities


class Body(BaseModel):
    default: str
    cities: list[str] = []


def make_router() -> APIRouter:
    router = APIRouter(prefix="/api/cities")

    @router.get("")
    async def get():
        return await cities.get()

    @router.put("")
    async def put(b: Body):
        try:
            return await cities.save(b.default, b.cities)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
