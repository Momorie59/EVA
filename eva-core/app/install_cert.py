"""Page publique « Installer le certificat d'EVA » : accessible avant la connexion, car c'est justement elle qui supprime l'avertissement du navigateur.
Elle ne distribue que le certificat RACINE (public par nature, comme celui de n'importe quelle autorité) : jamais la clé privée."""
import base64
import html

CSS = """
:root{color-scheme:dark light}
body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#0f1420;color:#e8ecf4;display:flex;justify-content:center;padding:24px 16px}
main{max-width:640px;width:100%}
h1{font-size:1.5rem;margin:0 0 4px} p.sub{color:#9aa6bd;margin:0 0 20px}
.card{background:#171e2e;border:1px solid #2a3550;border-radius:16px;padding:16px 18px;margin:0 0 14px}
.card h2{font-size:1.05rem;margin:0 0 8px} ol{margin:6px 0 0;padding-left:20px;line-height:1.55}
a.btn{display:inline-block;background:#5b8cff;color:#fff;text-decoration:none;font-weight:600;padding:10px 16px;border-radius:12px;margin:4px 8px 4px 0}
a.btn.alt{background:#2a3550} small{color:#9aa6bd}
@media (prefers-color-scheme:light){body{background:#f3f5fa;color:#1c2333}.card{background:#fff;border-color:#d7ddea}p.sub,small{color:#5a6785}}
"""


def page(cert_ready: bool, error: str = "") -> str:
    warn = "" if cert_ready else f'<div class="card"><strong>Le certificat n\'est pas encore prêt.</strong><br><small>{html.escape(error or "Ouvre EVA une fois en HTTPS, puis recharge cette page.")}</small></div>'
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVA — supprimer l'avertissement de sécurité</title><style>{CSS}</style></head><body><main>
<h1>Supprimer l'avertissement « connexion non privée »</h1>
<p class="sub">À faire une seule fois par appareil. Ensuite EVA s'ouvre comme n'importe quel site, avec le cadenas.</p>{warn}
<div class="card"><h2>Windows (le plus simple)</h2>
<a class="btn" href="install/installer-windows.bat" data-testid="dl-bat">Télécharger l'installateur Windows</a>
<ol><li>Ouvre le fichier téléchargé (double-clic). Si Windows prévient, clique « Informations complémentaires » puis « Exécuter quand même ».</li>
<li>Réponds <strong>Oui</strong> à la question sur le certificat.</li><li>Ferme complètement Chrome / Edge et rouvre EVA.</li></ol></div>
<div class="card"><h2>Téléphone Android</h2><a class="btn alt" href="install/eva-certificat.crt" data-testid="dl-crt">Télécharger le certificat</a>
<ol><li>Réglages › Sécurité › Plus de paramètres › Chiffrement et identifiants › Installer un certificat › Certificat d'autorité (CA).</li><li>Choisis le fichier « eva-certificat.crt » téléchargé.</li></ol></div>
<div class="card"><h2>iPhone / iPad</h2><a class="btn alt" href="install/eva-certificat.crt">Télécharger le certificat</a>
<ol><li>Autorise le téléchargement, puis Réglages › Profil téléchargé › Installer.</li><li>Réglages › Général › Informations › Réglages du certificat de confiance › active « EVA ».</li></ol></div>
<div class="card"><h2>Mac</h2><a class="btn alt" href="install/eva-certificat.crt">Télécharger le certificat</a>
<ol><li>Double-clique le fichier : il s'ouvre dans « Trousseaux d'accès ».</li><li>Double-clique « EVA » dans la liste, déplie « Se fier », choisis « Toujours faire confiance ».</li></ol></div>
<div class="card"><h2>Firefox</h2><small>Firefox a son propre magasin : Paramètres › Vie privée et sécurité › Certificats › Afficher les certificats › Autorités › Importer, puis coche « Confirmer cette AC pour identifier des sites web ».</small></div>
</main></body></html>"""


def windows_bat(pem: bytes) -> bytes:
    """Installateur Windows : réécrit le certificat, l'ajoute aux autorités de confiance de l'utilisateur (sans droits administrateur)."""
    lines = [l.strip() for l in pem.decode("ascii", "ignore").splitlines() if l.strip()]
    body = [f"echo {l}>>\"%TEMP%\\eva-certificat.b64\"" for l in lines]
    script = ["@echo off", "chcp 65001 >nul", "title EVA - installation du certificat", 'del "%TEMP%\\eva-certificat.b64" 2>nul', *body,
              'certutil -f -decode "%TEMP%\\eva-certificat.b64" "%TEMP%\\eva-certificat.crt" >nul',
              'certutil -user -addstore Root "%TEMP%\\eva-certificat.crt"',
              'del "%TEMP%\\eva-certificat.b64" "%TEMP%\\eva-certificat.crt" 2>nul',
              "echo.", "echo Termine. Ferme completement Chrome / Edge puis rouvre EVA : plus d'avertissement.", "pause"]
    return ("\r\n".join(script) + "\r\n").encode("utf-8")
