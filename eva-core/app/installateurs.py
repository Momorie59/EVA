"""Installateurs du satellite prêts à l'emploi, pour chaque système : fichier à double-cliquer (Windows) ou commande à
coller dans le Terminal (macOS, Linux, Raspberry Pi), avec l'adresse d'EVA, le jeton et les options déjà remplis."""
import re
from pathlib import Path

DOSSIER = Path(__file__).parent / "data" / "satellite"
SYSTEMES = ("windows", "mac", "linux", "android")
OPTIONS = ("fenetre", "tableau", "ecran", "gestes", "local")
_PS = {"fenetre": "-Fenetre", "tableau": "-Tableau", "ecran": "-Ecran", "gestes": "-Gestes", "local": "-Eveil local"}


def version() -> str:
    m = re.search(r'^VERSION = "([^"]+)"', (DOSSIER / "satellite.py").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


def version_android() -> int:
    """Numéro de version de l'APK servie par EVA (0 s'il n'y en a pas)."""
    try:
        return int((DOSSIER / "android-version.txt").read_text().strip()) if (DOSSIER / "eva-satellite.apk").is_file() else 0
    except (OSError, ValueError):
        return 0


# Durées d'installation constatées (connexion ADSL/fibre ordinaire), affichées avant de lancer l'installation.
_DUREES = {
    "windows": (5, 10, "Python s'installe tout seul s'il manque (+3 min)"),
    "mac": (5, 10, "la première fois, macOS peut proposer les outils de développement (+5 à 15 min)"),
    "linux": (3, 8, "sur un Raspberry Pi 3 ou 4 compte plutôt 10 à 20 min"),
    "android": (1, 2, "téléchargement de l'appli (6 Mo) et autorisation du micro"),
}
_DUREES_OPTIONS = {"ecran": (2, 5, "lecture de l'écran"), "gestes": (5, 10, "caméra et modèle de la main"), "local": (1, 3, "mot d'éveil local"),
                   "fenetre": (0, 0, ""), "tableau": (0, 0, "")}


def duree(systeme: str, options: list[str]) -> dict:
    mini, maxi, note = _DUREES.get(systeme, (3, 10, ""))
    details = []
    if systeme != "android":
        for o in options or []:
            a, b, quoi = _DUREES_OPTIONS.get(o, (0, 0, ""))
            mini, maxi = mini + a, maxi + b
            if quoi:
                details.append(f"{quoi} +{a} à {b} min")
    return {"min": mini, "max": maxi, "texte": f"Compte environ {mini} à {maxi} minutes" + (f" ({', '.join(details)})" if details else "")
            + (f". {note[0].upper() + note[1:]}." if note else "."), "note": note}


def desinstallation(eva: str) -> dict:
    """Comment désinstaller un satellite à la main (s'il est éteint quand on le supprime dans EVA), système par système :
    fichier à télécharger (lien cliquable) et/ou commande à copier."""
    eva = eva.rstrip("/")
    base = f"{eva}/api/public/satellite"
    return {
        "windows": {"fichier": f"{base}/desinstaller-windows.cmd", "nom": "Desinstaller-EVA.cmd",
                    "aide": "Télécharge ce fichier sur le PC et double-clique dessus (ou double-clique sur desinstaller.cmd dans ton dossier eva-satellite)."},
        "mac": {"fichier": f"{base}/desinstaller-mac.sh", "nom": "desinstaller-eva.sh", "commande": f"curl -fsSk {base}/desinstaller-mac.sh | bash",
                "aide": "Colle la commande dans le Terminal du Mac."},
        "linux": {"fichier": f"{base}/desinstaller-linux.sh", "nom": "desinstaller-eva.sh", "commande": f"curl -fsSk {base}/desinstaller-linux.sh | bash",
                  "aide": "Colle la commande dans un terminal de la machine (Raspberry Pi, PC Linux)."},
        "android": {"aide": "Sur le téléphone : appui long sur l'icône EVA Satellite › Désinstaller."},
    }


def _nom_fichier(nom: str) -> str:
    propre = re.sub(r"[^A-Za-z0-9_-]+", "-", nom).strip("-")[:30] or "satellite"
    return f"Installer-EVA-{propre}"


def generer(systeme: str, eva: str, jeton: str, nom: str, options: list[str]) -> dict:
    if systeme not in SYSTEMES:
        raise ValueError("Système inconnu (windows, mac, linux ou android).")
    eva = eva.rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-\[\]:]+", eva):
        raise ValueError("Adresse d'EVA invalide.")
    if not re.fullmatch(r"evasat_[A-Za-z0-9_\-]+", jeton):
        raise ValueError("Jeton invalide.")
    opts = [o for o in OPTIONS if o in set(options or [])]
    if systeme == "windows":
        args = " ".join(_PS[o] for o in opts)
        # L'installateur PowerShell est EMBARQUÉ dans le .cmd (base64 après le marqueur) : rien à télécharger avec PowerShell,
        # dont la connexion chiffrée échoue souvent avec EVA sous Windows PowerShell 5 (« La connexion sous-jacente a été fermée »).
        import base64
        ps1 = (DOSSIER / "installer-windows.ps1").read_bytes()
        if not ps1.startswith(b"\xef\xbb\xbf"):
            ps1 = b"\xef\xbb\xbf" + ps1                         # accents corrects sous Windows PowerShell 5
        b64 = base64.b64encode(ps1).decode()
        donnees = "\r\n".join(b64[i:i + 120] for i in range(0, len(b64), 120))
        extraire = ("$c=[IO.File]::ReadAllText('%~f0'); $m='::EVA'+'PS1::'; $b=$c.Substring($c.LastIndexOf($m)+$m.Length) -replace '[^A-Za-z0-9+/=]',''; "
                    "[IO.File]::WriteAllBytes((Join-Path $env:TEMP 'eva-installer.ps1'),[Convert]::FromBase64String($b))")
        # Droits administrateur : le .cmd se relance lui-même « en tant qu'administrateur » (fenêtre d'autorisation de Windows).
        # Le profil et le compte de la personne sont notés avant, pour installer chez elle et non chez le compte administrateur.
        admin = ("net session >nul 2>&1\r\nif %errorlevel% neq 0 (\r\n"
                 "  echo Droits administrateur necessaires : Windows va demander l'autorisation...\r\n"
                 "  >\"%PUBLIC%\\eva-profil.txt\" echo %USERPROFILE%\r\n"
                 "  >\"%PUBLIC%\\eva-compte.txt\" echo %USERDOMAIN%\\%USERNAME%\r\n"
                 "  powershell -NoProfile -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"\r\n"
                 "  exit /b\r\n)\r\n"
                 "set \"EVA_PROFIL=%USERPROFILE%\"\r\nset \"EVA_COMPTE=%USERDOMAIN%\\%USERNAME%\"\r\n"
                 "if exist \"%PUBLIC%\\eva-profil.txt\" set /p EVA_PROFIL=<\"%PUBLIC%\\eva-profil.txt\"\r\n"
                 "if exist \"%PUBLIC%\\eva-compte.txt\" set /p EVA_COMPTE=<\"%PUBLIC%\\eva-compte.txt\"\r\n"
                 "del \"%PUBLIC%\\eva-profil.txt\" \"%PUBLIC%\\eva-compte.txt\" 2>nul\r\n")
        cmd = ("@echo off\r\nchcp 65001 >nul\r\ntitle Installation du satellite EVA\r\n" + admin +
               f"echo Installation du satellite EVA \"{re.sub(r'[&|<>^\"%!]', ' ', nom)}\" sur cet ordinateur (administrateur)...\r\necho.\r\n"
               "del \"%TEMP%\\eva-installer.ps1\" 2>nul\r\n"
               f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"{extraire}\"\r\n"
               "if not exist \"%TEMP%\\eva-installer.ps1\" (\r\n  echo Impossible de preparer l'installateur.\r\n  pause\r\n  exit /b 1\r\n)\r\n"
               f"powershell -NoProfile -ExecutionPolicy Bypass -File \"%TEMP%\\eva-installer.ps1\" -Eva \"{eva}\" -Jeton \"{jeton}\" "
               f"-Profil \"%EVA_PROFIL%\" -Compte \"%EVA_COMPTE%\" {args}\r\n"
               "echo.\r\npause\r\nexit /b\r\n\r\n::EVAPS1::\r\n" + donnees + "\r\n")
        commande = (f"curl.exe -fsSk --ssl-no-revoke {eva}/api/public/satellite/installer-windows.ps1 -o \"$env:TEMP\\eva-installer.ps1\"; "
                    f"powershell -NoProfile -ExecutionPolicy Bypass -File \"$env:TEMP\\eva-installer.ps1\" -Eva {eva} -Jeton {jeton} {args}").strip()
        return {"fichier": {"nom": _nom_fichier(nom) + ".cmd", "contenu": cmd}, "commande": commande,
                "aide": "Double-clique sur le fichier téléchargé. Si Windows affiche « Windows a protégé votre ordinateur » : "
                        "« Informations complémentaires » puis « Exécuter quand même ». Windows demande ensuite l'autorisation "
                        "administrateur : réponds Oui (le satellite pourra aussi agir sur les fenêtres ouvertes en administrateur). "
                        "Python est installé tout seul s'il manque."}
    if systeme == "android":
        from urllib.parse import quote
        lien = f"evasat://config?eva={quote(eva, safe='')}&jeton={quote(jeton, safe='')}"
        return {"lien": lien, "apk": f"{eva}/api/public/satellite/eva-satellite.apk", "apk_present": version_android() > 0,
                "commande": lien,
                "aide": "Sur le téléphone : 1. télécharge et installe l'appli (autorise « installer des applis inconnues » si Android le demande) ; "
                        "2. touche « Ouvrir dans l'appli » (ou scanne le QR code avec l'appareil photo) ; 3. autorise le micro. "
                        "Android 8 ou plus récent."}
    script = "installer-mac.sh" if systeme == "mac" else "installer-linux.sh"
    args = " ".join([eva, jeton, *opts])
    commande = f"curl -fsSk {eva}/api/public/satellite/{script} -o /tmp/eva-installer.sh && bash /tmp/eva-installer.sh {args}"
    fichier = "#!/bin/bash\n" + commande + "\necho\nread -r -p \"Appuie sur Entrée pour fermer.\" _\n"
    if systeme == "mac":
        return {"fichier": {"nom": _nom_fichier(nom) + ".command", "contenu": fichier}, "commande": commande,
                "aide": "Ouvre le Terminal (Cmd + Espace, tape « Terminal »), colle la commande et appuie sur Entrée. "
                        "macOS demandera ensuite l'accès au micro, et pour l'option écran « Enregistrement de l'écran » et « Accessibilité »."}
    return {"fichier": {"nom": _nom_fichier(nom).lower() + ".sh", "contenu": fichier}, "commande": commande,
            "aide": "Ouvre un terminal sur la machine (Raspberry Pi, Ubuntu, Debian…), colle la commande et appuie sur Entrée. "
                    "Ton mot de passe peut être demandé pour installer les paquets du son."}
