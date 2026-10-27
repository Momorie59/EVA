"""Recherche approfondie : requêtes en parallèle, sources variées, pages lues, extraits à citer."""
import asyncio

from app.harness.tools.recherche_tools import RechercheApprofondieTool


def test_recherche_approfondie():
    outil = RechercheApprofondieTool()
    pages = {
        "https://a.fr/prix": ("Prix Crit'Air", "Menu du site\n\nLa vignette Crit'Air coûte 3,77 euros en 2026, envoi compris.\n\nPied de page."),
        "https://a.fr/autre": ("A autre", "Rien à voir avec la question, une recette de cuisine pour la famille entière."),
        "https://a.fr/troisieme": ("A 3", "Troisième page du même site, sur la vignette également, mais refusée."),
        "https://b.org/vignette": ("Vignette b", ""),
    }

    async def cherche(query="", max_results=6, **_):
        if query == "en panne":
            return {"error": "x"}
        return {"results": [{"title": t, "url": u, "snippet": f"extrait {u}"} for u, (t, _x) in pages.items()]}

    async def lit(url="", _max=0, **_):
        if url not in pages:
            return {"error": "404"}
        return {"url": url, "title": pages[url][0], "text": pages[url][1]}
    outil._cherche.execute, outil._lit.execute = cherche, lit
    r = asyncio.run(outil.execute(question="Combien coûte la vignette Crit'Air en 2026 ?", requetes=["prix vignette crit air", "en panne"]))
    urls = [s["url"] for s in r["sources"]]
    assert urls[0] == "https://a.fr/prix" and "3,77 euros" in r["sources"][0]["extrait"] and "Menu" not in r["sources"][0]["extrait"]
    assert "https://a.fr/troisieme" not in urls                         # deux pages au plus par site
    assert r["sources"][-1]["url"] == "https://b.org/vignette" and r["sources"][-1]["extrait"].startswith("extrait")   # page vide → extrait du moteur
    assert [s["n"] for s in r["sources"]] == list(range(1, len(urls) + 1)) and "Sources" in r["consigne"]
    assert "error" in asyncio.run(outil.execute(question="x", requetes=["en panne"]))
