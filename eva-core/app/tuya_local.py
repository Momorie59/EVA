"""Tuya en réseau local : détection de la version du protocole et du bon « DP » d'interrupteur, avec un diagnostic lisible.

Pourquoi : les appareils Tuya parlent la version 3.1, 3.3, 3.4 ou 3.5, et une ampoule n'allume pas le même DP qu'une prise (20 contre 1).
Avec un mauvais réglage l'appareil ne répond pas, sans explication : on essaie donc les versions une à une et on lit les DP."""
from typing import Any

VERSIONS = ["3.3", "3.4", "3.5", "3.2", "3.1"]
LIGHT_MODES = {"white", "colour", "scene", "music"}


def infer(dps: dict) -> dict:
    """Déduit le type (light/switch) et le DP d'interrupteur à partir de l'état brut."""
    d = {str(k): v for k, v in (dps or {}).items()}
    if isinstance(d.get("20"), bool) and ("22" in d or "21" in d):                      # ampoule « v2 » : 20 allumer, 21 mode, 22 luminosité, 24 couleur
        return {"type": "light", "switch_dp": 20}
    if isinstance(d.get("1"), bool) and str(d.get("2")) in LIGHT_MODES:                  # ampoule à numérotation 1..n
        return {"type": "light", "switch_dp": 1}
    if isinstance(d.get("20"), bool):
        return {"type": "light", "switch_dp": 20}
    if isinstance(d.get("1"), bool):
        return {"type": "switch", "switch_dp": 1}
    first = next((int(k) for k, v in sorted(d.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999) if isinstance(v, bool) and k.isdigit()), None)
    return {"type": "switch", "switch_dp": first or 1}


def diagnose(errors: list[str]) -> str:
    joined = " ".join(errors).lower()
    if "914" in joined or "key" in joined:
        return "Clé locale refusée (ou version du protocole non gérée). Récupère à nouveau la clé locale dans ton compte Tuya : elle change si tu réassocies l'appareil à l'appli."
    if "901" in joined or "905" in joined or "network" in joined or "connect" in joined or "timed out" in joined:
        return ("Appareil injoignable en local : vérifie qu'il est allumé (pas coupé à l'interrupteur mural), que l'adresse IP est la bonne, et ferme l'appli "
                "Smart Life / Tuya sur les téléphones — un appareil Tuya n'accepte qu'UNE connexion locale à la fois.")
    return "Aucune réponse exploitable : vérifie l'adresse IP, la clé locale et que l'appareil est allumé."


def probe_sync(device_id: str, ip: str, key: str, hint: str = "") -> dict[str, Any]:
    import tinytuya
    versions = list(dict.fromkeys([v for v in [hint, *VERSIONS] if v]))
    errs: list[str] = []
    for v in versions:
        try:
            dev = tinytuya.Device(device_id, ip, key, version=float(v))
            dev.set_socketTimeout(3)
            dev.set_socketRetryLimit(1)
            dev.set_socketPersistent(False)
            st = dev.status() or {}
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{v}: {exc}")
            continue
        dps = st.get("dps")
        if dps:
            return {"ok": True, "version": v, "dps": dps, **infer(dps)}
        errs.append(f"{v}: {st.get('Error') or st.get('Err') or 'pas de réponse'} {st.get('Err', '')}")
        if "905" in str(st.get("Err", "")) or "901" in str(st.get("Err", "")):
            break                                           # inutile d'essayer d'autres versions si on n'arrive même pas à se connecter
    return {"ok": False, "error": diagnose(errs), "details": errs[-3:]}
