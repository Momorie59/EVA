import ipaddress
import re
import socket
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..permissions import Permission
from .base import Tool

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SEARCH_URL = "https://html.duckduckgo.com/html/"
MAX_FETCH_CHARS = 4000
MAX_REDIRECTS = 5


def _is_unsafe_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # pas une IP valide -> on refuse par prudence
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # couvre aussi 169.254.169.254 (métadonnées cloud)
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _check_url_safe(url: str) -> Optional[str]:
    """Retourne un message d'erreur si l'URL cible un hôte interne/privé
    (réseau local, loopback, métadonnées cloud...), sinon None.

    Protège web_fetch contre le SSRF : sans ça, EVA pourrait être utilisée
    pour sonder le réseau local ou un service interne à partir d'une
    requête web en apparence innocente (y compris via une redirection, ou
    un contenu malveillant renvoyé par une recherche web).

    Limite connue : vérifie l'IP au moment de l'appel, pas au moment de la
    connexion TCP réelle — une attaque DNS-rebinding (le nom résout en IP
    publique ici, puis en IP privée lors de la connexion httpx juste
    après) n'est pas couverte. Un vrai pare-feu réseau sur le conteneur
    reste la protection complète.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Seuls http:// et https:// sont autorisés."
    if not parsed.hostname:
        return "URL invalide : pas de nom d'hôte."

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        return f"Résolution DNS impossible : {exc}"

    resolved_ips = {info[4][0] for info in infos}
    if not resolved_ips:
        return "Aucune adresse IP résolue pour cet hôte."

    if any(_is_unsafe_ip(ip) for ip in resolved_ips):
        return "Cette adresse pointe vers un réseau interne/privé — refusée par sécurité."

    return None


def _extract_real_url(ddg_href: str) -> str:
    """DuckDuckGo enveloppe les liens sortants en /l/?uddg=<url encodée>."""
    parsed = urlparse(ddg_href)
    qs = parse_qs(parsed.query)
    if "uddg" in qs:
        return unquote(qs["uddg"][0])
    return ddg_href


def _bing_real_url(href: str) -> str:
    """Bing enveloppe ses liens (bing.com/ck/a?...&u=a1<base64 de l'URL>)."""
    import base64
    parsed = urlparse(href)
    if "bing.com" in (parsed.hostname or "") and parsed.path.startswith("/ck/"):
        u = parse_qs(parsed.query).get("u", [""])[0]
        if u.startswith("a1"):
            try:
                raw = u[2:] + "=" * (-len(u[2:]) % 4)
                return base64.urlsafe_b64decode(raw).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                return href
    return href


def parse_ddg_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for block in soup.select("div.result__body") or soup.select("div.result"):
        link = block.select_one("a.result__a")
        if not link or not link.get("href"):
            continue
        snippet_el = block.select_one("a.result__snippet, div.result__snippet")
        url = _extract_real_url(link["href"])
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http"):
            out.append({"title": link.get_text(strip=True), "url": url, "snippet": snippet_el.get_text(strip=True) if snippet_el else ""})
    return out


def parse_ddg_lite(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for link in soup.select("a.result-link"):
        url = _extract_real_url(link.get("href", ""))
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            continue
        row = link.find_parent("tr")
        snip = row.find_next_sibling("tr") if row else None
        sn = snip.select_one("td.result-snippet") if snip else None
        out.append({"title": link.get_text(strip=True), "url": url, "snippet": sn.get_text(" ", strip=True) if sn else ""})
    return out


def parse_bing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        url = _bing_real_url(a["href"])
        if not url.startswith("http"):
            continue
        p = li.select_one("div.b_caption p, p.b_lineclamp2, p")
        out.append({"title": a.get_text(strip=True), "url": url, "snippet": p.get_text(" ", strip=True) if p else ""})
    return out


async def _searxng(client: httpx.AsyncClient, query: str) -> list[dict]:
    import os
    base = os.getenv("EVA_SEARXNG_URL", "").strip().rstrip("/")
    if not base:
        return []
    r = await client.get(base + "/search", params={"q": query, "format": "json", "language": "fr"})
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")} for x in r.json().get("results", []) if str(x.get("url", "")).startswith("http")]


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Recherche sur le web et renvoie des résultats (titre, url, extrait). À utiliser pour toute question sur le monde "
        "(un jeu, un produit, une personne, une actualité, comment faire quelque chose). Ensuite, ouvre les meilleurs résultats avec web_fetch "
        "puis résume ou explique ce que tu as trouvé."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "La requête de recherche, en mots-clés"},
            "max_results": {"type": "integer", "description": "Nombre de résultats max (défaut 5, max 10)"},
        },
        "required": ["query"],
    }
    permission = Permission.AUTO

    async def execute(self, query: str = "", max_results: int = 5, **_: Any) -> dict:
        query = (query or "").strip()
        if not query:
            return {"error": "Requête vide : donne des mots-clés à chercher."}
        try:
            max_results = max(1, min(int(max_results), 10))
        except (TypeError, ValueError):
            max_results = 5

        # Plusieurs moteurs, l'un après l'autre : un moteur qui bloque ou change sa page ne suffit plus à casser la recherche.
        attempts: list[tuple[str, str]] = []                         # (moteur, problème)
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
            engines = [
                ("SearXNG", lambda: _searxng(client, query)),
                ("DuckDuckGo", lambda: _fetch_parse(client, "POST", SEARCH_URL, {"q": query, "kl": "fr-fr"}, parse_ddg_html)),
                ("DuckDuckGo Lite", lambda: _fetch_parse(client, "POST", "https://lite.duckduckgo.com/lite/", {"q": query, "kl": "fr-fr"}, parse_ddg_lite)),
                ("Bing", lambda: _fetch_parse(client, "GET", "https://www.bing.com/search", {"q": query, "setlang": "fr", "cc": "fr"}, parse_bing)),
            ]
            for name, run in engines:
                try:
                    results = await run()
                except httpx.HTTPError as exc:
                    attempts.append((name, f"injoignable ({type(exc).__name__})"))
                    continue
                except Exception as exc:  # noqa: BLE001 — page inattendue : on passe au moteur suivant
                    attempts.append((name, f"réponse illisible ({exc})"))
                    continue
                if results:
                    return {"query": query, "engine": name, "results": results[:max_results]}
                if name != "SearXNG":
                    attempts.append((name, "aucun résultat (page bloquée ou vide)"))
        if attempts and all("injoignable" in p for _, p in attempts):
            return {"error": "Pas d'accès à Internet depuis EVA (les moteurs de recherche sont injoignables). Vérifie la connexion du NAS ; ne réessaie pas."}
        return {"error": f"Aucun résultat pour « {query} » (essayé : " + ", ".join(f"{n} — {p}" for n, p in attempts) + "). Reformule avec d'autres mots-clés."}


async def _fetch_parse(client: httpx.AsyncClient, method: str, url: str, params: dict, parser) -> list[dict]:
    if method == "POST":
        r = await client.post(url, data=params)
    else:
        r = await client.get(url, params=params)
    r.raise_for_status()
    return parser(r.text)


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Lit le contenu texte d'une page web à partir de son URL (nettoyé du HTML/scripts)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL complète de la page (avec https://)"},
        },
        "required": ["url"],
    }
    permission = Permission.AUTO

    async def execute(self, url: str, _max: int = MAX_FETCH_CHARS, **_: Any) -> dict:
        max_chars = max(500, min(int(_max or MAX_FETCH_CHARS), 60000))       # _max : réservé aux appels internes (recherche approfondie)
        if not url.startswith(("http://", "https://")):
            return {"error": "URL invalide : doit commencer par http:// ou https://"}

        current_url = url
        resp = None

        # On suit les redirections nous-mêmes (follow_redirects=False) pour
        # revalider chaque destination — une redirection vers une IP privée
        # est le contournement SSRF le plus courant.
        async with httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": USER_AGENT}, follow_redirects=False
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                safety_error = _check_url_safe(current_url)
                if safety_error:
                    return {"error": safety_error}

                try:
                    resp = await client.get(current_url)
                except httpx.HTTPError as exc:
                    return {"error": f"Page injoignable : {exc}"}

                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return {"error": "Redirection sans destination."}
                    current_url = urljoin(current_url, location)
                    continue

                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    return {"error": f"Page injoignable : {exc}"}
                break
            else:
                return {"error": "Trop de redirections."}

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text/plain" not in content_type:
            return {"error": f"Type de contenu non pris en charge : {content_type or 'inconnu'}"}

        if "text/plain" in content_type:
            text = resp.text.strip()
            truncated = len(text) > max_chars
            return {"url": current_url, "title": "", "text": text[:max_chars], "truncated": truncated}

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        title = soup.title.get_text(strip=True) if soup.title else ""
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        truncated = len(text) > max_chars
        return {
            "url": current_url,
            "title": title,
            "text": text[:max_chars],
            "truncated": truncated,
        }
