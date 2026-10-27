import ast
import asyncio
import json
import re
import time
from typing import Awaitable, Callable

from ..ollama_client import OllamaError, stream_decide
from . import guard
from .args import normalize as normalize_args
from .permissions import Permission
from .registry import ToolRegistry
from ..traces import TraceRecorder
from .. import history

MAX_TOOL_ITERATIONS = 4
PLAN_MAX_ITERATIONS = 16        # tâche suivie par un plan : plusieurs étapes, donc plus de tours d'outils

SendEvent = Callable[[dict], Awaitable[None]]
ConfirmGate = Callable[[str, dict], Awaitable[bool]]


# Les petits modèles locaux écrivent parfois l'appel d'outil en texte ({"name": "web_search", "parameters": {...}}) au lieu de
# l'émettre pour de bon : on le reconnaît, on ne l'affiche pas, et on l'exécute.
_CALL_START = re.compile(r'(```(?:json|python)?\s*)?["\']?\{\s*["\']name["\']\s*:')


# Certains modèles (qwen2.5 notamment) récitent parfois leur format d'entraînement au lieu de répondre après un outil :
# « <tool_response>…</tool_response> », « The output MUST strictly adhere to the following format… ». Jamais affiché.
_FUITE = re.compile(r"</?tool_(?:call|response)>|</?function_calls?>|The output MUST strictly|If no function call is needed|"
                    r"Please make sure the parameter type is correct|<\|im_(?:start|end)\|>", re.I)
_RELANCE = ("Réponds maintenant directement à la personne, en langage naturel et dans sa langue, à partir des résultats "
            "d'outils ci-dessus. N'écris aucun format technique (pas de balises, pas de JSON).")


def couper_fuite(text: str) -> tuple[str, bool]:
    """Texte avant une éventuelle récitation de format technique, et si une récitation a été trouvée."""
    m = _FUITE.search(text)
    return (text[:m.start()].rstrip(), True) if m else (text, False)


def _safe_end(acc: str) -> int:
    """Jusqu'où on peut déjà afficher : rien à partir d'un début possible d'appel d'outil ou de format récité."""
    fuite = _FUITE.search(acc)
    if fuite:
        acc = acc[:fuite.start()]
    lt = acc.rfind("<")
    if lt != -1 and len(acc) - lt < 18:          # « <tool_res » tout juste arrivé : on attend la suite
        acc = acc[:lt]
    tail = acc[-16:]
    for amorce in ("The output", "If no function", "Please make sure"):
        for k in range(len(amorce), 2, -1):         # début d'une phrase de format en fin de flux : on attend la suite
            if tail.endswith(amorce[:k]):
                acc = acc[:len(acc) - k]
                break
    m = _CALL_START.search(acc)
    if m:
        return m.start()
    cut = max(acc.rfind("{"), acc.rfind("```"))
    if cut != -1 and len(acc) - cut < 14:        # « { » ou « ```js » tout juste arrivé : peut-être le début d'un appel
        return cut
    return len(acc)


def _objet(text: str, start: int):
    """Lit un objet {…} à partir de `start` : JSON, ou à défaut syntaxe Python ({'name': …}, True/None). (objet, fin) ou None."""
    try:
        return json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        pass
    profondeur, guillemet = 0, ""
    for i in range(start, len(text)):
        ch = text[i]
        if guillemet:
            if ch == guillemet and text[i - 1] != "\\":
                guillemet = ""
        elif ch in "\"'":
            guillemet = ch
        elif ch == "{":
            profondeur += 1
        elif ch == "}":
            profondeur -= 1
            if profondeur == 0:
                try:
                    return ast.literal_eval(text[start:i + 1]), i + 1 - start
                except (ValueError, SyntaxError):
                    return None
    return None


def extract_text_tool_call(text: str, registry) -> tuple[list[dict], str] | None:
    """Cherche dans un texte un appel d'outil écrit à la main. Retourne ([tool_call], texte_sans_appel) ou None."""
    m = _CALL_START.search(text)
    if not m:
        return None
    start = text.index("{", m.start())
    lu = _objet(text, start)
    if lu is None:
        return None
    obj, end = lu
    name = obj.get("name") if isinstance(obj, dict) else None
    args = (obj.get("parameters") if "parameters" in obj else obj.get("arguments")) if isinstance(obj, dict) else None
    if not isinstance(name, str) or registry.get(name) is None or not isinstance(args if args is not None else {}, dict):
        return None
    tail = text[start + end:]
    tail = re.sub(r"^\s*[\"']?\s*```|^\s*[\"']", "", tail)
    return [{"function": {"name": name, "arguments": args or {}}}], (text[:m.start()] + tail).strip()


def appel_seul(text: str) -> bool:
    """Le texte n'est qu'un appel d'outil écrit à la main (rien d'autre à montrer à la personne) ?"""
    m = _CALL_START.search(text or "")
    return bool(m) and not text[:m.start()].strip(" \n\"'`")


def _tool_result_message(tool_name: str, result: dict) -> dict:
    # Format "tool" role attendu par Ollama (compatible OpenAI) : le modèle
    # relit ce message pour poursuivre son raisonnement.
    return {"role": "tool", "name": tool_name, "content": json.dumps(result, ensure_ascii=False)}


async def _run_harness_inner(
    history: list[dict],
    registry: ToolRegistry,
    send_event: SendEvent,
    confirm_gate: ConfirmGate,
    trace: TraceRecorder | None = None,
    model: str | None = None,
    tools_enabled: bool = True,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    unattended: bool = False,
) -> str | None:
    """Fait avancer `history` (en place) jusqu'à ce que le modèle produise
    une réponse finale sans appel d'outil, et retourne ce texte final.

    La réponse finale est diffusée en direct (événements "token") au fur
    et à mesure qu'Ollama la génère — plus de fausse frappe mot par mot
    après coup. Les tours intermédiaires avec appel d'outil ne produisent
    normalement pas de texte visible (le modèle émet directement les
    tool_calls), donc rien n'est affiché avant la vraie réponse finale.

    Retourne None si une erreur a été rencontrée — dans ce cas un event
    "error" a déjà été envoyé via send_event, il n'y a rien d'autre à faire.
    """

    tool_schemas = registry.schemas() if tools_enabled else None
    prefixe = ""                  # réponse déjà donnée avant une relance de vérification
    plan_touche = relance_faite = False
    tour = 0

    while tour < (max(max_iterations, PLAN_MAX_ITERATIONS) if plan_touche else max_iterations):
        tour += 1
        await send_event({"type": "state", "state": "thinking"})

        accumulated_content = ""
        sent_len = 0                      # caractères déjà diffusés (on retient tout ce qui pourrait être un appel d'outil écrit en texte)
        tool_calls = None
        started_speaking = False
        usage: dict = {}
        llm_started = time.monotonic()

        try:
            async for kind, value in stream_decide(history, tools=tool_schemas, model=model):
                if kind == "content":
                    accumulated_content += value
                    upto = _safe_end(accumulated_content) if tools_enabled else len(accumulated_content)
                    if upto > sent_len:
                        if not started_speaking:
                            await send_event({"type": "state", "state": "speaking"})
                            started_speaking = True
                        await send_event({"type": "token", "text": accumulated_content[sent_len:upto]})
                        sent_len = upto
                elif kind == "usage":
                    usage = value
                elif kind == "tool_calls":
                    tool_calls = value
        except OllamaError as exc:
            await send_event({"type": "state", "state": "error"})
            await send_event({"type": "error", "message": str(exc)})
            if trace:
                trace.llm(int((time.monotonic() - llm_started) * 1000))
            return None

        if trace:
            trace.llm(
                int((time.monotonic() - llm_started) * 1000),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

        accumulated_content, fuite = couper_fuite(accumulated_content)
        if fuite and not tool_calls:
            if len(accumulated_content.strip()) < 2:
                # Rien d'utile avant la récitation : on redemande une vraie réponse, sans outils.
                return await _repondre_sans_format(history, send_event, model, trace, started_speaking)
            if sent_len < len(accumulated_content):
                await send_event({"type": "token", "text": accumulated_content[sent_len:]})
            return accumulated_content
        if not tool_calls and tools_enabled and sent_len < len(accumulated_content):
            found = extract_text_tool_call(accumulated_content, registry)
            if found:
                tool_calls, accumulated_content = found           # appel écrit en texte : on l'exécute vraiment
                sent_len = len(accumulated_content)
            elif appel_seul(accumulated_content):
                # Appel d'outil écrit en texte mais inutilisable (outil non proposé, format abîmé) : jamais affiché tel quel,
                # on redemande une vraie réponse.
                return await _repondre_sans_format(history, send_event, model, trace, started_speaking)
            else:
                await send_event({"type": "token", "text": accumulated_content[sent_len:]})   # fausse alerte : on affiche ce qu'on retenait
                sent_len = len(accumulated_content)

        if not tool_calls:
            # Vérification avant de conclure : un plan suivi pendant ce tour ne doit pas rester à moitié fait.
            if plan_touche and not relance_faite:
                reste = await _etapes_restantes()
                if reste:
                    relance_faite = True
                    history.append({"role": "assistant", "content": accumulated_content})
                    history.append({"role": "user", "content": (
                        "[Vérification automatique avant de conclure] Ces étapes de ton plan ne sont pas cochées : "
                        + " ; ".join(reste) + ". Termine-les maintenant et coche-les avec plan_taches. Si l'une est impossible, "
                        "marque-la « abandonne » et dis clairement ce qui manque et pourquoi.")})
                    prefixe += accumulated_content.rstrip() + "\n\n"
                    await send_event({"type": "token", "text": "\n\n"})
                    continue
            # Réponse directe, déjà diffusée en direct ci-dessus.
            return prefixe + accumulated_content

        assistant_msg = {"role": "assistant", "content": accumulated_content, "tool_calls": tool_calls}
        history.append(assistant_msg)

        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            tool = registry.get(name)
            problem = None
            if tool is not None:
                args, problem = normalize_args(getattr(tool, "parameters", None) or {}, args)    # nom de paramètre approximatif, nombre entre guillemets…

            await send_event({"type": "state", "state": "acting"})
            await send_event({"type": "tool_call", "name": name, "args": args})

            tool_started = time.monotonic()

            if tool is None:
                result = {"error": f"Outil inconnu : {name}. Outils disponibles : {', '.join(sorted(registry.names())[:40])}"}
            elif problem:
                result = {"error": problem}
            else:
                effective_permission = tool.permission_for(args)
                if effective_permission == Permission.FORBIDDEN:
                    result = {"error": f"Outil interdit : {name}"}
                elif effective_permission == Permission.CONFIRM and not (unattended and tool.agent_safe):
                    await send_event({"type": "confirm_pending", "name": name})      # plus de phrase d'attente pendant la question
                    approved = await confirm_gate(name, args)
                    if not approved:
                        result = {"error": "Action refusée par l'utilisateur."}
                    else:
                        result = await _safe_execute(tool, args)
                else:
                    result = await _safe_execute(tool, args)

            result, suspected = guard.annotate(name, result)
            if suspected:
                await send_event({"type": "security", "tool": name})
            if trace:
                trace.tool(name, args, int((time.monotonic() - tool_started) * 1000), result)
            await send_event({"type": "tool_result", "name": name, "result": result})
            history.append(_tool_result_message(name, result))
            if name == "plan_taches" and isinstance(result, dict) and result.get("ok"):
                plan_touche = True

    # Trop d'itérations sans conclusion — on arrête plutôt que de boucler à l'infini.
    # Ce texte-ci vient d'EVA CORE, pas du modèle : jamais streamé, on l'envoie
    # d'un bloc pour rester cohérent avec le protocole (état "speaking" + token).
    fallback = "Je n'arrive pas à conclure cette tâche avec les outils disponibles."
    await send_event({"type": "state", "state": "speaking"})
    await send_event({"type": "token", "text": fallback})
    return fallback


async def _etapes_restantes() -> list[str]:
    from .. import plans
    from . import contexte
    try:
        return plans.restantes(await plans.lire(contexte.session.get()))
    except Exception:  # noqa: BLE001 — la vérification ne doit jamais casser la réponse
        return []


async def _repondre_sans_format(history: list[dict], send_event: SendEvent, model: str | None, trace, deja_parle: bool) -> str | None:
    """Deuxième essai après une récitation de format : le modèle doit répondre en langage naturel, sans outils."""
    texte, envoye = "", 0
    started = time.monotonic()
    try:
        async for kind, value in stream_decide(history + [{"role": "system", "content": _RELANCE}], tools=None, model=model):
            if kind != "content":
                continue
            texte += value
            propre, _ = couper_fuite(texte)
            fin = _safe_end(propre)
            if fin > envoye:
                if not deja_parle:
                    await send_event({"type": "state", "state": "speaking"})
                    deja_parle = True
                await send_event({"type": "token", "text": propre[envoye:fin]})
                envoye = fin
    except OllamaError as exc:
        await send_event({"type": "state", "state": "error"})
        await send_event({"type": "error", "message": str(exc)})
        return None
    if trace:
        trace.llm(int((time.monotonic() - started) * 1000))
    propre, _ = couper_fuite(texte)
    propre = propre.strip() or "Je n'ai pas réussi à formuler la réponse, peux-tu reposer la question ?"
    if envoye < len(propre):
        if not deja_parle:
            await send_event({"type": "state", "state": "speaking"})
        await send_event({"type": "token", "text": propre[envoye:]})
    return propre


async def _safe_execute(tool, args: dict) -> dict:
    args, problem = normalize_args(getattr(tool, "parameters", None) or {}, args)
    if problem:
        return {"error": problem}
    try:
        await asyncio.to_thread(history.before_tool, tool.name, args)
        return await tool.execute(**args)
    except TypeError as exc:
        return {"error": f"Arguments invalides pour {tool.name} : {exc}"}
    except Exception as exc:  # noqa: BLE001 — un bug d'outil ne doit pas planter le harness
        return {"error": f"Erreur inattendue dans {tool.name} : {exc}"}


async def run_harness(history_msgs: list[dict], registry: ToolRegistry, send_event: SendEvent, confirm_gate: ConfirmGate, *args, **kwargs) -> str | None:
    """Voir _run_harness_inner. Enveloppe : enregistre une version des projets modifiés par EVA pendant l'intervention."""
    token = history.begin()
    try:
        return await _run_harness_inner(history_msgs, registry, send_event, confirm_gate, *args, **kwargs)
    finally:
        request = next((m.get("content", "") for m in reversed(history_msgs) if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        touched = history.end(token)
        if touched:
            await asyncio.to_thread(history.finish, touched, request)
