"""Paraître rapide à l'oral (comme Jarvis, docs/latency.md) : ne jamais laisser de silence.

- Découpage au fil de l'eau : la réponse du modèle est coupée en phrases dès qu'elles sont complètes, pour que le satellite
  (ou l'interface) commence à parler pendant que la suite s'écrit.
- Accusé immédiat : si un outil met plus d'une seconde (recherche, météo, mails…), EVA dit tout de suite une courte phrase
  (« Je regarde la météo. »), variée et adaptée à la personnalité ; au-delà de quelques secondes, une phrase de patience.
- Si le modèle met longtemps à commencer (gros modèle chargé, carte graphique occupée), un petit « Voyons… ».
Aucune de ces phrases n'est enregistrée dans la conversation : ce ne sont que des sons d'attente."""
import asyncio
import random
import re
from typing import Awaitable, Callable

DELAI_ACCUSE_S = 0.9            # un outil plus rapide que ça ne mérite pas de phrase
DELAI_PATIENCE_S = 7.0
DELAI_REFLEXION_S = 3.5

# Fin de phrase : . ! ? … suivi d'un espace (pas « 3.5 », ni « M. Dupont », ni « etc. » en milieu de phrase)
_FIN = re.compile(r"(?<!\b[A-Z])(?<!\bM)(?<!\bMme)(?<!\betc)(?<!\bex)([.!?…]+)[\"»)]?\s+")
MIN_PHRASE = 12
SANS_ACCUSE = {"poser_question", "plan_taches", "present", "memoire_retenir", "note_add"}   # instantanés, ou une question suit


class Decoupeur:
    """Reçoit le texte morceau par morceau, rend les phrases complètes. fin() rend le reste."""

    def __init__(self):
        self.tampon = ""

    def ajouter(self, morceau: str) -> list[str]:
        self.tampon += morceau
        sorties = []
        while True:
            m = next((m for m in _FIN.finditer(self.tampon) if m.end() >= MIN_PHRASE), None)
            if not m:
                break
            phrase, self.tampon = self.tampon[:m.end()].strip(), self.tampon[m.end():]
            if phrase:
                sorties.append(phrase)
        if len(self.tampon) > 260:                       # très longue phrase sans point : on coupe à une virgule
            i = self.tampon.rfind(", ", 0, 240)
            if i > 60:
                sorties.append(self.tampon[:i + 1].strip())
                self.tampon = self.tampon[i + 2:]
        return sorties

    def fin(self) -> str:
        reste, self.tampon = self.tampon.strip(), ""
        return reste


_ATTENTE = {
    "meteo": ["Je regarde la météo.", "Je jette un œil au ciel."],
    "web": ["Je cherche.", "Je regarde ça.", "Je fais une recherche."],
    "mail": ["Je regarde tes mails.", "Je jette un œil à ta boîte."],
    "agenda": ["Je regarde l'agenda.", "Je consulte ton agenda."],
    "maison": ["Je m'en occupe.", "C'est parti.", "Tout de suite."],
    "document": ["Je prépare le document.", "Je m'y mets."],
    "image": ["Je dessine.", "Je m'y mets, ça prend quelques secondes."],
    "ecran": ["Je regarde ton écran.", "Je regarde."],
    "colis": ["Je regarde tes colis.", "Je vérifie tes livraisons."],
    "musique": ["Je lance ça.", "Tout de suite."],
    "papiers": ["Je regarde dans tes papiers."],
    "defaut": ["Un instant.", "Je m'en occupe.", "Deux secondes.", "Je regarde."],
}
_ATTENTE_MAJORDOME = {
    "meteo": ["Je consulte le ciel, un instant."], "web": ["Je me renseigne, un instant je vous prie."],
    "mail": ["Je parcours votre courrier."], "agenda": ["Je consulte votre agenda."], "maison": ["Tout de suite.", "Bien entendu."],
    "ecran": ["Je regarde votre écran."], "colis": ["Je vérifie vos livraisons."],
    "defaut": ["Un instant, je vous prie.", "Je m'en occupe.", "Bien entendu, un instant."],
}
_PATIENCE = ["Je cherche encore, deux secondes.", "Ça arrive.", "Encore un petit instant.", "Presque fini."]
_PATIENCE_MAJORDOME = ["Encore un instant, je vous prie.", "Je suis presque à vous."]
_REFLEXION = ["Voyons…", "Alors…", "Bonne question…", "Hmm, voyons voir."]
_REFLEXION_MAJORDOME = ["Voyons…", "Permettez-moi d'y réfléchir."]


def famille(outil: str) -> str:
    o = outil or ""
    for motif, f in ((r"meteo|weather", "meteo"), (r"web_|recherche|navigateur|wiki_search|docs_search", "web"), (r"gmail|mail", "mail"),
                     (r"calendar|agenda", "agenda"), (r"device|scene|hue|presence|cast|annonce|obs_", "maison"),
                     (r"document|pdf", "document"), (r"image", "image"), (r"ecran", "ecran"), (r"colis", "colis"),
                     (r"spotify|musique", "musique"), (r"papiers", "papiers")):
        if re.search(motif, o):
            return f
    return "defaut"


def phrase_attente(outil: str, personnalite: str = "", hasard: random.Random | None = None) -> str:
    r = hasard or random
    table = _ATTENTE_MAJORDOME if personnalite == "majordome" else _ATTENTE
    return r.choice(table.get(famille(outil)) or table["defaut"])


class Accuseur:
    """Observe les événements d'un tour (state, token, tool_call, tool_result, confirm_request) et fait dire, au bon moment,
    une phrase d'attente par `dire`. Jamais plus d'un accusé, d'une patience et d'une réflexion par tour."""

    def __init__(self, dire: Callable[[str], Awaitable[None]], personnalite: str = "", reflexion: bool = True):
        self.dire, self.perso, self.reflexion = dire, personnalite, reflexion
        self._minuteurs: dict[str, asyncio.Task] = {}
        self.a_parle = False                             # le modèle a commencé sa vraie réponse
        self.dit: list[str] = []
        self._fait: set[str] = set()

    def _plus_tard(self, cle: str, delai: float, texte_fn: Callable[[], str]) -> None:
        if cle in self._fait or cle in self._minuteurs:
            return

        async def attendre():
            try:
                await asyncio.sleep(delai)
                if self.a_parle or cle in self._fait:
                    return
                self._fait.add(cle)
                t = texte_fn()
                self.dit.append(t)
                await self.dire(t)
            except asyncio.CancelledError:
                pass
            finally:
                self._minuteurs.pop(cle, None)
        self._minuteurs[cle] = asyncio.create_task(attendre())

    def _annuler(self, *cles: str) -> None:
        for c in cles or list(self._minuteurs):
            t = self._minuteurs.pop(c, None)
            if t:
                t.cancel()

    async def observer(self, ev: dict) -> None:
        typ = ev.get("type")
        if typ == "state" and ev.get("state") == "thinking" and self.reflexion and not self._fait & {"accuse", "reflexion"}:
            r = _REFLEXION_MAJORDOME if self.perso == "majordome" else _REFLEXION
            self._plus_tard("reflexion", DELAI_REFLEXION_S, lambda: random.choice(r))
        elif typ == "token" and (ev.get("text") or "").strip():
            self.a_parle = True
            self._annuler()
        elif typ == "tool_call":
            self._annuler("reflexion")
            self._fait.add("reflexion")
            nom = ev.get("name", "")
            if nom in SANS_ACCUSE:
                return
            self._plus_tard("accuse", DELAI_ACCUSE_S, lambda: phrase_attente(nom, self.perso))
            p = _PATIENCE_MAJORDOME if self.perso == "majordome" else _PATIENCE
            self._plus_tard("patience", DELAI_PATIENCE_S, lambda: random.choice(p))
        elif typ == "tool_result":
            self._annuler("accuse", "patience")
        elif typ in ("confirm_pending", "confirm_request", "question_request", "error", "done"):
            self._annuler()

    def fermer(self) -> None:
        self.a_parle = True
        self._annuler()
