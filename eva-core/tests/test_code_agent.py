"""Agent de code (Aider) : garde-fous, et un vrai passage d'Aider face à un faux serveur Ollama
si EVA_TEST_AIDER pointe vers un venv où Aider est installé (sinon ce test-là est ignoré)."""
import asyncio
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app import code_agent
from app.config import settings


def _lancer(ws, *a, **kw):
    return asyncio.run(code_agent.lancer(ws, *a, **kw))


def _installe(ws: Path, cible: str | None = None):
    d = code_agent.dossier(ws)
    if cible:
        d.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(cible, d)
    else:
        (d / "bin").mkdir(parents=True)
        (d / "bin" / "aider").write_text("#!/bin/sh\nexit 0\n")


def test_pas_installe(tmp_path):
    assert "pas installé" in _lancer(tmp_path, "x", "fais quelque chose")["error"]
    assert code_agent.statut(tmp_path)["installe"] is False


def test_garde_fous(tmp_path):
    _installe(tmp_path)
    (tmp_path / "projets" / "ok").mkdir(parents=True)
    assert "invalide" in _lancer(tmp_path, "../papiers", "lis tout")["error"]
    assert "introuvable" in _lancer(tmp_path, "absent", "fais quelque chose")["error"]
    assert "consigne" in _lancer(tmp_path, "ok", "x")["error"]
    assert "hors du projet" in _lancer(tmp_path, "ok", "modifie ce fichier", ["../../papiers/papiers.db"])["error"]


REPONSE = 'Voici.\n\nbonjour.py\n```python\ndef saluer(nom):\n    return f"Bonjour {nom} !"\n```\n'


class _FauxOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        corps = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/show":
            out = {"model_info": {"general.architecture": "qwen2", "qwen2.context_length": 32768}, "template": "", "parameters": "", "details": {}}
        else:
            out = {"model": corps.get("model"), "message": {"role": "assistant", "content": REPONSE}, "done": True,
                   "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 10}
        d = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)


@pytest.mark.skipif(not os.getenv("EVA_TEST_AIDER"), reason="EVA_TEST_AIDER non défini : pas d'Aider installé pour ce test")
def test_aider_modifie_et_commite(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _FauxOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "ollama_host", f"http://127.0.0.1:{srv.server_port}")
    _installe(tmp_path, os.environ["EVA_TEST_AIDER"])
    proj = tmp_path / "projets" / "salut"
    proj.mkdir(parents=True)
    (proj / "bonjour.py").write_text("def saluer(nom):\n    return 'salut'\n")
    r = _lancer(tmp_path, "salut", "Fais dire bonjour avec le nom", ["bonjour.py"], model="qwen2.5:7b")
    srv.shutdown()
    assert "error" not in r, r
    assert r["commits"] and "bonjour.py" in r["fichiers"] and 'Bonjour {nom}' in r["diff"]
    assert 'Bonjour {nom}' in (proj / "bonjour.py").read_text()
    subprocess.run(["git", "reset", "-q", "--hard", r["avant"]], cwd=proj, check=True)   # l'annulation proposée fonctionne
    assert "salut" in (proj / "bonjour.py").read_text()
