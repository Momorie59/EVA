"""Infos pratiques (portage de cornelius-modules) : règles de ramassage, vacances, fériés, carburants, éphéméride, RSS."""
from datetime import date, datetime

import pytest

from app import pratique


def test_regles_poubelles():
    r = pratique.lire_regle("1er et 3e mercredi du mois")
    assert r == {"jours": [2], "ordinaux": [1, 3], "parite": "toutes"}
    assert pratique.lire_regle("Mardis semaines paires")["parite"] == "paires"
    assert pratique.lire_regle("dernier vendredi du mois")["ordinaux"] == [-1]
    with pytest.raises(pratique.PratiqueError):
        pratique.lire_regle("quand il pleut")
    with pytest.raises(pratique.PratiqueError):
        pratique.lire_regle("1er mardi semaines paires")
    bacs = [{"bac": "menager", "jours": "lundi et jeudi"}, {"bac": "verre", "jours": "1er mercredi du mois"},
            {"bac": "emballages", "jours": "mercredi semaines paires"}]
    jeu = datetime(2026, 10, 29, 9, 0)                      # jeudi 29/10/2026 (semaine 44, paire)
    p = pratique.prochains_ramassages(bacs, jeu)
    assert p[0] == {"bac": "menager", "date": date(2026, 10, 29)}          # avant midi : celui du jour compte
    verre = next(x for x in p if x["bac"] == "verre")
    assert verre["date"] == date(2026, 11, 4)                              # 1er mercredi de novembre
    emb = next(x for x in p if x["bac"] == "emballages")
    assert emb["date"] == date(2026, 11, 11)                              # 4/11 : semaine 45 impaire → 11/11 (46)
    soir = pratique.prochains_ramassages(bacs, datetime(2026, 10, 29, 18, 0))
    assert soir[0]["date"] == date(2026, 11, 2)                            # après midi : lundi suivant


def test_vacances_et_feries():
    res = [{"description": "Vacances de la Toussaint", "population": "-", "start_date": "2026-10-16T22:00:00+00:00", "end_date": "2026-11-01T23:00:00+00:00"},
           {"description": "Vacances de Noël", "population": "-", "start_date": "2026-12-18T23:00:00+00:00", "end_date": "2027-01-03T23:00:00+00:00"},
           {"description": "Vacances d'Hiver", "population": "Enseignants", "start_date": "2027-02-05T23:00:00+00:00", "end_date": "2027-02-21T23:00:00+00:00"},
           {"description": "Vacances de Noël", "population": "Élèves", "start_date": "2026-12-18T23:00:00+00:00", "end_date": "2027-01-03T23:00:00+00:00"}]
    v = pratique.vacances_depuis(res, date(2026, 10, 29))
    assert [x["nom"] for x in v] == ["Vacances de la Toussaint", "Vacances de Noël"]                 # enseignants ignorés, doublon fusionné
    assert v[0]["debut"] == date(2026, 10, 17) and v[0]["reprise"] == date(2026, 11, 2)
    f = pratique.feries_depuis({"2026-05-01": "1er mai", "2026-11-01": "Toussaint", "2026-11-11": "11 novembre"}, date(2026, 10, 29))
    assert [x["nom"] for x in f] == ["Toussaint", "11 novembre"]


def test_carburants_ephemeride_rss():
    st = pratique.stations_depuis([{"adresse": "1 rue A", "ville": "LONS", "cp": "39000", "gazole_prix": 1.799, "gazole_maj": "2026-10-28T08:00:00+00:00"},
                                   {"adresse": "2 rue B", "ville": "LONS", "cp": "39000", "gazole_prix": 1.689},
                                   {"adresse": "3 rue C", "ville": "LONS", "cp": "39000", "gazole_prix": None}], "gazole")
    assert [s["prix"] for s in st] == [1.689, 1.799] and st[1]["maj"] == "2026-10-28"
    ev = pratique.evenements_depuis([{"text": "A", "year": 2016}, {"text": "B", "year": 1976}, {"text": "C", "year": 2025}], 2026)
    assert ev[0]["texte"] == "B" and ev[0]["il_y_a"] == 50                  # 50 ans : le plus « rond »
    rss = b"""<?xml version="1.0"?><rss><channel><title>Franceinfo - Les titres</title>
      <item><title>Premier titre</title><link>https://x/1</link></item><item><title>Second  titre</title></item></channel></rss>"""
    nom, items = pratique.titres_depuis(rss, 5)
    assert nom == "Franceinfo" and [i["titre"] for i in items] == ["Premier titre", "Second titre"] and items[0]["lien"] == "https://x/1"
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title><entry><title>Un</title><link href="https://y"/></entry></feed>"""
    assert pratique.titres_depuis(atom, 5)[1][0]["lien"] == "https://y"
    with pytest.raises(pratique.PratiqueError):
        pratique.titres_depuis(b"<html><body>pas un flux", 5)


def test_reglages_et_outils(eva, monkeypatch):
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    assert c.put("/api/pratique/reglages", json={"zone": "B"}, headers=H(t["bob"])).status_code == 403
    r = c.put("/api/pratique/reglages", json={"poubelles": {"bacs": [{"bac": "menager", "jours": "quand il pleut"}]}}, headers=H(t["alice"]))
    assert r.status_code == 400 and "pleut" in r.json()["detail"]
    r = c.put("/api/pratique/reglages", json={"zone": "C", "poubelles": {"bacs": [{"bac": "menager", "jours": "lundi et jeudi"}]},
                                              "carburant": {"lieu": "39000"}}, headers=H(t["alice"]))
    assert r.status_code == 200 and r.json()["zone"] == "C"
    res = c.portal.call(lambda: m.registry.get("pratique_poubelles").execute())
    assert "ordures ménagères" in res["phrase"]

    class Rep:
        status_code, content = 200, b"{}"

        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d
    vus = {}

    async def faux_get(url, params=None, accept="", limite=0):
        vus[url] = params
        return Rep({"results": [{"adresse": "1 rue A", "ville": "LONS", "cp": "39000", "e10_prix": 1.75}]})
    monkeypatch.setattr(pratique, "_get", faux_get)
    res = c.portal.call(lambda: m.registry.get("pratique_carburants").execute(carburant="essence"))
    assert "SP95-E10" in res["phrase"] and "1,75" in res["phrase"]
    assert 'cp="39000"' in vus[pratique.URL_CARBURANTS]["where"]
    c.put("/api/pratique/reglages", json={"poubelles": {"bacs": []}, "zone": "B", "carburant": {"lieu": ""}}, headers=H(t["alice"]))
