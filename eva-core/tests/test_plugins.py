"""Plugins : chargés seulement une fois activés, outils branchés au registre et proposés au modèle, plugin cassé ignoré,
symlinks jamais suivis par les outils de fichiers, phrase d'accord unique."""
import shutil
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def test_plugins(eva, tmp_path, monkeypatch):
    from app import plugins
    from app.harness.selection import select_tool_names
    c, A, m = eva["c"], eva["H"](eva["t"]["alice"]), eva["m"]
    shutil.copytree(RACINE / "plugins" / "exemple", tmp_path / "exemple")
    (tmp_path / "casse").mkdir()
    (tmp_path / "casse" / "plugin.py").write_text("raise RuntimeError('boum')\n")
    monkeypatch.setenv("EVA_PLUGINS_DIR", str(tmp_path))
    d = c.get("/api/plugins", headers=A).json()["plugins"]
    ex = next(p for p in d if p["nom"] == "exemple")
    assert not ex["actif"] and ex["outils"] == [] and "exemple_tirage" not in m.registry.names()   # rien sans accord
    assert "boum" in next(p for p in d if p["nom"] == "casse")["erreur"]
    d = c.put("/api/plugins", json={"exemple": True}, headers=A).json()["plugins"]
    assert next(p for p in d if p["nom"] == "exemple")["outils"] == ["exemple_tirage"]
    assert "exemple_tirage" in m.registry.names()
    assert "exemple_tirage" in select_tool_names(["fais un pile ou face"], m.registry.names())
    assert "exemple_tirage" not in select_tool_names(["quel temps fait-il ?"], m.registry.names())
    r = c.portal.call(lambda: m.registry.get("exemple_tirage").execute(sorte="liste", choix=["a", "b"]))
    assert r["resultat"] in ("a", "b")
    assert c.put("/api/plugins", json={"exemple": True}, headers=eva["H"](eva["t"]["bob"])).status_code == 403
    c.put("/api/plugins", json={"exemple": False}, headers=A)
    assert "exemple_tirage" not in m.registry.names()


def test_liens_symboliques_jamais_suivis(tmp_path):
    from app.harness.tools.dev_tools import _walk
    ws = tmp_path / "ws"
    (ws / "projet").mkdir(parents=True)
    (ws / "projet" / "a.txt").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("mot de passe")
    (ws / "projet" / "lien.txt").symlink_to(secret)
    (ws / "projet" / "dossier-lien").symlink_to(tmp_path)
    vus = {p.name for p in _walk(ws / "projet")}
    assert vus == {"a.txt"}


def test_phrase_accord():
    from app import autorisations
    assert autorisations.phrase_accord("fs_delete", {"path": "notes.txt"}) == "EVA veut supprimer « notes.txt »."
    assert autorisations.phrase_accord("gmail_send", {"to": "bob@exemple.fr"}, oral=True) == \
        "Je voudrais envoyer un e-mail à « bob@exemple.fr ». Tu confirmes ?"
    assert autorisations.phrase_accord("outil_inconnu", {"x": 1}) == "EVA veut utiliser « outil_inconnu » (x = 1)."
