"""Prudence des outils : un outil d'action n'est proposé que si le message actuel le demande, une récitation de format
technique (<tool_response>…) n'est jamais affichée, et « je m'appelle … » est retenu sans le modèle."""
import asyncio

from app.harness import loop
from app.harness.selection import LECTURE, SubsetRegistry, est_lecture, select_tool_names
from app import memoire

TOUS = ["fs_list", "fs_read", "fs_write", "fs_append", "docs_search", "web_search", "papiers_echeances", "papiers_question",
        "papiers_a_verifier", "papiers_corriger", "papiers_marquer", "papiers_deposer", "note_create", "note_list", "note_delete",
        "device_control", "device_list", "scene_run", "list_add", "list_show", "memoire_retenir", "memoire_lister", "mcp_x_tool"]


def test_suite_d_une_demande_papiers_ne_garde_que_la_consultation():
    choisis = set(select_tool_names(["je m'appelle Paul", "que disent mes papiers ?", "quelles échéances ?"], TOUS))
    assert {"papiers_echeances", "papiers_question"} <= choisis
    assert not choisis & {"papiers_corriger", "papiers_marquer", "papiers_deposer", "fs_write", "fs_append"}


def test_demande_actuelle_donne_toute_la_famille():
    choisis = set(select_tool_names(["corrige la date de l'échéance de l'assurance", ""], TOUS))
    assert {"papiers_corriger", "papiers_marquer"} <= choisis
    assert "fs_write" in select_tool_names(["écris un fichier notes.md"], TOUS)


def test_classement_lecture_action():
    for n in ("papiers_corriger", "note_create", "device_control", "scene_run", "fs_write", "memoire_retenir", "mcp_x_tool", "code_agent"):
        assert not est_lecture(n), n
    for n in ("papiers_echeances", "fs_read", "web_search", "list_show", "memoire_lister"):
        assert est_lecture(n), n


class _Outil:
    def __init__(self, n):
        self.name = n

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "description": "Fait quelque chose.", "parameters": {}}}


class _Base:
    def get(self, n):
        return _Outil(n) if n in TOUS else None


def test_registre_refuse_une_action_non_proposee_et_previent_le_modele():
    reg = SubsetRegistry(_Base(), ["papiers_echeances", "note_create"])
    assert reg.get("papiers_corriger") is None                  # action non proposée : refusée
    assert reg.get("fs_read") is not None                        # lecture hors sélection : permise
    desc = {s["function"]["name"]: s["function"]["description"] for s in reg.schemas()}
    assert "ACTION" in desc["note_create"] and "ACTION" not in desc["papiers_echeances"]


def _faux_flux(morceaux_par_appel):
    appels = iter(morceaux_par_appel)

    async def flux(history, tools=None, model=None):
        for m in next(appels):
            yield "content", m
    return flux


def _lancer(monkeypatch, morceaux_par_appel, interdits=None):
    monkeypatch.setattr(loop, "stream_decide", _faux_flux(morceaux_par_appel))
    evs = []

    async def send(ev):
        evs.append(ev)

    async def gate(*_):
        return False
    hist = [{"role": "system", "content": "x"}, {"role": "user", "content": "comment je m'appelle"}]
    out = asyncio.run(loop._run_harness_inner(hist, SubsetRegistry(_Base(), [], interdits), send, gate))
    return out, "".join(e["text"] for e in evs if e.get("type") == "token")


def test_recitation_seule_redemande_une_vraie_reponse(monkeypatch):
    out, affiche = _lancer(monkeypatch, [
        ["The output MUST strictly adhere ", "to the following format", '<tool_response>[{"souvenirs": []}]</tool_response>'],
        ["Tu t'appelles Paul."]])
    assert out == affiche == "Tu t'appelles Paul."


def test_recitation_apres_du_texte_est_coupee(monkeypatch):
    out, affiche = _lancer(monkeypatch, [["Je ne trouve pas cet élément. ", "<tool_", 'response>{"error": "x"}</tool_response>']])
    assert out == affiche.strip() == "Je ne trouve pas cet élément."
    assert "<" not in affiche


def test_reponse_normale_intacte(monkeypatch):
    out, affiche = _lancer(monkeypatch, [["Bonjour ", "Paul, ", "The output est prêt."]])
    assert out == affiche == "Bonjour Paul, The output est prêt."


def test_detection_du_prenom():
    assert memoire.detect("je m'appelle Paul") == {"action": "nom", "nom": "Paul"}
    assert memoire.detect("Comment je m'appelle ?") == {"action": "quel_nom"}
    assert memoire.detect("je m'appelle Paul et je cherche un plombier") is None
    assert "papiers_corriger" not in LECTURE


def test_appel_ecrit_en_python_jamais_affiche(monkeypatch):
    # qwen2.5 a écrit : "{'name': 'docs_search', 'parameters': {...}}" — outil non proposé : on redemande une vraie réponse.
    out, affiche = _lancer(monkeypatch, [
        ["\"{'name': 'docs_search', ", "'parameters': {'limit': 10, 'query': 'prenom Paul'}}\""],
        ["Enchantée Paul ! Je retiens ta date de naissance."]], interdits={"docs_search"})
    assert out == affiche == "Enchantée Paul ! Je retiens ta date de naissance."
    assert "name" not in affiche


def test_parle_de_soi():
    assert memoire.parle_de_soi("slt eva, tu sais que mon véritable prénom est Paul et je suis né le 14-03-1985")
    assert not memoire.parle_de_soi("quel temps fera-t-il demain à Lille ?")
