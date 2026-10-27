"""Évolution toute seule : les modifications d'EVA survivent aux mises à jour, et l'application automatique
se fait avec banc d'essai avant/après et retour arrière."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import selfboot  # noqa: E402


def _base(d: Path, version: str) -> Path:
    (d / "app").mkdir(parents=True, exist_ok=True)
    (d / "app" / "__init__.py").write_text("")
    (d / "app" / "main.py").write_text(f"VERSION = {version!r}\n")
    (d / "app" / "outils.py").write_text("def dire():\n    return 'bonjour'\n")
    return d


def test_modifs_d_eva_rejouees_apres_mise_a_jour(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_SELF_DIR", str(tmp_path / "self"))
    (tmp_path / "self").mkdir()
    base = _base(tmp_path / "v1", "1")
    live, mode = selfboot.choose_code_dir(base)
    assert mode == "live"
    (live / "app" / "outils.py").write_text("def dire():\n    return 'bonjour'\n\n\ndef nouveau():\n    return 'appris'\n")
    selfboot._git(live, "commit", "-qam", "Proposition #1 : nouvel outil")
    base2 = _base(tmp_path / "v2", "2")                                       # mise à jour d'EVA
    live2, mode2 = selfboot.choose_code_dir(base2)
    assert mode2 == "live"
    assert "VERSION = '2'" in (live2 / "app" / "main.py").read_text()          # nouveau code de base
    assert "appris" in (live2 / "app" / "outils.py").read_text()               # + la modification d'EVA
    info = json.loads((tmp_path / "self" / "obsolete.json").read_text())
    assert info["reportees"] == ["Proposition #1 : nouvel outil"] and info["laissees"] == []


def test_modif_en_conflit_laissee_de_cote(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_SELF_DIR", str(tmp_path / "self"))
    (tmp_path / "self").mkdir()
    live, _ = selfboot.choose_code_dir(_base(tmp_path / "v1", "1"))
    (live / "app" / "main.py").write_text("VERSION = 'eva'\n")
    selfboot._git(live, "commit", "-qam", "Proposition #2 : change la version")
    live2, mode = selfboot.choose_code_dir(_base(tmp_path / "v2", "2"))
    assert mode == "live" and "VERSION = '2'" in (live2 / "app" / "main.py").read_text()
    info = json.loads((tmp_path / "self" / "obsolete.json").read_text())
    assert info["laissees"] == ["Proposition #2 : change la version"]


def test_evolution_auto(eva, monkeypatch):
    from datetime import datetime
    from app import lecons, self_mod
    c = eva["c"]
    run = lambda f: c.portal.call(f)  # noqa: E731
    run(lambda: lecons.regler(auto=True, heure=3))
    run(lambda: lecons._sauver_auto({}))
    props = [{"id": 7, "status": "pending", "title": "Mieux lister les recettes"}]
    faits = []
    monkeypatch.setattr(self_mod, "enabled", lambda: True)
    monkeypatch.setattr(self_mod, "status", lambda: {"boot_error": None})

    async def lister():
        return props

    async def appliquer(pid):
        faits.append(("apply", pid))
        return {"ok": True}

    async def annuler(pid):
        faits.append(("revert", pid))
        return {"ok": True}
    scores = iter([5, 4])

    async def score(registry, modele):
        return {"score": next(scores), "total": 6}
    monkeypatch.setattr(self_mod, "list_proposals", lister)
    monkeypatch.setattr(self_mod, "apply", appliquer)
    monkeypatch.setattr(self_mod, "revert", annuler)
    monkeypatch.setattr(lecons, "_score", score)
    nuit, jour = datetime(2026, 10, 28, 4, 0), datetime(2026, 10, 28, 14, 0)
    assert run(lambda: lecons.evolution_auto(None, jour)) == "hors_fenetre"
    assert run(lambda: lecons.evolution_auto(None, nuit)) == "appliquee" and faits == [("apply", 7)]
    assert run(lambda: lecons.evolution_auto(None, nuit)) == "attente"           # EVA redémarre
    e = run(lecons._etat_auto); e["applique_le"] -= 3600
    run(lambda: lecons._sauver_auto(e))
    assert run(lambda: lecons.evolution_auto(None, nuit)) == "annulee"           # 4/6 au lieu de 5/6 : retour arrière
    assert faits[-1] == ("revert", 7)
    assert run(lecons._etat_auto)["dernier"]["resultat"] == "annulee"
    assert run(lambda: lecons.evolution_auto(None, nuit)) == "deja_fait"         # une par nuit
    run(lambda: lecons.regler(auto=False))


def test_journal(eva):
    from app import journal
    c, A = eva["c"], eva["H"](eva["t"]["alice"])
    c.portal.call(lambda: journal.noter("routine", "Routine « Bonsoir » : lumière salon : off"))
    c.portal.call(lambda: journal.noter("bizarre", "genre inconnu rangé en système"))
    lignes = c.get("/api/journal", headers=A).json()["lignes"]
    assert any(l["genre"] == "routine" and "Bonsoir" in l["texte"] for l in lignes)
    assert any(l["genre"] == "systeme" and "inconnu" in l["texte"] for l in lignes)
    assert all(l["genre"] == "routine" for l in c.get("/api/journal?genre=routine", headers=A).json()["lignes"])
    assert c.get("/api/journal", headers=eva["H"](eva["t"]["bob"])).status_code == 403          # administrateur seulement
