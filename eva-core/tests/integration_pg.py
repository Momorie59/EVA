import tempfile
from pathlib import Path
"""Aide pour les tests d'intégration : une vraie base Postgres et l'application EVA complète.

Activés seulement si EVA_TEST_PG est défini (ex. postgresql://eva@127.0.0.1:55432/postgres) ; sinon ignorés.
Tous les modules partagent la même application et la même base neuve (fixture « eva »)."""
import asyncio
import os
import uuid

import pytest

PG = os.getenv("EVA_TEST_PG", "")


def base_neuve() -> str:
    import asyncpg
    nom = "evatest_" + uuid.uuid4().hex[:8]

    async def creer():
        c = await asyncpg.connect(PG)
        await c.execute(f'CREATE DATABASE "{nom}"')
        await c.close()
    asyncio.run(creer())
    return PG.rsplit("/", 1)[0] + "/" + nom


def supprimer_base(url: str) -> None:
    import asyncpg
    nom = url.rsplit("/", 1)[1]
    if not nom.startswith("evatest_"):
        return

    async def drop():
        c = await asyncpg.connect(PG)
        await c.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
        await c.close()
    try:
        asyncio.run(drop())
    except Exception:  # noqa: BLE001 — le ménage ne doit pas faire échouer les tests
        pass


requiert_pg = pytest.mark.skipif(not PG, reason="EVA_TEST_PG non défini : pas de Postgres pour les tests d'intégration")


MDP = "Mot-de-passe-solide-1"


@pytest.fixture(scope="session")
def eva():
    """EVA complète sur une base neuve : un administrateur (alice) et deux personnes (bob, carla)."""
    from app.config import settings
    settings.database_url = base_neuve()
    settings.workspace_root = tempfile.mkdtemp(prefix="eva-ws-")
    settings.ollama_host = "http://127.0.0.1:9"                  # aucun modèle : rien ne doit l'appeler ici
    from fastapi.testclient import TestClient
    import app.main as m

    async def _rien():
        return None
    boucle = m.papiers_mod.boucle
    m.papiers_mod.boucle = _rien                                 # la boucle des papiers réels gênerait les tests du majordome
    settings.workspace_root = str(m.workspace_root)              # app.main a pu être importée plus tôt avec un autre dossier
    with TestClient(m.app) as c:
        admin = c.post("/api/auth/setup", json={"user": "alice", "password": MDP}).json()["token"]
        H = lambda t: {"Authorization": f"Bearer {t}"}           # noqa: E731
        for nom in ("bob", "carla"):
            assert c.post("/api/auth/users", json={"user": nom, "password": MDP, "role": "user"}, headers=H(admin)).status_code == 200
        jetons = {"alice": admin}
        for nom in ("bob", "carla"):
            jetons[nom] = c.post("/api/auth/login", json={"user": nom, "password": MDP}).json()["token"]
        yield {"c": c, "m": m, "H": H, "t": jetons, "ws": Path(m.workspace_root)}
    m.papiers_mod.boucle = boucle
    supprimer_base(settings.database_url)                          # pas d'accumulation de bases de test


