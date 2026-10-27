"""Navigateur d'EVA : un Chromium sans écran, dans son propre conteneur, démarré à la demande et arrêté après 10 minutes
sans usage. EVA le pilote par le protocole DevTools : ouvrir une page, la lire, cliquer, remplir un champ, faire une capture.

Garde-fous : seulement http(s) vers Internet (pas le réseau de la maison ni le NAS), jamais de champ mot de passe ni de
carte bancaire, cliquer et remplir demandent l'accord de la personne. Le navigateur ne garde aucune session entre deux
démarrages (pas de comptes connectés)."""
import asyncio
import base64
import ipaddress
import json
import logging
import os
import socket
import time
from urllib.parse import urlparse

import httpx

from . import medias

logger = logging.getLogger("eva-core.navigateur")

IMAGE = os.getenv("EVA_NAVIGATEUR_IMAGE", "chromedp/headless-shell:stable")
CONTENEUR = "eva-navigateur"
CDP_DIRECT = os.getenv("EVA_NAVIGATEUR_CDP", "")          # ex. http://127.0.0.1:9222 : Chromium déjà lancé (développement)
INACTIF_S = 600
_etat: dict = {"base": "", "page_ws": "", "dernier": 0.0}
_verrou = asyncio.Lock()


class NavigateurError(RuntimeError):
    pass


# ---------------------------------------------------------------- démarrage du conteneur

def _docker():
    import docker
    return docker.from_env()


def _demarrer_bloquant() -> str:
    cl = _docker()
    try:
        c = cl.containers.get(CONTENEUR)
        if c.status != "running":
            c.remove(force=True)
            raise LookupError
    except Exception:  # noqa: BLE001 — absent (ou arrêté) : on le crée
        reseau = None
        try:
            moi = cl.containers.get(socket.gethostname())
            reseau = next(iter(moi.attrs["NetworkSettings"]["Networks"]), None)
        except Exception:  # noqa: BLE001 — EVA hors conteneur : réseau par défaut
            pass
        try:
            cl.images.get(IMAGE)
        except Exception:  # noqa: BLE001
            logger.info("Téléchargement du navigateur (%s)…", IMAGE)
            cl.images.pull(IMAGE)
        c = cl.containers.run(IMAGE, name=CONTENEUR, detach=True, auto_remove=True, network=reseau, shm_size="512m",
                              mem_limit="1g", labels={"eva.managed": "navigateur"})
    c.reload()
    nets = c.attrs["NetworkSettings"]["Networks"]
    ip = next((n.get("IPAddress") for n in nets.values() if n.get("IPAddress")), "")
    if not ip:
        raise NavigateurError("Le navigateur a démarré sans adresse réseau.")
    return f"http://{ip}:9222"


def _arreter_bloquant() -> None:
    try:
        _docker().containers.get(CONTENEUR).stop(timeout=3)
    except Exception:  # noqa: BLE001
        pass


async def _base() -> str:
    if CDP_DIRECT:
        return CDP_DIRECT.rstrip("/")
    try:
        base = await asyncio.to_thread(_demarrer_bloquant)
    except NavigateurError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise NavigateurError(f"Impossible de démarrer le navigateur (Docker) : {exc}"[:300]) from exc
    for _ in range(40):
        try:
            async with httpx.AsyncClient(timeout=2) as cl:
                if (await cl.get(f"{base}/json/version")).status_code == 200:
                    return base
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    raise NavigateurError("Le navigateur ne répond pas.")


async def _page() -> str:
    """URL websocket de l'onglet d'EVA (créé au besoin)."""
    if _etat["page_ws"]:
        try:
            async with httpx.AsyncClient(timeout=3) as cl:
                cibles = (await cl.get(f"{_etat['base']}/json/list")).json()
            if any(t.get("webSocketDebuggerUrl") == _etat["page_ws"] for t in cibles):
                return _etat["page_ws"]
        except (httpx.HTTPError, ValueError):
            pass
    _etat["base"] = await _base()
    async with httpx.AsyncClient(timeout=5) as cl:
        r = await cl.put(f"{_etat['base']}/json/new?about:blank")
    _etat["page_ws"] = r.json()["webSocketDebuggerUrl"]
    return _etat["page_ws"]


async def periodique() -> None:
    if time.time() - _etat.get("nettoye", 0) > 3600:
        _etat["nettoye"] = time.time()
        await asyncio.to_thread(nettoyer_captures)
    if _etat["page_ws"] and time.time() - _etat["dernier"] > INACTIF_S:
        _etat.update(page_ws="", base="")
        if not CDP_DIRECT:
            await asyncio.to_thread(_arreter_bloquant)
        logger.info("Navigateur arrêté (inutilisé depuis 10 minutes).")


# ---------------------------------------------------------------- protocole DevTools

class _Session:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def cmd(self, methode: str, params: dict | None = None, delai: float = 20) -> dict:
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": methode, "params": params or {}}))
        fin = time.monotonic() + delai
        while True:
            reste = fin - time.monotonic()
            if reste <= 0:
                raise NavigateurError(f"Le navigateur n'a pas répondu à temps ({methode}).")
            m = json.loads(await asyncio.wait_for(self.ws.recv(), reste))
            if m.get("id") == mid:
                if "error" in m:
                    raise NavigateurError(f"Navigateur : {m['error'].get('message', 'erreur')}")
                return m.get("result") or {}

    async def js(self, expr: str, delai: float = 20):
        r = await self.cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, delai)
        if r.get("exceptionDetails"):
            raise NavigateurError("Erreur dans la page : " + str(r["exceptionDetails"].get("text", ""))[:200])
        return (r.get("result") or {}).get("value")

    async def attendre_chargement(self, delai: float = 15) -> None:
        fin = time.monotonic() + delai
        await asyncio.sleep(0.3)
        while time.monotonic() < fin:
            try:
                if await self.js("document.readyState", 5) == "complete":
                    break
            except NavigateurError:
                pass
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)                      # laisse le temps aux scripts de la page


async def _avec_page(fn):
    import websockets
    async with _verrou:
        _etat["dernier"] = time.time()
        ws_url = await _page()
        try:
            async with websockets.connect(ws_url, max_size=2**25, open_timeout=10) as ws:
                return await fn(_Session(ws))
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as exc:
            _etat["page_ws"] = ""
            raise NavigateurError(f"Connexion au navigateur perdue ({type(exc).__name__}) : réessaie.") from exc
        finally:
            _etat["dernier"] = time.time()


# ---------------------------------------------------------------- garde-fous

def _prive(hote: str) -> bool:
    """L'hôte désigne-t-il le réseau local, le NAS ou la machine ? (résolution DNS comprise)"""
    h = (hote or "").strip("[]").lower()
    if not h or h == "localhost" or h.endswith((".local", ".lan", ".home", ".internal")) or "." not in h and ":" not in h:
        return True
    try:
        adresses = {i[4][0] for i in socket.getaddrinfo(h, None)}
    except OSError:
        return False                                  # introuvable : le navigateur affichera lui-même l'erreur
    for a in adresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return True
    return False


def verifier_url(url: str) -> str:
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise NavigateurError("Adresse invalide : seulement des pages web (http ou https).")
    if _prive(u.hostname):
        raise NavigateurError("Le navigateur d'EVA ne va pas sur le réseau de la maison ni sur le NAS : seulement des sites Internet.")
    return url


_INSTANTANE = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-eva-ref]').forEach((e) => e.removeAttribute('data-eva-ref'));
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=checkbox], [role=tab], [onclick], summary';
  const els = []; let n = 0;
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || n >= 80) continue;
    n += 1; e.setAttribute('data-eva-ref', String(n));
    const t = (e.innerText || e.value || e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('alt') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const o = { ref: n, type: e.tagName.toLowerCase() + (e.type ? ':' + e.type : '') };
    if (t) o.texte = t;
    if (e.placeholder) o.indice = e.placeholder.slice(0, 60);
    if (e.name) o.nom = e.name.slice(0, 40);
    if (e.tagName === 'A') o.lien = e.href.slice(0, 160);
    if (e.tagName === 'SELECT') o.choix = [...e.options].slice(0, 15).map((x) => x.text.trim()).filter(Boolean);
    if (e.type === 'checkbox' || e.type === 'radio') o.coche = e.checked;
    els.push(o);
  }
  const texte = (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n').trim();
  return { titre: document.title, url: location.href, texte: texte.slice(0, 7000), tronque: texte.length > 7000, elements: els };
})()
"""

_SENSIBLE = r"""
((e) => {
  if (!e) return 'introuvable';
  const t = (e.type || '').toLowerCase(), ac = (e.autocomplete || '').toLowerCase();
  const id = ((e.name || '') + ' ' + (e.id || '') + ' ' + (e.placeholder || '') + ' ' + (e.getAttribute('aria-label') || '')).toLowerCase();
  if (t === 'password' || ac.includes('password') || ac.startsWith('cc-') || ac.includes('one-time-code')) return 'sensible';
  if (/pass|mot.?de.?passe|mdp|cvv|cvc|cryptogramme|carte|card|iban|otp|code.?secret|pin\b/.test(id)) return 'sensible';
  return 'ok';
})(document.querySelector('[data-eva-ref="REF"]'))
"""


async def _instantane(s: _Session) -> dict:
    r = await s.js(_INSTANTANE)
    if not isinstance(r, dict):
        raise NavigateurError("Page illisible.")
    if r.get("url", "").startswith(("http://", "https://")) and _prive(urlparse(r["url"]).hostname or ""):
        await s.cmd("Page.navigate", {"url": "about:blank"})
        raise NavigateurError("La page a redirigé vers le réseau de la maison : arrêté.")
    return r


# ---------------------------------------------------------------- actions

async def ouvrir(url: str) -> dict:
    url = verifier_url(url)

    async def f(s):
        await s.cmd("Page.enable")
        r = await s.cmd("Page.navigate", {"url": url}, 30)
        if r.get("errorText"):
            raise NavigateurError(f"Page inaccessible : {r['errorText']}.")
        await s.attendre_chargement()
        return await _instantane(s)
    return await _avec_page(f)


async def lire() -> dict:
    return await _avec_page(_instantane)


def _ref(ref) -> int:
    try:
        n = int(ref)
    except (TypeError, ValueError) as exc:
        raise NavigateurError("Numéro d'élément invalide (champ « ref » de la lecture de page).") from exc
    if not 1 <= n <= 200:
        raise NavigateurError("Numéro d'élément invalide.")
    return n


async def cliquer(ref) -> dict:
    n = _ref(ref)

    async def f(s):
        ok = await s.js(f"""((e) => {{ if (!e) return false; e.scrollIntoView({{block: 'center'}}); e.click(); return true; }})(document.querySelector('[data-eva-ref="{n}"]'))""")
        if not ok:
            raise NavigateurError("Élément introuvable : relis la page (les numéros changent quand la page change).")
        await s.attendre_chargement()
        return await _instantane(s)
    return await _avec_page(f)


async def remplir(ref, texte: str, valider: bool = False) -> dict:
    n = _ref(ref)
    texte = str(texte or "")[:2000]

    async def f(s):
        verdict = await s.js(_SENSIBLE.replace("REF", str(n)))
        if verdict == "introuvable":
            raise NavigateurError("Champ introuvable : relis la page.")
        if verdict == "sensible":
            raise NavigateurError("Ce champ demande un mot de passe, un code ou une carte bancaire : EVA ne le remplit jamais. Fais-le toi-même.")
        ok = await s.js(f"""((e, v) => {{
            if (!e) return false;
            e.scrollIntoView({{block: 'center'}}); e.focus();
            if (e.tagName === 'SELECT') {{
              const o = [...e.options].find((x) => x.text.trim().toLowerCase() === v.toLowerCase() || x.value === v)
                     || [...e.options].find((x) => x.text.toLowerCase().includes(v.toLowerCase()));
              if (!o) return false; e.value = o.value;
            }} else if (e.type === 'checkbox' || e.type === 'radio') {{
              const voulu = !/^(non|false|0|décoche|decoche)$/i.test(v); if (e.checked !== voulu) e.click();
            }} else {{
              const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
              const set = Object.getOwnPropertyDescriptor(proto, 'value'); if (set && set.set) set.set.call(e, v); else e.value = v;
            }}
            e.dispatchEvent(new Event('input', {{bubbles: true}})); e.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;
          }})(document.querySelector('[data-eva-ref="{n}"]'), {json.dumps(texte)})""")
        if not ok:
            raise NavigateurError("Impossible de remplir ce champ (option introuvable ?).")
        if valider:
            await s.js(f"""((e) => {{ if (e.form && e.form.requestSubmit) e.form.requestSubmit(); else if (e.form) e.form.submit();
                else e.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}})); }})(document.querySelector('[data-eva-ref="{n}"]'))""")
            await s.attendre_chargement()
        return await _instantane(s)
    return await _avec_page(f)


async def capture(page_entiere: bool = False) -> dict:
    async def f(s):
        p = {"format": "png"}
        if page_entiere:
            m = await s.cmd("Page.getLayoutMetrics")
            taille = m.get("cssContentSize") or m.get("contentSize") or {}
            p.update(captureBeyondViewport=True, clip={"x": 0, "y": 0, "width": min(taille.get("width", 1280), 1600),
                                                       "height": min(taille.get("height", 800), 8000), "scale": 1})
        r = await s.cmd("Page.captureScreenshot", p, 30)
        titre = await s.js("document.title")
        return base64.b64decode(r["data"]), titre
    donnees, titre = await _avec_page(f)
    fichier, chemin, _max = medias.nouveau("captures", "capture.png")
    chemin.write_bytes(donnees)
    url = f"/api/public/medias/{fichier}"
    return {"ok": True, "titre": titre, "image": url, "markdown": f"![Capture : {titre}]({url})",
            "consigne": "Montre la capture à la personne en recopiant le champ markdown tel quel dans ta réponse."}


def nettoyer_captures(age_jours: int = 7) -> int:
    from pathlib import Path
    d = Path(medias._racine) / medias.DOSSIERS["captures"]
    n = 0
    limite = time.time() - age_jours * 86400
    for p in d.glob("*.png") if d.is_dir() else []:
        if p.stat().st_mtime < limite:
            p.unlink(missing_ok=True)
            n += 1
    return n
