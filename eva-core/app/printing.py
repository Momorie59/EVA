"""Impression à distance sur imprimante réseau — protocole IPP (celui d'AirPrint / « IPP Everywhere », port 631).

EVA envoie le travail depuis le NAS vers l'imprimante : on peut donc lui demander d'imprimer de n'importe où.
Aucune dépendance : client IPP minimal + petit générateur de PDF (texte) ; les images passent en JPEG (OpenCV)."""
import asyncio
import ipaddress
import re
import socket
import struct
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .db import get_pool

CHARSET = "utf-8"
MAX_BYTES = 25 * 1024 * 1024
TEXT_EXT = {".txt", ".md", ".csv", ".log", ".py", ".js", ".json", ".yml", ".yaml", ".html", ".css", ".sql", ".sh", ".ini", ".conf", ".xml"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class PrintError(RuntimeError):
    pass


# ---------------------------------------------------------------- IPP
OP_PRINT_JOB, OP_GET_PRINTER_ATTRS = 0x0002, 0x000B
TAG_INT, TAG_BOOL, TAG_ENUM = 0x21, 0x22, 0x23


def _attr(tag: int, name: str, value) -> bytes:
    n = name.encode()
    if tag in (TAG_INT, TAG_ENUM):
        v = struct.pack(">i", int(value))
    elif tag == TAG_BOOL:
        v = b"\x01" if value else b"\x00"
    else:
        v = str(value).encode("utf-8")
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(v)) + v


def build_request(op: int, printer_uri: str, request_id: int = 1, job_name: str = "", fmt: str = "", job_attrs: dict | None = None,
                  want: list[str] | None = None, data: bytes = b"") -> bytes:
    out = struct.pack(">BBHI", 1, 1, op, request_id)
    out += b"\x01" + _attr(0x47, "attributes-charset", CHARSET) + _attr(0x48, "attributes-natural-language", "fr")
    out += _attr(0x45, "printer-uri", printer_uri) + _attr(0x42, "requesting-user-name", "eva")
    if op == OP_PRINT_JOB:
        if job_name:
            out += _attr(0x42, "job-name", job_name[:100])
        if fmt:
            out += _attr(0x49, "document-format", fmt)
    if op == OP_GET_PRINTER_ATTRS and want:
        for i, w in enumerate(want):
            out += (_attr(0x44, "requested-attributes", w) if i == 0 else struct.pack(">BH", 0x44, 0) + struct.pack(">H", len(w)) + w.encode())
    if job_attrs:
        out += b"\x02"
        for k, (tag, v) in job_attrs.items():
            out += _attr(tag, k, v)
    return out + b"\x03" + data


def parse_response(buf: bytes) -> tuple[int, dict]:
    """→ (code d'état IPP, attributs {nom: [valeurs]})."""
    if len(buf) < 8:
        raise PrintError("Réponse IPP trop courte.")
    status = struct.unpack(">H", buf[2:4])[0]
    attrs: dict = {}
    i, last = 8, None
    while i < len(buf):
        tag = buf[i]
        i += 1
        if tag == 0x03:
            break
        if tag < 0x10:          # début de groupe d'attributs
            continue
        nlen = struct.unpack(">H", buf[i:i + 2])[0]; i += 2
        name = buf[i:i + nlen].decode(errors="replace"); i += nlen
        vlen = struct.unpack(">H", buf[i:i + 2])[0]; i += 2
        raw = buf[i:i + vlen]; i += vlen
        if tag in (TAG_INT, TAG_ENUM) and vlen == 4:
            val = struct.unpack(">i", raw)[0]
        elif tag == TAG_BOOL:
            val = bool(raw[:1] != b"\x00")
        else:
            val = raw.decode("utf-8", errors="replace")
        if nlen:
            last = name
            attrs[last] = [val]
        elif last:
            attrs[last].append(val)
    return status, attrs


def _http_url(uri: str) -> tuple[str, str]:
    p = urlparse(uri.strip())
    if p.scheme not in ("ipp", "ipps", "http", "https") or not p.hostname:
        raise PrintError("Adresse d'imprimante invalide : attendu ipp://IP:631/ipp/print")
    secure = p.scheme in ("ipps", "https")
    port = p.port or (443 if secure and p.scheme == "https" else 631)
    path = p.path or "/ipp/print"
    return f"{'https' if secure else 'http'}://{p.hostname}:{port}{path}", f"{'ipps' if secure else 'ipp'}://{p.hostname}:{port}{path}"


async def _post(url: str, body: bytes) -> bytes:
    """Seul point d'accès réseau (remplaçable dans les tests)."""
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as c:   # imprimantes : certificats auto-signés
            r = await c.post(url, content=body, headers={"Content-Type": "application/ipp"})
    except httpx.HTTPError as exc:
        raise PrintError(f"Imprimante injoignable : {exc}") from exc
    if r.status_code != 200:
        raise PrintError(f"L'imprimante a répondu HTTP {r.status_code}.")
    return r.content


async def printer_info(uri: str) -> dict:
    url, puri = _http_url(uri)
    status, a = parse_response(await _post(url, build_request(OP_GET_PRINTER_ATTRS, puri, want=[
        "printer-name", "printer-make-and-model", "printer-state", "printer-state-reasons", "printer-is-accepting-jobs",
        "document-format-supported", "sides-supported"])))
    if status >= 0x0100:
        raise PrintError(f"L'imprimante refuse la demande (code IPP 0x{status:04x}).")
    state = {3: "prête", 4: "imprime", 5: "arrêtée"}.get((a.get("printer-state") or [0])[0], "inconnu")
    return {"model": (a.get("printer-make-and-model") or [""])[0], "state": state, "accepting": (a.get("printer-is-accepting-jobs") or [True])[0],
            "reasons": [r for r in a.get("printer-state-reasons", []) if r != "none"], "formats": a.get("document-format-supported", []),
            "sides": a.get("sides-supported", [])}


async def send_job(uri: str, data: bytes, mime: str, title: str, copies: int = 1, duplex: bool = False) -> dict:
    if len(data) > MAX_BYTES:
        raise PrintError("Document trop gros (25 Mo maximum).")
    info = await printer_info(uri)
    fmts = info["formats"]
    if info["state"] == "arrêtée" or info["accepting"] is False:
        raise PrintError(f"L'imprimante n'est pas disponible ({', '.join(info['reasons']) or info['state']}).")
    send_mime = mime
    if fmts and mime not in fmts:
        if "application/octet-stream" in fmts:
            send_mime = "application/octet-stream"
        else:
            raise PrintError(f"Cette imprimante n'accepte pas le format {mime} (formats : {', '.join(fmts[:6])}).")
    job_attrs = {"copies": (TAG_INT, max(1, min(int(copies), 20)))}
    if duplex and any("two-sided" in s for s in info["sides"]):
        job_attrs["sides"] = (0x44, "two-sided-long-edge")
    url, puri = _http_url(uri)
    status, a = parse_response(await _post(url, build_request(OP_PRINT_JOB, puri, request_id=2, job_name=title, fmt=send_mime, job_attrs=job_attrs, data=data)))
    if status >= 0x0100:
        raise PrintError(f"L'impression a été refusée (code IPP 0x{status:04x}).")
    return {"job_id": (a.get("job-id") or [0])[0], "state": (a.get("job-state") or [None])[0], "printer_model": info["model"]}


# ---------------------------------------------------------------- documents
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_ACCENT_BASE = {c: b for b, cs in {"A": "ÀÁÂÃÄÅ", "a": "àáâãäå", "E": "ÈÉÊË", "e": "èéêë", "I": "ÌÍÎÏ", "i": "ìíîï", "O": "ÒÓÔÕÖ", "o": "òóôõö", "U": "ÙÚÛÜ", "u": "ùúûü", "C": "Ç", "c": "ç", "N": "Ñ", "n": "ñ", "Y": "Ý", "y": "ýÿ"}.items() for c in cs}
_PAGE_W, _PAGE_H, _MARGIN = 595, 842, 56


def _cp1252(ch: str) -> bytes:
    try:
        return ch.encode("cp1252")
    except UnicodeEncodeError:
        return b"?"


def _w(ch: str, size: float) -> float:
    base = _ACCENT_BASE.get(ch, ch)
    o = ord(base)
    return (_HELV[o - 32] if 32 <= o <= 126 else 556) * size / 1000


def _wrap(line: str, size: float, max_w: float) -> list[str]:
    out, cur, w = [], "", 0.0
    for word in re.split(r"(\s+)", line.expandtabs(4)):
        ww = sum(_w(c, size) for c in word)
        if cur and w + ww > max_w and not word.isspace():
            out.append(cur.rstrip()); cur, w = "", 0.0
        while ww > max_w:       # mot plus large qu'une ligne : coupé
            k, acc = 0, 0.0
            while k < len(word) and acc + _w(word[k], size) <= max_w:
                acc += _w(word[k], size); k += 1
            out.append(word[:k]); word, ww = word[k:], sum(_w(c, size) for c in word[k:])
        cur += word; w += ww
    out.append(cur.rstrip())
    return out


def text_to_pdf(text: str, title: str = "") -> bytes:
    """PDF A4 (Helvetica 11 pt) : titre, retour à la ligne automatique, pagination. « # » = intertitre, « - » = puce."""
    lines: list[tuple[str, float, bool]] = []     # (texte, taille, gras)
    if title:
        lines += [(l, 16, True) for l in _wrap(title, 16, _PAGE_W - 2 * _MARGIN)] + [("", 11, False)]
    for raw in (text or "").replace("\r", "").split("\n"):
        size, bold, line = 11.0, False, raw
        m = re.match(r"^(#{1,3})\s+(.*)", raw)
        if m:
            size, bold, line = {1: 15.0, 2: 13.0, 3: 12.0}[len(m.group(1))], True, m.group(2)
        elif re.match(r"^\s*[-*]\s+", raw):
            line = "\u2022 " + re.sub(r"^\s*[-*]\s+", "", raw)
        lines += [(l, size, bold) for l in _wrap(line, size, _PAGE_W - 2 * _MARGIN)]
    pages, cur, y = [], [], _PAGE_H - _MARGIN
    for txt, size, bold in lines:
        lead = size * 1.35
        if y - lead < _MARGIN:
            pages.append(cur); cur, y = [], _PAGE_H - _MARGIN
        y -= lead
        cur.append((y, txt, size, bold))
    pages.append(cur)
    objs: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                         b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for pg in pages:
        body = b"BT\n"
        for y, txt, size, bold in pg:
            esc = b"".join(_cp1252(c) for c in txt).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            body += f"/{'F2' if bold else 'F1'} {size} Tf 1 0 0 1 {_MARGIN} {y:.1f} Tm (".encode() + esc + b") Tj\n"
        body += b"ET"
        objs.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        cid = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] /Contents {cid} 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>".encode())
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    out, offs = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{n} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()


def image_to_jpeg(data: bytes) -> bytes:
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PrintError("Image illisible.")
    h, w = img.shape[:2]
    if max(h, w) > 3600:
        s = 3600 / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise PrintError("Conversion de l'image impossible.")
    return buf.tobytes()


def file_to_document(path: Path) -> tuple[bytes, str, str]:
    """Fichier du workspace → (octets, type MIME imprimable, titre)."""
    ext = path.suffix.lower()
    if path.stat().st_size > MAX_BYTES:
        raise PrintError("Fichier trop gros (25 Mo maximum).")
    raw = path.read_bytes()
    if ext == ".pdf":
        return raw, "application/pdf", path.name
    if ext in (".jpg", ".jpeg"):
        return raw, "image/jpeg", path.name
    if ext in IMAGE_EXT:
        return image_to_jpeg(raw), "image/jpeg", path.name
    if ext in TEXT_EXT or not ext:
        return text_to_pdf(raw.decode("utf-8", errors="replace"), path.name), "application/pdf", path.name
    raise PrintError(f"Format {ext or 'inconnu'} non imprimable directement (PDF, images et fichiers texte uniquement) : convertis-le d'abord en PDF.")


# ---------------------------------------------------------------- imprimantes enregistrées
async def list_printers() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT id, name, uri, is_default FROM printers ORDER BY is_default DESC, id")
    return [dict(r) for r in rows]


async def add_printer(name: str, uri: str, make_default: bool = False) -> dict:
    name = " ".join((name or "").split())[:60]
    if not name:
        raise PrintError("Donne un nom à l'imprimante.")
    _http_url(uri)
    async with get_pool().acquire() as conn:
        first = not await conn.fetchval("SELECT 1 FROM printers LIMIT 1")
        if make_default or first:
            await conn.execute("UPDATE printers SET is_default=false")
        try:
            row = await conn.fetchrow("INSERT INTO printers (name, uri, is_default) VALUES ($1,$2,$3) RETURNING id, name, uri, is_default", name, uri.strip(), make_default or first)
        except Exception as exc:  # noqa: BLE001 — nom déjà pris
            raise PrintError("Une imprimante porte déjà ce nom.") from exc
    return dict(row)


async def set_default(pid: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE printers SET is_default = (id=$1)", pid)


async def delete_printer(pid: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM printers WHERE id=$1", pid)
        if not await conn.fetchval("SELECT 1 FROM printers WHERE is_default") and (nid := await conn.fetchval("SELECT id FROM printers ORDER BY id LIMIT 1")):
            await conn.execute("UPDATE printers SET is_default=true WHERE id=$1", nid)


async def pick(name: str = "") -> dict:
    ps = await list_printers()
    if not ps:
        raise PrintError("Aucune imprimante enregistrée (Maison › Imprimantes).")
    if not name:
        return ps[0]
    from .lists import norm
    q = norm(name)
    hits = [p for p in ps if q and (q == norm(p["name"]) or q in norm(p["name"]))]
    if len(hits) != 1:
        raise PrintError(f"Imprimante « {name} » introuvable ou ambiguë. Disponibles : {', '.join(p['name'] for p in ps)}.")
    return hits[0]


async def print_text(text: str, title: str = "", printer: str = "", copies: int = 1, duplex: bool = False) -> dict:
    p = await pick(printer)
    r = await send_job(p["uri"], text_to_pdf(text, title), "application/pdf", title or "EVA", copies, duplex)
    return {**r, "printer": p["name"]}


async def print_path(path: Path, printer: str = "", copies: int = 1, duplex: bool = False) -> dict:
    p = await pick(printer)
    data, mime, title = await asyncio.to_thread(file_to_document, path)
    r = await send_job(p["uri"], data, mime, title, copies, duplex)
    return {**r, "printer": p["name"], "file": title}


# ---------------------------------------------------------------- découverte
def default_cidr() -> str:
    import os
    return os.getenv("EVA_LAN_CIDR", "192.168.1.0/24")


async def scan(cidr: str = "") -> list[dict]:
    """Cherche les imprimantes IPP du réseau local (port 631 ouvert, puis question à l'imprimante)."""
    try:
        net = ipaddress.ip_network(cidr or default_cidr(), strict=False)
    except ValueError as exc:
        raise PrintError("Plage réseau invalide (ex. 192.168.1.0/24).") from exc
    hosts = [str(h) for h in net.hosts()][:1024]
    sem = asyncio.Semaphore(128)

    async def probe(ip: str):
        async with sem:
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(ip, 631), 0.6)
                w.close()
            except Exception:  # noqa: BLE001
                return None
        for path in ("/ipp/print", "/"):
            uri = f"ipp://{ip}:631{path}"
            try:
                return {"uri": uri, **await asyncio.wait_for(printer_info(uri), 6)}
            except Exception:  # noqa: BLE001
                continue
        return {"uri": f"ipp://{ip}:631/ipp/print", "model": "", "state": "inconnu"}
    return [r for r in await asyncio.gather(*(probe(h) for h in hosts)) if r]
