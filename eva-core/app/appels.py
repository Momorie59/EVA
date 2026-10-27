"""Appel téléphonique où EVA converse (comme Jarvis) : « appelle Maman et demande-lui si elle vient dimanche ».

Twilio appelle le contact, EVA se présente comme assistante automatique, dit l'objet de l'appel, écoute la réponse (reconnaissance
vocale de Twilio), répond avec le modèle rapide, et ainsi de suite (8 échanges au plus). À la fin, le résumé et la transcription
arrivent dans la conversation d'origine, avec une notification.

Il faut qu'EVA soit joignable depuis Internet en HTTPS (ACCES-A-DISTANCE.md) : Twilio vient y chercher chaque réplique. Chaque
requête de Twilio est vérifiée (signature avec l'Auth Token) et l'adresse de l'appel contient un jeton aléatoire à usage unique."""
import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from xml.sax.saxutils import escape

from . import connecteurs as cx

logger = logging.getLogger("eva-core.appels")

MAX_ECHANGES = 8
DUREE_MAX_S = 10 * 60
_appels: dict[str, dict] = {}            # jeton → appel en cours


def signature_valide(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Signature Twilio : HMAC-SHA1(Auth Token, URL + paramètres POST triés « cléValeur »), en base64."""
    donnees = url + "".join(k + str(params[k]) for k in sorted(params))
    attendu = base64.b64encode(hmac.new(auth_token.encode(), donnees.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(attendu, signature or "")


def _dire(texte: str) -> str:
    return f'<Say language="fr-FR">{escape(texte)}</Say>'


def _ecouter(base: str, jeton: str) -> str:
    return (f'<Gather input="speech" language="fr-FR" speechTimeout="auto" timeout="6" action="{escape(base)}/api/public/appel/{jeton}/tour" method="POST"/>'
            + _dire("Je n'ai rien entendu. Je vous laisse, au revoir.") + "<Hangup/>")


def twiml(corps: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{corps}</Response>'


async def lancer(contact: str, objectif: str, qui: str, session: str) -> dict:
    c = await cx.config("twilio")
    if not c:
        raise cx.ConnecteurError("Les appels ne sont pas configurés (Twilio, Paramètres › Services connectés).")
    base = (c.get("adresse_publique") or "").rstrip("/")
    if not base.startswith("https://"):
        raise cx.ConnecteurError("Pour un appel où EVA converse, renseigne l'adresse publique HTTPS d'EVA dans Twilio (Services connectés) — "
                                 "voir ACCES-A-DISTANCE.md. Sinon, demande un appel avec un simple message.")
    nom, num = cx._contact(c, contact)
    objectif = re.sub(r"\s+", " ", str(objectif or "")).strip()[:500]
    if not objectif:
        raise cx.ConnecteurError("Dis ce qu'EVA doit demander ou dire pendant l'appel.")
    jeton = secrets.token_urlsafe(24)
    _appels[jeton] = {"contact": nom, "objectif": objectif, "qui": qui or "", "session": session, "debut": time.time(),
                      "echanges": [], "reponse": None, "en_cours": None, "fini": False, "base": base}
    for k in [k for k, v in _appels.items() if time.time() - v["debut"] > 3600]:
        _appels.pop(k, None)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{c['sid']}/Calls.json"
    r = await cx._http("POST", url, auth=(c["sid"], c["token"]), data={
        "To": num, "From": c["de"], "Url": f"{base}/api/public/appel/{jeton}/debut", "Method": "POST",
        "StatusCallback": f"{base}/api/public/appel/{jeton}/fin", "StatusCallbackMethod": "POST", "TimeLimit": str(DUREE_MAX_S)})
    if r.status_code >= 300:
        _appels.pop(jeton, None)
        raise cx.ConnecteurError(f"Twilio a refusé l'appel ({r.status_code}).")
    return {"ok": True, "contact": nom, "type": "conversation"}


def appel(jeton: str) -> dict | None:
    return _appels.get(jeton)


def debut(a: dict, jeton: str) -> str:
    qui = f", de la part de {a['qui']}" if a["qui"] else ""
    intro = (f"Bonjour, ici EVA, l'assistante automatique de la maison{qui}. Je ne suis pas une personne. "
             f"Je vous appelle pour ceci : {a['objectif']}")
    a["echanges"].append({"eva": intro})
    return twiml(_dire(intro) + _ecouter(a["base"], jeton))


async def _repondre(a: dict, entendu: str) -> None:
    from . import ollama_client, router as model_router
    system = (f"Tu es EVA, l'assistante automatique d'une famille, au téléphone avec « {a['contact']} » de la part de {a['qui'] or 'la famille'}. "
              f"Objectif de l'appel : {a['objectif']}. Tu parles à voix haute : une ou deux phrases courtes, polies, en français, sans liste "
              "ni emoji. Ne prétends jamais être humaine. Ne promets rien au nom de la famille, ne donne aucune information personnelle "
              "(adresse, codes, argent). Quand l'objectif est atteint, ou si la personne veut raccrocher, remercie, dis au revoir et "
              "termine ta réplique par [FIN].")
    msgs = [{"role": "system", "content": system}]
    for e in a["echanges"]:
        if "eva" in e:
            msgs.append({"role": "assistant", "content": e["eva"]})
        if "contact" in e:
            msgs.append({"role": "user", "content": e["contact"]})
    try:
        choix = await model_router.select(entendu, prefer_fast=True)
        rep = await ollama_client.chat_once(msgs, model=choix["model"])
        texte = (rep.get("content") or "").strip() or "Pardon, pouvez-vous répéter ? "
    except Exception:  # noqa: BLE001
        logger.warning("Réplique d'appel en échec", exc_info=True)
        texte = "Je rencontre un problème technique. Je transmettrai votre réponse. Au revoir. [FIN]"
    a["reponse"] = texte


async def tour(a: dict, jeton: str, entendu: str) -> str:
    entendu = (entendu or "").strip()[:500]
    a["echanges"].append({"contact": entendu or "(silence)"})
    if len([e for e in a["echanges"] if "contact" in e]) > MAX_ECHANGES:
        a["echanges"].append({"eva": "Merci pour votre temps, je transmets tout. Au revoir."})
        return twiml(_dire("Merci pour votre temps, je transmets tout. Au revoir.") + "<Hangup/>")
    a["reponse"] = None
    a["en_cours"] = asyncio.create_task(_repondre(a, entendu))
    return await attendre(a, jeton)


async def attendre(a: dict, jeton: str) -> str:
    """Twilio n'attend que 15 s une réponse : si le modèle réfléchit encore, on patiente et Twilio revient chercher la suite."""
    try:
        await asyncio.wait_for(asyncio.shield(a["en_cours"]), 8)
    except asyncio.TimeoutError:
        return twiml(f'<Pause length="2"/><Redirect method="POST">{escape(a["base"])}/api/public/appel/{jeton}/attendre</Redirect>')
    texte = a["reponse"] or ""
    fin = "[FIN]" in texte
    texte = texte.replace("[FIN]", "").strip()
    a["echanges"].append({"eva": texte})
    return twiml(_dire(texte) + ("<Hangup/>" if fin else _ecouter(a["base"], jeton)))


async def terminer(jeton: str, statut: str) -> None:
    a = _appels.pop(jeton, None)
    if not a or a["fini"]:
        return
    a["fini"] = True
    lignes = [f"- **{'EVA' if 'eva' in e else a['contact']}** : {e.get('eva') or e.get('contact')}" for e in a["echanges"]]
    if statut not in ("completed",) or not any("contact" in e for e in a["echanges"]):
        resume = {"busy": "occupé", "no-answer": "pas de réponse", "failed": "échec", "canceled": "annulé"}.get(statut, "pas de réponse")
        message = f"📞 **Appel à {a['contact']}** : {resume}."
    else:
        resume = ""
        try:
            from . import fil
            from . import ollama_client
            rep = await ollama_client.chat_once([{"role": "system", "content": "Résume en 2 phrases, en français, ce que la personne appelée a répondu, "
                                                   "par rapport à l'objectif de l'appel. Pas de préambule."},
                                                  {"role": "user", "content": f"Objectif : {a['objectif']}\n\n" + "\n".join(lignes)}],
                                                 model=await fil._modele())
            resume = (rep.get("content") or "").strip()
        except Exception:  # noqa: BLE001
            pass
        message = f"📞 **Appel à {a['contact']} terminé.** {resume}\n\n" + "\n".join(lignes)
    try:
        from .connections import connection_manager
        from .memory import save_message
        if a["session"]:
            await save_message(a["session"], "assistant", message)
            await connection_manager._deliver(a["session"], {"type": "proactive", "text": message})
        await connection_manager._hooks({"type": "proactive", "text": message.split("\n\n")[0].replace("**", "")})
    except Exception:  # noqa: BLE001
        logger.warning("Compte rendu d'appel non livré", exc_info=True)
