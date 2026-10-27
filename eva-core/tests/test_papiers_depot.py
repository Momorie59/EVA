"""Dossiers surveillés, traitement en masse et réglages des papiers."""
import os
import time

import pytest

from app import papiers
from app.papiers import depot
from app.papiers.config import SOUS_DOSSIER_IMPORTES, Reglages, valider

from conftest import run


def _fichier(p, contenu=b"%PDF-1.4 x", age=120):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(contenu)
    t = time.time() - age
    os.utime(p, (t, t))
    return p


@pytest.fixture
def nas(env):
    m, p, o, tmp = env
    racine = tmp / "nas"
    m.s.dossiers = ["a-classer"]
    return m, p, racine


def test_import_en_masse_et_rangement(nas):
    m, p, racine = nas
    for i in range(30):                                                    # copie en masse
        _fichier(racine / "a-classer" / "2024" / f"facture-{i:02}.pdf")
    _fichier(racine / "a-classer" / "photo.JPG")
    _fichier(racine / "a-classer" / "notes.exe")                           # format refusé : ignoré
    _fichier(racine / "a-classer" / "en-cours.pdf", age=1)                 # encore en copie : attendu
    _fichier(racine / "a-classer" / ".cache" / "x.pdf")                    # caché : ignoré
    b1 = depot.scanner(m.db, p, racine, m.s)
    assert b1["envoyes"] == depot.MAX_ENVOIS and b1["en_attente"] == 31 - depot.MAX_ENVOIS
    b2 = depot.scanner(m.db, p, racine, m.s)
    assert b2["envoyes"] == 31 - depot.MAX_ENVOIS and b2["en_attente"] == 0
    assert len(p.deposes) == 31
    rangés = list((racine / "a-classer" / SOUS_DOSSIER_IMPORTES).rglob("*.*"))
    assert len(rangés) == 31 and (racine / "a-classer" / SOUS_DOSSIER_IMPORTES / "2024" / "facture-00.pdf").exists()
    assert (racine / "a-classer" / "notes.exe").exists() and (racine / "a-classer" / "en-cours.pdf").exists()
    assert depot.scanner(m.db, p, racine, m.s)["envoyes"] == 0              # rien n'est renvoyé deux fois


def test_modes_supprimer_et_laisser(nas):
    m, p, racine = nas
    f = _fichier(racine / "a-classer" / "a.pdf")
    m.s.apres_import = "supprimer"
    depot.scanner(m.db, p, racine, m.s)
    assert not f.exists() and p.deposes == [("a.pdf", 10)]
    g = _fichier(racine / "a-classer" / "b.pdf")
    m.s.apres_import = "laisser"
    depot.scanner(m.db, p, racine, m.s)
    depot.scanner(m.db, p, racine, m.s)
    assert g.exists() and [n for n, _ in p.deposes] == ["a.pdf", "b.pdf"]   # laissé, mais envoyé une seule fois
    _fichier(g, b"%PDF-1.4 nouvelle version")                               # modifié : renvoyé
    depot.scanner(m.db, p, racine, m.s)
    assert [n for n, _ in p.deposes] == ["a.pdf", "b.pdf", "b.pdf"]


def test_erreurs_et_dossiers_absents(nas):
    m, p, racine = nas
    m.s.dossiers = ["a-classer", "inexistant", "../../etc"]
    _fichier(racine / "a-classer" / "vide.pdf", b"")
    _fichier(racine / "a-classer" / "ok.pdf")
    b = depot.scanner(m.db, p, racine, m.s)
    assert b["envoyes"] == 1 and b["erreurs"] == 1
    assert any("n'existe pas" in x for x in b["problemes"]) and any("sort du dossier" in x for x in b["problemes"])
    for _ in range(5):                                                     # abandonné après max_retries
        depot.scanner(m.db, p, racine, m.s)
    assert m.db.one("SELECT tentatives FROM imports WHERE chemin LIKE '%vide.pdf'")["tentatives"] == m.s.max_retries
    p.panne = True                                                          # Paperless hors ligne : réessayé plus tard
    _fichier(racine / "a-classer" / "plus-tard.pdf")
    assert depot.scanner(m.db, p, racine, m.s)["erreurs"] == 1
    p.panne = False
    assert depot.scanner(m.db, p, racine, m.s)["envoyes"] == 1


def test_progression(nas):
    m, p, racine = nas
    for i in range(3):
        _fichier(racine / "a-classer" / f"f{i}.pdf")
    pr = run(papiers.progression())
    assert pr["dans_les_dossiers"] == 3 and pr["dans_paperless"] == 4 and pr["a_analyser"] == 4
    run(papiers.passage())
    pr = run(papiers.progression())
    assert pr["dans_les_dossiers"] == 0 and pr["imports_envoyes"] == 3 and pr["analyses"] == 3 and pr["a_analyser"] == 1   # 3 analyses par passage


def test_reglages():
    r, faits = valider(Reglages(), {"paperless_url": "http://192.168.1.10:8002/", "alert_days": "7, 30,0",
                                    "dossiers": ["/majordome/a-classer/", "Scans"], "apres_import": "laisser",
                                    "paperless_token": "", "inconnu": 1})
    assert r.paperless_url == "http://192.168.1.10:8002" and r.alert_days == [30, 7, 0]
    assert r.dossiers == ["majordome/a-classer", "Scans"] and "paperless_token" not in faits and "inconnu" not in faits
    for mauvais in ({"paperless_url": "ftp://x"}, {"alert_days": "-3"}, {"dossiers": ["../etc"]},
                    {"apres_import": "brûler"}, {"analyses_par_passage": 0}):
        with pytest.raises(ValueError):
            valider(Reglages(), mauvais)
    assert Reglages(paperless_token="secret").publics()["paperless_token"] is True


def test_maj_reglages_reconstruit_le_moteur(env):
    m, *_ = env
    pub = run(papiers.maj_reglages({"dossiers": ["Scans"], "analyses_par_passage": 5}))
    assert pub["dossiers"] == ["Scans"] and pub["analyses_par_passage"] == 5 and pub["paperless_token"] is True
    assert papiers.moteur() is not m                                       # reconstruit avec les nouveaux réglages
    with pytest.raises(papiers.PapiersError):
        run(papiers.maj_reglages({"apres_import": "n'importe quoi"}))
