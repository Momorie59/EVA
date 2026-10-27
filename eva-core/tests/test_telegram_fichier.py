"""Briefing en PDF envoyé sur Telegram (comme Jarvis) : fichier du workspace seulement."""
import json

import httpx

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_envoi_fichier(eva, monkeypatch):
    from app import telegram as tg
    from app.db import get_pool
    c, m = eva["c"], eva["m"]

    async def regler():
        async with get_pool().acquire() as conn:
            await conn.execute("INSERT INTO kv (key, value) VALUES ('telegram',$1::jsonb) ON CONFLICT (key) DO UPDATE SET value=$1::jsonb",
                               json.dumps({"token": "123:abc", "allowed": [42]}))
    c.portal.call(regler)
    envois = []

    async def faux_post(self, url, data=None, files=None, **kw):
        envois.append((url, data, files))
        return httpx.Response(200, json={"ok": True, "result": {}})
    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    doc = c.portal.call(lambda: m.registry.get("document_creer").execute(format="pdf", nom="Briefing du jour", contenu="# Briefing\n\n- Soleil"))
    r = c.portal.call(lambda: m.registry.get("telegram_notify").execute(text="Ton briefing ☀️", fichier=doc["path"]))
    assert r == {"sent_to": 1, "fichier": "Briefing du jour.pdf"}, r
    url, data, files = envois[-1]
    assert url.endswith("/bot123:abc/sendDocument") and data["chat_id"] == "42" and files["document"][1][:4] == b"%PDF"
    assert "introuvable" in c.portal.call(lambda: m.registry.get("telegram_notify").execute(text="x", fichier="../../etc/passwd"))["error"]
