"""IA gratuites (liste awesome-free-llm-apis) : catalogue, ajout en un clic, service sans clé, mise à jour de la liste."""
import json

import httpx

from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_catalogue_et_ajout(eva, monkeypatch):
    from app import cloud_ai, ia_gratuites
    c, A, B = eva["c"], eva["H"](eva["t"]["alice"]), eva["H"](eva["t"]["bob"])
    d = c.get("/api/cloud/gratuites", headers=A).json()
    par = {s["id"]: s for s in d["services"]}
    assert d["maj"] and "github.com/mnfst/awesome-free-llm-apis" in d["source"] and len(par) >= 10
    assert par["google-gemini"]["base_url"].endswith("/v1beta/openai") and par["google-gemini"]["entrainement"] == "hors_ue"
    assert par["mistral-ai"]["entrainement"] == "oui" and par["groq"]["entrainement"] == ""
    assert par["ovhcloud-ai-endpoints"]["cle_facultative"] and not par["groq"]["cle_facultative"]
    assert par["cohere"]["base_url"] == "https://api.cohere.ai/compatibility/v1" and par["ollama-cloud"]["base_url"] == "https://ollama.com/v1"
    assert par["cloudflare-workers-ai"]["compte_cloudflare"] and "carte bancaire demandée" not in sum((s["conditions"] for s in par.values()), [])
    assert all(m["id"] for s in par.values() for m in s["modeles"])                       # ni « + 55 more models » ni embeddings

    ovh = par["ovhcloud-ai-endpoints"]
    corps = {"preset": "custom", "label": ovh["nom"], "base_url": ovh["base_url"], "models": ", ".join(m["id"] for m in ovh["modeles"][:2]),
             "sans_cle": True, "gratuit": True, "prix_entree": "0", "prix_sortie": "0"}
    assert c.put(f"/api/cloud/providers/{ovh['id']}", json=corps, headers=B).status_code == 403
    p = c.put(f"/api/cloud/providers/{ovh['id']}", json=corps, headers=A).json()["providers"][ovh["id"]]
    assert p["sans_cle"] and p["gratuit"] and not p["has_key"]
    noms = [m["name"] for m in c.portal.call(cloud_ai.model_entries)]
    assert f"cloud:{ovh['id']}/{ovh['modeles'][0]['id']}" in noms                          # proposé sans clé

    vu = {}

    def repond(request: httpx.Request):
        vu["auth"] = request.headers.get("authorization")
        vu["url"] = str(request.url)
        corps_sse = 'data: {"choices":[{"delta":{"content":"Bonjour !"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=corps_sse, headers={"content-type": "text/event-stream"})
    vrai = httpx.AsyncClient
    monkeypatch.setattr(cloud_ai.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(repond), **{k: v for k, v in kw.items() if k != "transport"}))

    async def lire():
        return [x async for x in cloud_ai.stream([{"role": "user", "content": "salut"}], None, f"cloud:{ovh['id']}/{ovh['modeles'][0]['id']}")]
    evs = c.portal.call(lire)
    assert ("content", "Bonjour !") in evs and vu["auth"] is None and vu["url"].startswith(ovh["base_url"])   # aucune clé envoyée

    cf = par["cloudflare-workers-ai"]
    r = c.put(f"/api/cloud/providers/{cf['id']}", json={"preset": "custom", "base_url": cf["base_url"], "models": "x", "api_key": "k"}, headers=A)
    assert r.status_code == 400 and "Cloudflare" in r.json()["detail"]
    c.delete(f"/api/cloud/providers/{ovh['id']}", headers=A)

    data = json.loads(ia_gratuites.COPIE.read_text(encoding="utf-8"))
    data["lastUpdated"] = "2099-01-01"
    monkeypatch.setattr(ia_gratuites.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data))))
    assert c.post("/api/cloud/gratuites/maj", headers=A).json()["maj"] == "2099-01-01"
    assert c.get("/api/cloud/gratuites", headers=A).json()["maj"] == "2099-01-01"            # gardée dans la base
    monkeypatch.setattr(ia_gratuites.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"x": 1}))))
    assert "illisible" in c.post("/api/cloud/gratuites/maj", headers=A).json()["detail"]
    assert c.get("/api/cloud/gratuites", headers=A).json()["maj"] == "2099-01-01"


def test_rotation_automatique(eva, monkeypatch):
    """Quota atteint, clé refusée, panne : EVA passe tout seul au modèle / à l'IA gratuite suivante et met le fautif de côté."""
    import time as _t
    from app import cloud_ai, router
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    cloud_ai._pauses.clear()
    services = {"groq": ("https://api.groq.com/openai/v1", "", "k1", "g1, g2"), "mistral-ai": ("https://api.mistral.ai/v1", "oui", "k2", "m1"),
                "nvidia-nim": ("https://integrate.api.nvidia.com/v1", "", "k3", "n1"), "ovh": ("https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "", "", "o1, o2"),
                "aion": ("https://api.aionlabs.ai/v1", "", "", "a1")}                       # pas de clé, pas « sans clé » : en attente
    for pid, (url, ent, cle, mods) in services.items():
        c.put(f"/api/cloud/providers/{pid}", json={"preset": "custom", "label": pid, "base_url": url, "models": mods, "api_key": cle,
                                                   "sans_cle": pid == "ovh", "gratuit": True, "entrainement": ent}, headers=A)
    r = c.get("/api/cloud/rotation", headers=A).json()
    par = {x["cle"]: x for x in r["services"]}
    assert [x["cle"] for x in r["services"] if not x["bloque"]] == ["groq|g1", "groq|g2", "nvidia-nim|n1", "ovh|o1", "ovh|o2"]
    assert "entraîner" in par["mistral-ai|m1"]["bloque"] and "clé manquante" in par["aion|a1"]["bloque"]   # visibles, avec la raison
    assert "cloud:auto/gratuit" in [m["name"] for m in c.portal.call(cloud_ai.model_entries)]

    appels = []

    def repond(request: httpx.Request):
        modele = json.loads(request.content)["model"]
        appels.append(modele)
        if modele == "g1":
            return httpx.Response(429, json={"error": {"message": "Rate limit reached: requests per minute"}})     # ce modèle seulement
        if modele == "g2":
            return httpx.Response(429, json={"error": {"message": "Daily token quota exceeded. Retry after 87494 seconds."}})
        if modele == "n1":
            return httpx.Response(401, json={"error": "invalid key"})
        if modele == "o1":
            return httpx.Response(429, json={"error": "API rate limit exceeded"})
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Réponse de o2"}}]}\n\ndata: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})
    vrai = httpx.AsyncClient
    monkeypatch.setattr(cloud_ai.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(repond), **{k: v for k, v in kw.items() if k != "transport"}))

    async def demander():
        return [x async for x in cloud_ai.stream([{"role": "user", "content": "salut"}], None, "cloud:auto/gratuit")]
    assert ("content", "Réponse de o2") in c.portal.call(demander)
    assert appels == ["g1", "g2", "n1", "o1", "o2"]
    etat = {x["cle"]: x for x in c.get("/api/cloud/rotation", headers=A).json()["services"]}
    assert 60 <= etat["groq|g1"]["pause_jusqua"] - _t.time() <= 90 * 1000                           # par minute : ce modèle
    assert etat["groq|g2"]["pause_jusqua"] - _t.time() > 86000                                       # « Retry after 87494 s » : respecté
    assert etat["nvidia-nim|n1"]["pause_jusqua"] and etat["ovh|o2"]["ok"] and not etat["ovh|o2"]["pause_jusqua"]
    appels.clear()
    c.portal.call(demander)
    assert appels == ["o2"]                                                                          # rien de ce qui est en pause n'est réessayé

    # décocher un modèle, réordonner, inclure ceux qui entraînent, repli quand le serveur IA est éteint
    c.put("/api/cloud/rotation", json={"exclus": ["ovh|o2"], "ordre": ["mistral-ai|m1", "ovh|o1"], "exclure_entrainement": False, "repli": True}, headers=A)
    r = c.get("/api/cloud/rotation", headers=A).json()
    assert [x["cle"] for x in r["services"]][:2] == ["mistral-ai|m1", "ovh|o1"] and not {x["cle"]: x for x in r["services"]}["ovh|o2"]["coche"]
    assert ("mistral-ai", "m1") in [(pid, m) for pid, _p, m in cloud_ai.eligibles(c.portal.call(cloud_ai.load))]
    assert ("ovh", "o2") not in [(pid, m) for pid, _p, m in cloud_ai.eligibles(c.portal.call(cloud_ai.load))]
    assert c.portal.call(cloud_ai.fallback_model) == "cloud:auto/gratuit"

    async def aucun(force=False):
        return None
    monkeypatch.setattr(router, "installed_models", aucun)
    assert c.portal.call(lambda: router.select("Explique-moi la photosynthèse"))["model"] == "cloud:auto/gratuit"   # serveur IA éteint

    cloud_ai._pauses.clear()
    monkeypatch.setattr(cloud_ai.httpx, "AsyncClient", lambda **kw: vrai(transport=httpx.MockTransport(lambda req: httpx.Response(503, text="panne"))))
    try:
        c.portal.call(demander)
        raise AssertionError("aurait dû échouer")
    except cloud_ai.CloudError as exc:
        assert "occupées ou à court de quota" in str(exc)
    c.put("/api/cloud/rotation", json={"exclus": [], "ordre": [], "exclure_entrainement": True, "repli": False}, headers=A)
    for pid in services:
        c.delete(f"/api/cloud/providers/{pid}", headers=A)
    cloud_ai._pauses.clear()
