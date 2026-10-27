"""Langues d'EVA VOICE : détection, choix et téléchargement des voix (sans Piper ni réseau).

Lancement : cd eva-voice && pip install pytest && python -m pytest tests -q"""
import json
import sys
import types

import pytest

# Piper n'est pas nécessaire pour ces tests : on le remplace par un module vide.
sys.modules.setdefault("piper", types.SimpleNamespace(PiperVoice=object))

from app import config, langues  # noqa: E402
from app import tts  # noqa: E402

CATALOGUE = {
    "it_IT-paola-medium": {"language": {"family": "it", "code": "it_IT"}, "quality": "medium", "num_speakers": 1,
                           "files": {"it/it_IT/paola/medium/it_IT-paola-medium.onnx": {}, "it/it_IT/paola/medium/it_IT-paola-medium.onnx.json": {}}},
    "it_IT-riccardo-x_low": {"language": {"family": "it", "code": "it_IT"}, "quality": "x_low", "num_speakers": 1, "files": {}},
    "en_GB-alan-medium": {"language": {"family": "en", "code": "en_GB"}, "quality": "medium", "num_speakers": 1, "files": {}},
    "en_US-lessac-high": {"language": {"family": "en", "code": "en_US"}, "quality": "high", "num_speakers": 1, "files": {}},
    "en_US-lessac-medium": {"language": {"family": "en", "code": "en_US"}, "quality": "medium", "num_speakers": 1, "files": {}},
}


@pytest.fixture
def voix(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VOICES_DIR", str(tmp_path))
    monkeypatch.setattr(config, "PIPER_VOICE", "fr_FR-siwis-medium")
    monkeypatch.setattr(config, "PIPER_DOWNLOAD_WAIT", 0)
    monkeypatch.setattr(langues, "_catalogue", dict(CATALOGUE))
    for ext in (".onnx", ".onnx.json"):
        (tmp_path / f"fr_FR-siwis-medium{ext}").write_bytes(b"x")
        (tmp_path / f"fr_FR-upmc-medium{ext}").write_bytes(b"x")
    telecharges = []

    def faux_get(url, timeout):
        telecharges.append(url)
        return b"modele"
    monkeypatch.setattr(langues, "_get", faux_get)
    return tmp_path, telecharges


@pytest.mark.parametrize("texte,langue", [
    ("Bonjour, est-ce que tu peux me dire la météo de demain ?", "fr"),
    ("Ciao, come stai? Grazie per la risposta, è molto utile.", "it"),
    ("Hello, what is the weather like today and can you help me?", "en"),
    ("Hola, ¿cómo está? Muchas gracias por la ayuda, es muy útil.", "es"),
    ("Guten Tag, ich habe eine Frage und das ist nicht einfach.", "de"),
    ("Привет, как дела? Это очень интересно.", "ru"),
    ("مرحبا كيف حالك اليوم", "ar"),
    ("你好，今天天气怎么样？", "zh"),
    ("ok", "fr"),                                                      # trop court : langue par défaut
])
def test_detecter(texte, langue):
    assert langues.detecter(texte) == langue


def test_choisir_prefere_region_et_qualite(voix):
    assert langues.choisir("it") == ("it_IT-paola-medium", "it/it_IT/paola/medium/it_IT-paola-medium")
    assert langues.choisir("en")[0] == "en_US-lessac-medium"               # en_US d'abord, puis qualité moyenne
    assert langues.choisir("de")[0] == "de_DE-thorsten-medium"             # absent du catalogue : voix connue
    assert langues.choisir("xx") is None                                   # langue sans voix Piper


def test_voix_pour(voix):
    d, telecharges = voix
    assert langues.voix_pour("fr", "fr_FR-upmc-medium") == "fr_FR-upmc-medium"   # la voix choisie garde sa langue
    assert langues.voix_pour("fr", None) == "fr_FR-siwis-medium"
    assert langues.telecharger("it") == "it_IT-paola-medium"
    assert sorted(u.rsplit("/", 1)[1] for u in telecharges) == ["it_IT-paola-medium.onnx", "it_IT-paola-medium.onnx.json"]
    assert langues.voix_pour("it", "fr_FR-upmc-medium") == "it_IT-paola-medium"  # l'italien parle avec une voix italienne
    assert langues.telecharger("it") == "it_IT-paola-medium" and len(telecharges) == 2   # pas de second téléchargement
    assert langues.etat()["installees"] == ["fr", "it"]


def test_echec_de_telechargement_propre(voix, monkeypatch):
    d, _ = voix

    def ko(url, timeout):
        raise OSError("réseau coupé")
    monkeypatch.setattr(langues, "_get", ko)
    assert langues.telecharger("en") is None
    assert not list(d.glob("en_*"))                                        # aucun fichier à moitié écrit


def test_voix_imposee_par_langue(voix, monkeypatch):
    d, _ = voix
    for ext in (".onnx", ".onnx.json"):
        (d / f"it_IT-riccardo-x_low{ext}").write_bytes(b"x")
        (d / f"it_IT-paola-medium{ext}").write_bytes(b"x")
    monkeypatch.setenv("PIPER_VOICE_IT", "it_IT-riccardo-x_low")
    assert langues.voix_pour("it", None) == "it_IT-riccardo-x_low"


def test_choisir_voix_tts(voix):
    d, _ = voix
    for ext in (".onnx", ".onnx.json"):
        (d / f"it_IT-paola-medium{ext}").write_bytes(b"x")
    assert tts.choisir_voix("Ciao, come stai? Grazie mille, è perfetto.", "fr_FR-upmc-medium", None) == ("it_IT-paola-medium", "it")
    assert tts.choisir_voix("Bonjour, c'est parfait.", "fr_FR-upmc-medium", None) == ("fr_FR-upmc-medium", "fr")
    assert tts.choisir_voix("Sì.", "fr_FR-upmc-medium", "it")[1] == "it"    # phrase trop courte : la langue entendue
    assert tts.choisir_voix("Bonjour, c'est parfait et très bien.", None, "it")[1] == "fr"   # texte clair : il décide
    v, langue = tts.choisir_voix("Hello, how are you today? It is a nice day.", None, None)
    assert langue == "en" and v is None                                    # voix pas encore là : repli sur la voix par défaut


def test_catalogue_en_cache(voix, monkeypatch):
    d, _ = voix
    monkeypatch.setattr(langues, "_catalogue", None)
    monkeypatch.setattr(langues, "_get", lambda url, timeout: json.dumps(CATALOGUE).encode())
    assert "it_IT-paola-medium" in langues.catalogue() and (d / "voices.json").exists()


def test_voix_par_langue_choisie_dans_l_interface(voix, monkeypatch):
    d, telecharges = voix
    lst = langues.voix_de_langue("it")
    assert [v["id"] for v in lst] == ["it_IT-paola-medium", "it_IT-riccardo-x_low"] and not lst[0]["installee"]
    assert lst[1]["nom"] == "Riccardo" and lst[1]["qualite"] == "x_low"
    # choisie mais absente : téléchargée en fond, et en attendant une autre voix italienne (ou rien)
    lances = []
    monkeypatch.setattr(langues, "preparer_voix", lambda cle: lances.append(cle))
    monkeypatch.setattr(langues, "preparer", lambda langue: None)
    assert langues.voix_pour("it", None, preferees={"it": "it_IT-riccardo-x_low"}) is None and lances == ["it_IT-riccardo-x_low"]
    assert langues.telecharger_voix("it_IT-riccardo-x_low") == "it_IT-riccardo-x_low"
    assert telecharges[-1].endswith("it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx")
    assert langues.voix_pour("it", None, preferees={"it": "it_IT-riccardo-x_low"}) == "it_IT-riccardo-x_low"
    # le français garde sa voix choisie par langue aussi
    assert langues.voix_pour("fr", "fr_FR-siwis-medium", preferees={"fr": "fr_FR-upmc-medium"}) == "fr_FR-upmc-medium"
    assert langues.telecharger_voix("../../etc/passwd") is None
    v, lang = tts.choisir_voix("Ciao, come stai? Grazie per la risposta, è molto utile.", None, None, {"it": "it_IT-riccardo-x_low"})
    assert (v, lang) == ("it_IT-riccardo-x_low", "it")


def test_lecture_et_langue_des_phrases_courtes(voix):
    from app.lecture import preparer
    assert preparer("Il est 21 h 45, il fait 12,5 °C.") == "Il est 21 heures 45, il fait 12 virgule 5 degrés."
    assert preparer("**Paella** : 1 l de bouillon → 25 min ☀️") == "Paella: 1 litre de bouillon, 25 minutes"
    assert "pour cent" in preparer("Batterie à 80 %") and "euros" in preparer("20 €")
    # Whisper a cru entendre de l'anglais : une réponse française courte garde la voix française
    v, lang = tts.choisir_voix("D'accord, c'est noté.", None, "en")
    assert lang == "fr" and v.startswith("fr_")


def test_moteur_microsoft_converti_en_wav(voix, monkeypatch):
    import io
    import sys
    import types
    import wave

    import av
    import numpy as np
    from app import moteur
    # un vrai petit MP3 (bip de 0,3 s) en guise de réponse du service
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp3") as sortie:
        flux = sortie.add_stream("mp3", rate=24000)
        flux.layout = "mono"
        t = np.sin(np.linspace(0, 2 * np.pi * 440 * 0.3, 7200)).astype(np.float32).reshape(1, -1)
        trame = av.AudioFrame.from_ndarray(t, format="fltp", layout="mono")
        trame.sample_rate = 24000
        for p in flux.encode(trame):
            sortie.mux(p)
        for p in flux.encode(None):
            sortie.mux(p)
    mp3 = buf.getvalue()
    vus = {}

    class Communicate:
        def __init__(self, texte, voix, rate="+0%"):
            vus.update(texte=texte, voix=voix, rate=rate)

        async def stream(self):
            yield {"type": "audio", "data": mp3}
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    assert moteur.lire()["moteur"] == "piper"
    moteur.ecrire("edge", {"fr": "fr-FR-HenriNeural"})
    wav = tts.synthesize("Il est 21 h 45.", speed=1.1)
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getnframes() > 3000
    assert vus == {"texte": "Il est 21 heures 45.", "voix": "fr-FR-HenriNeural", "rate": "+10%"}
    moteur.ecrire("piper")
