"""Budget des IA du marché : dépense comptée, plafond mensuel, repli automatique sur le modèle local."""
from integration_pg import requiert_pg

pytestmark = requiert_pg


def test_budget(eva):
    from app import cloud_ai, ollama_client
    from app.config import settings
    c, H, t = eva["c"], eva["H"], eva["t"]
    A = H(t["alice"])
    r = c.put("/api/cloud/providers/mistral", json={"preset": "mistral", "api_key": "k", "models": "mistral-small-latest",
                                                    "prix_entree": "0,2", "prix_sortie": "0,6", "budget_mois": "0,01"}, headers=A)
    assert r.status_code == 200, r.text
    p = r.json()["providers"]["mistral"]
    assert (p["prix_entree"], p["prix_sortie"], p["budget_mois"]) == (0.2, 0.6, 0.01) and "api_key" not in p
    modele = "cloud:mistral/mistral-small-latest"
    assert c.portal.call(cloud_ai.dans_budget, modele)
    c.portal.call(cloud_ai.compter, "mistral", 20_000, 5_000)          # 0,004 + 0,003 = 0,007 €
    d = c.get("/api/cloud", headers=A).json()["depenses"]["fournisseurs"]["mistral"]
    assert d["eur"] == 0.007 and d["appels"] == 1 and not d["atteint"]
    assert c.portal.call(ollama_client._hors_budget, modele) == modele
    c.portal.call(cloud_ai.compter, "mistral", 10_000, 0)              # + 0,002 → 0,009
    c.portal.call(cloud_ai.compter, "mistral", 10_000, 0)              # + 0,002 → 0,011 ≥ 0,01
    assert c.get("/api/cloud", headers=A).json()["depenses"]["fournisseurs"]["mistral"]["atteint"]
    assert c.portal.call(ollama_client._hors_budget, modele) == settings.ollama_model           # repli local
    c.put("/api/cloud/providers/mistral", json={"preset": "mistral", "budget_mois": "0"}, headers=A)
    assert c.portal.call(ollama_client._hors_budget, modele) == modele                          # sans plafond
    assert c.put("/api/cloud/providers/mistral", json={"preset": "mistral", "budget_mois": "beaucoup"}, headers=A).status_code == 400
