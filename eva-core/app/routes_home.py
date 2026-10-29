"""API de la maison : appareils, scènes, imprimantes, listes, réseau. Les routes « /admin » et « /api/net » sont réservées aux administrateurs."""
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import homeassistant as ha_mod
from . import auth as auth_mod
from . import devices, lan_discovery, lists, network, printing


class DeviceBody(BaseModel):
    name: str
    room: str = ""
    type: str = "switch"
    driver: str
    config: dict = {}
    aliases: str = ""
    confirm: bool = False


class ControlBody(BaseModel):
    action: str
    value: Any = None


class SceneBody(BaseModel):
    name: str
    actions: list[dict]


class TuyaCreds(BaseModel):
    region: str
    key: str
    secret: str
    device_id: str


class PrinterBody(BaseModel):
    name: str
    uri: str
    default: bool = False


class PrintTextBody(BaseModel):
    text: str
    title: str = ""
    printer: str = ""
    copies: int = 1


class ScanBody(BaseModel):
    cidr: str = ""
    deep: bool = False


class HostBody(BaseModel):
    name: str
    address: str
    port: int = 22
    username: str = "root"
    auth: str = "password"
    secret: str = ""
    notes: str = ""


class SshBody(BaseModel):
    host: str
    command: str
    timeout: int = 60


class HostRef(BaseModel):
    host: str


class ListBody(BaseModel):
    name: str
    prive: bool = False


async def _qui(request: Request) -> str:
    if not auth_mod.protected():
        return ""
    me = await auth_mod.identify(auth_mod.bearer(request.headers.get("authorization")))
    return (me or {}).get("user") or ""


async def _liste(request: Request, lid: int) -> str:
    qui = await _qui(request)
    if not await lists.visible(lid, qui):
        raise HTTPException(status_code=404, detail="Liste introuvable.")
    return qui


class ItemsBody(BaseModel):
    items: list[str]


class ItemPatch(BaseModel):
    text: str | None = None
    done: bool | None = None


class ListPrint(BaseModel):
    printer: str = ""
    include_done: bool = False
    recto_verso: bool = False
    copies: int = 1
    par_rayon: bool | None = None


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def make_router() -> APIRouter:
    r = APIRouter(prefix="/api")

    async def dev_by_id(did: int) -> dict:
        await devices.reload()
        d = next((x for x in devices._cache if x["id"] == did), None)
        if d is None:
            raise HTTPException(status_code=404, detail="Appareil introuvable.")
        return d

    # ---------------- appareils
    @r.get("/home/devices")
    async def list_devices():
        await devices.reload()
        return {"devices": [devices.public(d) for d in devices._cache], "scenes": await devices.list_scenes(),
                "types": devices.TYPES, "drivers": list(devices.DRIVERS)}

    # ---------------- présence (téléphones sur le wifi)
    @r.get("/home/presence")
    async def presence_etat():
        from . import presence
        return await presence.etat()

    @r.get("/home/admin/presence")
    async def presence_reglages():
        from . import presence
        e = await presence.etat()
        r = await presence.reglages()
        return {"reglages": r["personnes"], "automatismes": r["automatismes"], "etat": e["personnes"], "erreur": e["erreur"],
                "appareils": presence.appareils_vus(), "scenes": [{"id": x["id"], "nom": x["name"]} for x in await devices.list_scenes()],
                "dernier_automatisme": presence._etat.get("dernier_automatisme")}

    @r.put("/home/admin/presence")
    async def presence_enregistrer(body: dict):
        from . import presence
        try:
            return await presence.enregistrer((body or {}).get("personnes", {}), (body or {}).get("automatismes"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/home/admin/presence/scan")
    async def presence_scan():
        from . import presence
        await presence.scanner()
        e = await presence.etat()
        return {"appareils": presence.appareils_vus(), "etat": e["personnes"], "erreur": e["erreur"]}

    # ---------------- Présence pièce par pièce (ESP32 + ESPresense, MQTT)
    @r.get("/home/admin/espresense")
    async def espresense_etat():
        from . import espresense
        c = await espresense.reglages()
        return {"reglages": {**c, "mot_de_passe": "•••" if c["mot_de_passe"] else ""}, "etat": espresense.etat(),
                "appareils": espresense.appareils_vus(), "pieces": await espresense.pieces_famille()}

    @r.put("/home/admin/espresense")
    async def espresense_regler(body: dict):
        from . import espresense
        b = dict(body or {})
        if b.get("mot_de_passe") == "•••":
            b.pop("mot_de_passe")
        await espresense.regler(b)
        return await espresense_etat()

    # ---------------- Philips Hue en direct (pont local)
    @r.get("/home/admin/hue")
    async def hue_ponts():
        from . import hue
        return {"ponts": [{"ip": p["ip"], "nom": p["nom"]} for p in (await hue.ponts()).values()]}

    @r.post("/home/admin/hue/appairer")
    async def hue_appairer(body: dict):
        from . import hue
        try:
            return await hue.appairer(str((body or {}).get("ip", "")))
        except hue.HueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.get("/home/admin/hue/{ip}/lampes")
    async def hue_lampes(ip: str):
        from . import hue
        try:
            ls = await hue.lampes(ip)
        except hue.HueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await devices.reload()
        deja = {str(d["config"].get("light")) for d in devices._cache if d["driver"] == "hue" and d["config"].get("ip") == ip}
        return {"lampes": [{**l, "deja": l["id"] in deja} for l in ls]}

    @r.post("/home/admin/hue/{ip}/importer")
    async def hue_importer(ip: str, body: dict):
        from . import hue
        try:
            ls = {l["id"]: l for l in await hue.lampes(ip)}
        except hue.HueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await devices.reload()
        deja = {str(d["config"].get("light")) for d in devices._cache if d["driver"] == "hue" and d["config"].get("ip") == ip}
        ajoutees = []
        for lid in [str(x) for x in (body or {}).get("ids", [])][:60]:
            if lid in ls and lid not in deja:
                d = await devices.save(None, ls[lid]["nom"][:60], str((body or {}).get("piece", "")), "light", "hue", {"ip": ip, "light": lid})
                ajoutees.append(d["name"] if isinstance(d, dict) and "name" in d else ls[lid]["nom"])
        return {"ajoutees": ajoutees}

    @r.delete("/home/admin/hue/{ip}")
    async def hue_oublier(ip: str):
        from . import hue
        await hue.oublier(ip)
        return {"ok": True}

    @r.get("/home/hue/scenes")
    async def hue_scenes():
        from . import hue
        out = []
        for ip in await hue.ponts():
            try:
                out += [{**sc, "ip": ip} for sc in await hue.scenes(ip)]
            except hue.HueError:
                continue
        return {"scenes": out}

    @r.post("/home/hue/scenes/{ip}/{groupe}/{scene_id}")
    async def hue_lancer(ip: str, groupe: str, scene_id: str):
        from . import hue
        try:
            return await hue.lancer_scene(ip, scene_id, groupe)
        except hue.HueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/home/admin/ha/candidates")
    async def ha_candidates():
        try:
            c = await ha_mod.import_candidates()
        except ha_mod.HAError as exc:
            raise _bad(exc) from exc
        await devices.reload()
        have = {d["config"].get("entity_id") for d in devices._cache if d["driver"] == "ha"}
        for e in c["entities"]:
            e["already"] = e["entity_id"] in have
        return c

    @r.post("/home/admin/ha/import")
    async def ha_import(body: dict):
        await devices.reload()
        have = {d["config"].get("entity_id") for d in devices._cache if d["driver"] == "ha"}
        added, skipped = [], []
        for e in list(body.get("items") or [])[:200]:
            eid = str(e.get("entity_id", ""))
            if eid in have:
                skipped.append({"entity_id": eid, "reason": "déjà ajouté"}); continue
            if eid.split(".")[0] not in ha_mod.IMPORT_DOMAINS:
                skipped.append({"entity_id": eid, "reason": "type non pris en charge"}); continue
            try:
                nm = " ".join(str(e.get("name") or eid).split())[:60]
                dtype = ha_mod.IMPORT_DOMAINS[eid.split(".")[0]]
                try:
                    dv = await devices.save(None, nm, str(e.get("room") or ""), dtype, "ha", {"entity_id": eid}, "", dtype in devices.CONFIRM_TYPES)
                except devices.DeviceError as exc:
                    if "porte déjà ce nom" not in str(exc):
                        raise
                    dv = await devices.save(None, f"{nm} ({eid.split('.')[0]})", str(e.get("room") or ""), dtype, "ha", {"entity_id": eid}, "", dtype in devices.CONFIRM_TYPES)
                have.add(eid); added.append(dv["name"])
            except devices.DeviceError as exc:
                skipped.append({"entity_id": eid, "reason": str(exc)})
        return {"added": added, "skipped": skipped}

    @r.post("/home/admin/devices/test")
    async def test_device(body: dict):
        """Essaie un appareil NON enregistré (réglages saisis dans le formulaire) : état, allumer, éteindre."""
        action = str(body.get("action") or "state")
        if action not in ("state", "on", "off", "toggle"):
            raise HTTPException(400, "Test limité à : état, allumer, éteindre, basculer.")
        cfg = dict(body.get("config") or {})
        try:
            if cfg.get("ip"):
                await network.resolve_host(str(cfg["ip"]))        # réseau privé uniquement
            if body.get("driver") not in devices.DRIVERS:
                raise devices.DeviceError("Choisis un pilote.")
            return await devices.run({"id": 0, "name": "test", "type": body.get("type") or "switch", "driver": body["driver"], "config": cfg, "room": ""}, action, None)
        except (devices.DeviceError, network.NetError) as exc:
            raise _bad(exc) from exc

    @r.post("/home/devices/{did}/control")
    async def control(did: int, body: ControlBody):
        d = await dev_by_id(did)
        try:
            return await devices.run(d, body.action, body.value)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.post("/home/admin/devices")
    async def add_device(body: DeviceBody):
        try:
            return await devices.save(None, body.name, body.room, body.type, body.driver, body.config, body.aliases, body.confirm)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.put("/home/admin/devices/{did}")
    async def edit_device(did: int, body: DeviceBody):
        try:
            return await devices.save(did, body.name, body.room, body.type, body.driver, body.config, body.aliases, body.confirm)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.delete("/home/admin/devices/{did}")
    async def del_device(did: int):
        await devices.delete(did)
        return {"ok": True}

    @r.get("/home/tuya")
    async def tuya_status():
        return await devices.tuya_status()

    @r.post("/home/admin/tuya/creds")
    async def tuya_creds(body: TuyaCreds):
        try:
            await devices.tuya_save_creds(body.region, body.key, body.secret, body.device_id)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc
        return {"ok": True}

    @r.post("/home/admin/tuya/devices")
    async def tuya_devices():
        try:
            await devices.reload()
            return {"devices": [{**d, "local_key": devices.MASK if d["local_key"] else "", "_type": devices.tuya_type(d["category"])} for d in await devices.tuya_cloud_devices()]}
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.post("/home/admin/tuya/import")
    async def tuya_import(body: dict):
        """Importe des appareils Tuya du cloud : la clé locale est lue côté serveur, jamais renvoyée au navigateur."""
        wanted = set(body.get("ids") or [])
        room = str(body.get("room") or "")
        try:
            await devices.reload()
            added = []
            for x in await devices.tuya_cloud_devices():
                if x["device_id"] in wanted and not x["already"]:
                    cfg = {"device_id": x["device_id"], "local_key": x["local_key"], "ip": x["ip"], "version": x["version"] or "3.3", "mac": x.get("mac", "")}
                    try:
                        added.append(await devices.save(None, x["name"] or x["device_id"], room, devices.tuya_type(x["category"]), "tuya", cfg))
                    except devices.DeviceError:
                        cfg["ip"] = ""          # sans clé locale exploitable : mode cloud
                        added.append(await devices.save(None, x["name"] or x["device_id"], room, devices.tuya_type(x["category"]), "tuya", {**cfg, "local_key": ""}))
            return {"added": added}
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    # ---------------- scènes
    @r.post("/home/scenes/{sid}/run")
    async def run_scene(sid: int):
        await devices.reload()
        s = next((x for x in await devices.list_scenes() if x["id"] == sid), None)
        if not s:
            raise HTTPException(status_code=404, detail="Scène introuvable.")
        return await devices.run_scene(s)

    @r.post("/home/admin/scenes")
    async def add_scene(body: SceneBody):
        try:
            return await devices.save_scene(None, body.name, body.actions)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.put("/home/admin/scenes/{sid}")
    async def edit_scene(sid: int, body: SceneBody):
        try:
            return await devices.save_scene(sid, body.name, body.actions)
        except devices.DeviceError as exc:
            raise _bad(exc) from exc

    @r.delete("/home/admin/scenes/{sid}")
    async def del_scene(sid: int):
        await devices.delete_scene(sid)
        return {"ok": True}

    # ---------------- imprimantes
    @r.get("/print/printers")
    async def printers():
        return {"printers": await printing.list_printers(), "cidr": printing.default_cidr()}

    @r.get("/print/printers/{pid}/info")
    async def printer_info(pid: int):
        p = next((x for x in await printing.list_printers() if x["id"] == pid), None)
        if not p:
            raise HTTPException(status_code=404, detail="Imprimante introuvable.")
        try:
            return await printing.printer_info(p["uri"])
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    @r.post("/print/admin/printers")
    async def add_printer(body: PrinterBody):
        try:
            info = await printing.printer_info(body.uri)         # on vérifie que l'imprimante répond avant d'enregistrer
            return {**await printing.add_printer(body.name, body.uri, body.default), "info": info}
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    @r.post("/print/admin/printers/{pid}/default")
    async def printer_default(pid: int):
        await printing.set_default(pid)
        return {"ok": True}

    @r.delete("/print/admin/printers/{pid}")
    async def del_printer(pid: int):
        await printing.delete_printer(pid)
        return {"ok": True}

    @r.post("/print/admin/scan")
    async def scan_printers(body: ScanBody):
        try:
            return {"found": await printing.scan(body.cidr)}
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    @r.post("/print/text")
    async def print_text(body: PrintTextBody):
        try:
            return await printing.print_text(body.text, body.title, body.printer, body.copies)
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    @r.post("/print/printers/{pid}/test")
    async def print_test(pid: int):
        p = next((x for x in await printing.list_printers() if x["id"] == pid), None)
        if not p:
            raise HTTPException(status_code=404, detail="Imprimante introuvable.")
        try:
            return await printing.print_text("EVA sait imprimer.\n\nSi tu lis ce papier, l'imprimante est bien reliée à EVA.", "Page de test EVA", p["name"])
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    # ---------------- routines de la maison (heure ou capteur → scène, appareil, annonce, message)
    @r.get("/home/routines")
    async def routines_liste():
        from . import routines
        return {"routines": [{**x, "description": routines.decrire(x)} for x in await routines.lister()], "jours": routines.JOURS}

    @r.post("/home/routines")
    async def routines_creer(body: dict, request: Request):
        from . import routines
        try:
            return await routines.creer(body or {}, await _qui(request))
        except routines.RoutineError as exc:
            raise _bad(exc) from exc

    @r.patch("/home/routines/{rid}")
    async def routines_modifier(rid: str, body: dict):
        from . import routines
        try:
            return await routines.modifier(rid, body or {})
        except routines.RoutineError as exc:
            raise _bad(exc) from exc

    @r.delete("/home/routines/{rid}")
    async def routines_supprimer(rid: str):
        from . import routines
        return {"ok": await routines.supprimer(rid)}

    @r.post("/home/routines/{rid}/lancer")
    async def routines_lancer(rid: str):
        from . import routines
        x = next((y for y in await routines.lister() if y["id"] == rid), None)
        if not x:
            raise HTTPException(status_code=404, detail="Routine introuvable.")
        return {"fait": await routines.executer(x, "essai")}

    # ---------------- listes (celles de la famille + mes listes privées)
    @r.get("/lists")
    async def all_lists(request: Request):
        return {"lists": await lists.all_lists(await _qui(request))}

    @r.post("/lists")
    async def create_list(body: ListBody, request: Request):
        try:
            return await lists.create_list(body.name, body.prive, await _qui(request))
        except ValueError as exc:
            raise _bad(exc) from exc

    @r.get("/lists/{lid}")
    async def get_list(lid: int, request: Request):
        l = next((x for x in await lists.all_lists(await _qui(request)) if x["id"] == lid), None)
        if not l:
            raise HTTPException(status_code=404, detail="Liste introuvable.")
        return {**l, "items": await lists.items(lid)}

    @r.delete("/lists/{lid}")
    async def del_list(lid: int, request: Request):
        await _liste(request, lid)
        try:
            return {"ok": await lists.delete_list(lid)}
        except ValueError as exc:
            raise _bad(exc) from exc

    @r.post("/lists/{lid}/items")
    async def add_items(lid: int, body: ItemsBody, request: Request):
        qui = await _liste(request, lid)
        try:
            return await lists.add(lid, body.items, by=qui or "web")
        except ValueError as exc:
            raise _bad(exc) from exc

    @r.patch("/lists/{lid}/items/{iid}")
    async def patch_item(lid: int, iid: int, body: ItemPatch, request: Request):
        await _liste(request, lid)
        try:
            if not await lists.item_update(iid, body.text, body.done, lid):
                raise HTTPException(status_code=404, detail="Élément introuvable.")
        except ValueError as exc:
            raise _bad(exc) from exc
        return {"ok": True}

    @r.delete("/lists/{lid}/items/{iid}")
    async def del_item(lid: int, iid: int, request: Request):
        await _liste(request, lid)
        return {"ok": await lists.item_delete(iid, lid)}

    @r.post("/lists/{lid}/clear-done")
    async def clear_done(lid: int, request: Request):
        await _liste(request, lid)
        return {"removed": await lists.clear_done(lid)}

    @r.post("/lists/{lid}/print")
    async def print_list(lid: int, body: ListPrint, request: Request):
        await _liste(request, lid)
        title, text = await lists.as_text(lid, body.include_done, body.par_rayon)
        try:
            return await printing.print_text(text, title, body.printer, max(1, min(body.copies, 10)), body.recto_verso)
        except printing.PrintError as exc:
            raise _bad(exc) from exc

    @r.get("/lists/{lid}/texte")
    async def list_text(lid: int, request: Request, par_rayon: bool | None = None):
        """La liste en texte simple (à copier, partager sur le téléphone ou envoyer)."""
        await _liste(request, lid)
        title, text = await lists.as_text(lid, False, par_rayon)
        return {"titre": title, "texte": text.replace("[ ] ", "• ")}

    @r.post("/lists/{lid}/telegram")
    async def list_telegram(lid: int, request: Request):
        """Envoie la liste sur Telegram (sur le téléphone, au magasin)."""
        await _liste(request, lid)
        from . import telegram as tg
        title, text = await lists.as_text(lid, False)
        try:
            r = await tg.notify(f"🛒 {title}\n\n" + text.replace("[ ] ", "• "))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Telegram : {exc}") from exc
        if isinstance(r, dict) and r.get("error"):
            raise HTTPException(status_code=400, detail=str(r["error"]))
        return {"ok": True}

    # ---------------- réseau (administrateurs)
    @r.get("/net/overview")
    async def net_overview():
        await devices.reload()
        return {"hosts": await network.list_hosts(), "scan": await network.last_scan(), "cidr": printing.default_cidr()}

    @r.post("/net/scan")
    async def net_scan(body: ScanBody):
        try:
            return await network.scan(body.cidr or printing.default_cidr(), body.deep)
        except network.NetError as exc:
            raise _bad(exc) from exc

    # ── Détection et ajout d'appareils (lan_discovery) ──
    @r.get("/home/discovery")
    async def disc_overview():
        return await lan_discovery.overview()

    @r.post("/home/discovery/scan")
    async def disc_scan(body: dict | None = None):
        return lan_discovery.start_scan(bool((body or {}).get("quick")))

    @r.put("/home/discovery/settings")
    async def disc_settings(body: dict):
        try:
            return await lan_discovery.set_settings(bool(body.get("enabled")), int(body.get("interval_min") or 30), str(body.get("cidr") or ""))
        except (network.NetError, ValueError) as exc:
            raise _bad(exc) from exc

    @r.post("/home/discovery/test")
    async def disc_test(body: dict):
        try:
            return await lan_discovery.test(str(body.get("key") or ""), str(body.get("local_key") or ""))
        except lan_discovery.DiscoveryError as exc:
            raise _bad(exc) from exc

    @r.post("/home/discovery/add")
    async def disc_add(body: dict):
        try:
            return await lan_discovery.add(str(body.get("key") or ""), str(body.get("name") or ""), str(body.get("room") or ""), str(body.get("type") or ""),
                                           str(body.get("local_key") or ""), bool(body.get("force")))
        except (lan_discovery.DiscoveryError, devices.DeviceError) as exc:
            raise _bad(exc) from exc

    @r.post("/home/discovery/ignore")
    async def disc_ignore(body: dict):
        if body.get("reset"):
            return await lan_discovery.reset_ignored()
        return await lan_discovery.ignore(str(body.get("key") or ""), bool(body.get("undo")))

    @r.post("/home/devices/{dev_id}/repair-ip")
    async def disc_repair(dev_id: int):
        try:
            return await lan_discovery.repair_ip(dev_id)
        except lan_discovery.DiscoveryError as exc:
            raise _bad(exc) from exc

    @r.post("/net/hosts")
    async def net_add(body: HostBody):
        try:
            return await network.save_host(None, body.name, body.address, body.port, body.username, body.auth, body.secret, body.notes)
        except network.NetError as exc:
            raise _bad(exc) from exc

    @r.put("/net/hosts/{hid}")
    async def net_edit(hid: int, body: HostBody):
        try:
            return await network.save_host(hid, body.name, body.address, body.port, body.username, body.auth, body.secret, body.notes)
        except network.NetError as exc:
            raise _bad(exc) from exc

    @r.delete("/net/hosts/{hid}")
    async def net_del(hid: int):
        await network.delete_host(hid)
        return {"ok": True}

    @r.post("/net/hosts/{hid}/forget-key")
    async def net_forget(hid: int):
        await network.forget_key(hid)
        return {"ok": True}

    @r.post("/net/ssh")
    async def net_ssh(body: SshBody):
        try:
            return await network.ssh_run(body.host, body.command, body.timeout)
        except network.NetError as exc:
            raise _bad(exc) from exc

    @r.post("/net/inspect")
    async def net_inspect(body: HostRef):
        try:
            return await network.inspect(body.host)
        except network.NetError as exc:
            raise _bad(exc) from exc

    return r
