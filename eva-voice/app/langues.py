"""EVA multilingue : quelle langue est parlée ou écrite, et quelle voix Piper l'utiliser.

- Écoute : Whisper détecte la langue tout seul (une centaine de langues).
- Voix : Piper existe pour une quarantaine de langues. La première fois qu'EVA doit parler une langue sans voix
  installée, elle télécharge la voix depuis le catalogue officiel de Piper (Hugging Face), une fois pour toutes,
  dans le dossier des voix. Pendant le téléchargement, la voix par défaut est utilisée.
- Une langue sans voix Piper : EVA répond à l'écrit dans cette langue, et lit avec la voix par défaut."""
import json
import logging
import re
import threading
import time
import urllib.request
from pathlib import Path

from . import config

logger = logging.getLogger("eva-voice.langues")

BASE = config.PIPER_VOICES_URL.rstrip("/")
QUALITE = ["medium", "high", "low", "x_low"]
# Région préférée quand une langue a plusieurs variantes.
REGION = {"en": "en_US", "pt": "pt_BR", "es": "es_ES", "de": "de_DE", "it": "it_IT", "fr": "fr_FR", "zh": "zh_CN",
          "ar": "ar_JO", "nl": "nl_NL", "sr": "sr_RS", "sw": "sw_CD", "no": "no_NO", "ca": "ca_ES"}
# Voix connues, utilisées si le catalogue est injoignable (chemin = famille/code/nom/qualité/clé).
CONNUES = {
    "it": "it_IT-paola-medium", "en": "en_US-lessac-medium", "es": "es_ES-davefx-medium", "de": "de_DE-thorsten-medium",
    "pt": "pt_BR-faber-medium", "nl": "nl_NL-mls-medium", "ru": "ru_RU-irina-medium", "uk": "uk_UA-ukrainian_tts-medium",
    "pl": "pl_PL-gosia-medium", "ar": "ar_JO-kareem-medium", "zh": "zh_CN-huayan-medium", "tr": "tr_TR-dfki-medium",
    "ro": "ro_RO-mihai-medium", "el": "el_GR-rapunzelina-low", "sv": "sv_SE-nst-medium", "cs": "cs_CZ-jirka-medium",
    "hu": "hu_HU-anna-medium", "fi": "fi_FI-harri-medium", "da": "da_DK-talesyntese-medium", "no": "no_NO-talesyntese-medium",
    "ca": "ca_ES-upc_ona-medium", "vi": "vi_VN-vais1000-medium", "fa": "fa_IR-amir-medium", "ka": "ka_GE-natia-medium",
    "kk": "kk_KZ-issai-high", "ne": "ne_NP-google-medium", "sr": "sr_RS-serbski_institut-medium", "sk": "sk_SK-lili-medium",
    "sl": "sl_SI-artur-medium", "is": "is_IS-bui-medium", "cy": "cy_GB-gwryw_gogleddol-medium", "lb": "lb_LU-marylux-medium",
    "lv": "lv_LV-aivars-medium", "sw": "sw_CD-lanfrica-medium", "fr": "fr_FR-siwis-medium",
}
NOMS = {"fr": "français", "it": "italien", "en": "anglais", "es": "espagnol", "de": "allemand", "pt": "portugais",
        "nl": "néerlandais", "ru": "russe", "uk": "ukrainien", "pl": "polonais", "ar": "arabe", "zh": "chinois",
        "tr": "turc", "ro": "roumain", "el": "grec", "sv": "suédois", "cs": "tchèque", "hu": "hongrois", "fi": "finnois",
        "da": "danois", "no": "norvégien", "ca": "catalan", "vi": "vietnamien", "fa": "persan", "ja": "japonais",
        "ko": "coréen", "he": "hébreu", "hi": "hindi"}


# ---------------------------------------------------------------- langue d'un texte (pour choisir la voix)
_MOTS = {
    "fr": "le la les des une est et que qui pour pas dans sur avec vous je tu nous ce cette mais ou très bien c'est",
    "en": "the and is are you to of in that it for with this was have not be on your what can will",
    "it": "il lo la gli che è e di per non un una sono con questo come ciao grazie della perché anche",
    "es": "el la los las que es y de en un una por para con no se lo pero muy gracias como está",
    "de": "der die das und ist nicht ich du ein eine mit für auf zu den dem sie wir es auch",
    "pt": "o a os as que é e de em um uma não para com se do da você muito obrigado está",
    "nl": "de het een en is niet ik je van dat met voor op zijn maar ook wat",
}
_MOTS = {k: set(v.split()) for k, v in _MOTS.items()}
_ECRITURES = [("ja", r"[぀-ヿ]"), ("ko", r"[가-힯]"), ("zh", r"[一-鿿]"), ("ar", r"[؀-ۿ]"),
              ("he", r"[֐-׿]"), ("el", r"[Ͱ-Ͽ]"), ("hi", r"[ऀ-ॿ]"), ("ka", r"[Ⴀ-ჿ]")]


def detecter(texte: str, defaut: str = "fr") -> str:
    """Langue probable d'un texte (heuristique légère : écriture, puis mots courants). `defaut` si incertain."""
    t = (texte or "").lower()
    for code, motif in _ECRITURES:
        if len(re.findall(motif, t)) >= 2:
            return code
    cyr = re.findall(r"[Ѐ-ӿ]", t)
    if len(cyr) >= 3:
        return "uk" if re.search(r"[іїєґ]", t) else "ru"
    mots = re.findall(r"[a-zàâäçéèêëîïôöùûüñœæßíóúãõ']+", t)
    if len(mots) < 2:
        return defaut
    scores = {k: sum(1 for m in mots if m in v) for k, v in _MOTS.items()}
    meilleur = max(scores, key=scores.get)
    if scores[meilleur] == 0 or scores[meilleur] == scores.get(defaut, 0):
        return defaut
    return meilleur


# ---------------------------------------------------------------- voix par langue
_verrou = threading.Lock()
_en_cours: set[str] = set()
_catalogue: dict | None = None


def _dir() -> Path:
    return Path(config.VOICES_DIR)


def installees(langue: str) -> list[str]:
    out = []
    for onnx in sorted(_dir().glob(f"{langue}_*.onnx")):
        if onnx.with_name(onnx.name + ".json").exists():
            out.append(onnx.name[:-len(".onnx")])
    return out


def langue_de_voix(nom: str) -> str:
    return (nom or "").split("_", 1)[0].split("-", 1)[0].lower()


def _get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "eva-voice"}), timeout=timeout) as r:
        return r.read()


def catalogue() -> dict:
    """voices.json de Piper (mis en cache dans le dossier des voix, rafraîchi toutes les semaines)."""
    global _catalogue
    if _catalogue is not None:
        return _catalogue
    cache = _dir() / "voices.json"
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
            _catalogue = json.loads(cache.read_text())
            return _catalogue
        data = _get(f"{BASE}/voices.json", 20)
        _catalogue = json.loads(data)
        cache.write_bytes(data)
    except Exception as exc:  # noqa: BLE001 — sans catalogue, on se rabat sur les voix connues
        logger.warning("Catalogue des voix Piper indisponible : %s", exc)
        _catalogue = json.loads(cache.read_text()) if cache.exists() else {}
    return _catalogue


def _chemin(cle: str) -> str:
    code, nom, qualite = cle.split("-", 2)
    return f"{code.split('_')[0]}/{code}/{nom}/{qualite}/{cle}"


def choisir(langue: str) -> tuple[str, str] | None:
    """(clé de la voix, chemin dans le catalogue sans extension) pour une langue, ou None si Piper ne la parle pas."""
    cat = catalogue()
    candidats = []
    for cle, v in cat.items():
        lang = v.get("language", {}) if isinstance(v, dict) else {}
        if lang.get("family") != langue:
            continue
        qualite = v.get("quality", "")
        fichiers = [f for f in v.get("files", {}) if f.endswith(".onnx")]
        rang = (0 if lang.get("code") == REGION.get(langue, lang.get("code")) else 1,
                QUALITE.index(qualite) if qualite in QUALITE else 9,
                0 if v.get("num_speakers", 1) == 1 else 1, cle)
        candidats.append((rang, cle, fichiers[0][:-len(".onnx")] if fichiers else _chemin(cle)))
    if candidats:
        _r, cle, chemin = min(candidats)
        return cle, chemin
    if langue in CONNUES:
        return CONNUES[langue], _chemin(CONNUES[langue])
    return None


def voix_de_langue(langue: str) -> list[dict]:
    """Voix du catalogue Piper pour une langue (pour le choix dans l'interface)."""
    out = []
    for cle, v in catalogue().items():
        lang = v.get("language", {}) if isinstance(v, dict) else {}
        if lang.get("family") != langue:
            continue
        code, nom, qualite = (cle.split("-", 2) + ["", ""])[:3]
        out.append({"id": cle, "nom": nom.replace("_", " ").capitalize(), "region": lang.get("region") or code,
                    "qualite": qualite, "locuteurs": int(v.get("num_speakers", 1) or 1),
                    "installee": (_dir() / f"{cle}.onnx").exists() and (_dir() / f"{cle}.onnx.json").exists()})
    if not out and langue in CONNUES:
        cle = CONNUES[langue]
        out.append({"id": cle, "nom": cle.split("-")[1].capitalize(), "region": cle.split("-")[0], "qualite": cle.split("-")[2],
                    "locuteurs": 1, "installee": (_dir() / f"{cle}.onnx").exists()})
    qual = {q: i for i, q in enumerate(QUALITE)}
    return sorted(out, key=lambda x: (not x["installee"], x["region"] != REGION.get(langue, x["region"]), qual.get(x["qualite"], 9), x["nom"]))


def telecharger_voix(cle: str) -> str | None:
    """Télécharge une voix précise du catalogue (bloquant)."""
    if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)", cle or ""):
        return None
    if (_dir() / f"{cle}.onnx").exists() and (_dir() / f"{cle}.onnx.json").exists():
        return cle
    v = catalogue().get(cle) or {}
    fichiers = [f for f in v.get("files", {}) if f.endswith(".onnx")]
    chemin = fichiers[0][:-len(".onnx")] if fichiers else _chemin(cle)
    _dir().mkdir(parents=True, exist_ok=True)
    try:
        for ext in (".onnx.json", ".onnx"):
            cible = _dir() / f"{cle}{ext}"
            tmp = cible.with_suffix(cible.suffix + ".part")
            tmp.write_bytes(_get(f"{BASE}/{chemin}{ext}", 300))
            if tmp.stat().st_size == 0:
                raise OSError("fichier vide")
            tmp.replace(cible)
        logger.info("Voix « %s » installée", cle)
        return cle
    except Exception as exc:  # noqa: BLE001
        logger.warning("Téléchargement de la voix %s impossible : %s", cle, exc)
        for ext in (".onnx.json", ".onnx", ".onnx.part", ".onnx.json.part"):
            (_dir() / f"{cle}{ext}").unlink(missing_ok=True)
        return None


def preparer_voix(cle: str) -> None:
    """Téléchargement d'une voix choisie, en arrière-plan."""
    with _verrou:
        if cle in _en_cours:
            return
        _en_cours.add(cle)

    def run():
        try:
            telecharger_voix(cle)
        finally:
            with _verrou:
                _en_cours.discard(cle)
    threading.Thread(target=run, daemon=True, name=f"voix-{cle}").start()


def telecharger(langue: str) -> str | None:
    """Télécharge la voix d'une langue (bloquant). Renvoie son nom, ou None si impossible."""
    deja = installees(langue)
    if deja:
        return deja[0]
    choix = choisir(langue)
    if not choix:
        logger.info("Pas de voix Piper pour la langue « %s »", langue)
        return None
    cle, chemin = choix
    _dir().mkdir(parents=True, exist_ok=True)
    try:
        for ext in (".onnx.json", ".onnx"):
            cible = _dir() / f"{cle}{ext}"
            tmp = cible.with_suffix(cible.suffix + ".part")
            tmp.write_bytes(_get(f"{BASE}/{chemin}{ext}", 300))
            if tmp.stat().st_size == 0:
                raise OSError("fichier vide")
            tmp.replace(cible)
        logger.info("Voix « %s » installée pour le %s", cle, NOMS.get(langue, langue))
        return cle
    except Exception as exc:  # noqa: BLE001
        logger.warning("Téléchargement de la voix %s impossible : %s", cle, exc)
        for ext in (".onnx.json", ".onnx", ".onnx.part", ".onnx.json.part"):
            (_dir() / f"{cle}{ext}").unlink(missing_ok=True)
        return None


def preparer(langue: str) -> None:
    """Lance le téléchargement en arrière-plan (au moment où Whisper entend une nouvelle langue)."""
    if not config.PIPER_AUTO_DOWNLOAD or not langue or installees(langue):
        return
    with _verrou:
        if langue in _en_cours:
            return
        _en_cours.add(langue)

    def run():
        try:
            telecharger(langue)
        finally:
            with _verrou:
                _en_cours.discard(langue)
    threading.Thread(target=run, daemon=True, name=f"voix-{langue}").start()


def voix_pour(langue: str, voix_choisie: str | None, attendre: float = 0, preferees: dict | None = None) -> str | None:
    """Voix à utiliser pour parler `langue`. La voix choisie par la personne est gardée pour sa propre langue ;
    `preferees` = voix choisies langue par langue dans l'interface ({"it": "it_IT-riccardo-x_low#0", …}).
    attendre > 0 : patiente jusqu'à ce délai si la voix est en cours de téléchargement."""
    pref = str((preferees or {}).get(langue) or "")
    if pref and langue_de_voix(pref) == langue:
        modele = pref.partition("#")[0]
        if (_dir() / f"{modele}.onnx").exists() and (_dir() / f"{modele}.onnx.json").exists():
            return pref
        preparer_voix(modele)                                    # choisie mais pas encore là : on la télécharge
    if voix_choisie and langue_de_voix(voix_choisie) == langue:
        return voix_choisie
    if langue == langue_de_voix(config.PIPER_VOICE):
        return voix_choisie or config.PIPER_VOICE
    prefere = config.voix_preferee(langue)
    dispo = installees(langue)
    if prefere and prefere in dispo:
        return prefere
    if dispo:
        return dispo[0]
    preparer(langue)
    fin = time.time() + attendre
    while time.time() < fin:
        time.sleep(0.5)
        dispo = installees(langue)
        if dispo:
            return dispo[0]
    return None


def etat() -> dict:
    langues = sorted({langue_de_voix(p.name) for p in _dir().glob("*.onnx")})
    return {"installees": langues, "en_telechargement": sorted(_en_cours), "auto": config.PIPER_AUTO_DOWNLOAD}
