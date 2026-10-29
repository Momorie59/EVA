"""Mémoire structurée, « Mes données » (export, effacement) et souvenirs de fichiers, sur EVA complète + Postgres.

Lancement : EVA_TEST_PG=postgresql://eva@127.0.0.1:55432/postgres python -m pytest tests -q"""
import io
import zipfile

from integration_pg import MDP, requiert_pg

pytestmark = requiert_pg


def _sql(eva, q, *args):
    from app.db import get_pool

    async def run():
        async with get_pool().acquire() as conn:
            return await conn.fetch(q, *args)
    return eva["c"].portal.call(run)


def _ws_dire(eva, jeton, texte):
    c = eva["c"]
    sid = c.post("/api/sessions", json={"title": "test"}, headers=eva["H"](jeton)).json()["id"]
    with c.websocket_connect(f"/ws/chat?token={jeton}&session={sid}") as w:
        w.send_json({"text": texte})
        out = ""
        for _ in range(60):
            ev = w.receive_json()
            if ev.get("type") == "token":
                out += ev.get("text", "")
            if ev.get("type") == "done":
                return out
    return out


# ------------------------------------------------------------------ mémoire
def test_memoire_rest_cloisonnee(eva):
    c, H, t = eva["c"], eva["H"], eva["t"]
    s = c.post("/api/memoire", json={"texte": "Je préfère les réponses courtes"}, headers=H(t["bob"])).json()
    assert s["kind"] == "preference"
    assert c.post("/api/memoire", json={"texte": "On a décidé de partir en Bretagne en août"}, headers=H(t["bob"])).json()["kind"] == "decision"
    assert s["id"] not in [x["id"] for x in c.get("/api/memoire", headers=H(t["carla"])).json()["souvenirs"]]
    assert c.patch(f"/api/memoire/{s['id']}", json={"texte": "piraté"}, headers=H(t["carla"])).status_code == 404
    assert c.delete(f"/api/memoire/{s['id']}", headers=H(t["carla"])).status_code == 404
    assert c.patch(f"/api/memoire/{s['id']}", json={"actif": False}, headers=H(t["bob"])).json()["actif"] is False
    from app import memoire
    bloc = c.portal.call(memoire.bloc_prompt, "bob")
    assert "Bretagne" in bloc and "courtes" not in bloc                     # un souvenir désactivé n'est plus donné au modèle
    assert c.portal.call(memoire.bloc_prompt, "carla") == ""
    assert c.put("/api/memoire/reglage", json={"actif": False}, headers=H(t["bob"])).json()["actif"] is False
    assert c.portal.call(memoire.bloc_prompt, "bob") == ""                # mémoire coupée : rien n'est joint
    c.put("/api/memoire/reglage", json={"actif": True}, headers=H(t["bob"]))


def test_memoire_commandes_dans_la_conversation(eva):
    t = eva["t"]
    r = _ws_dire(eva, t["bob"], "retiens que ma fille s'appelle Léa")
    assert "C'est noté" in r and "ta fille" in r
    assert "Léa" in _ws_dire(eva, t["bob"], "que sais-tu de moi ?")
    assert "Léa" not in _ws_dire(eva, t["alice"], "que sais-tu de moi ?")  # même l'administrateur a sa propre mémoire
    assert "oublié" in _ws_dire(eva, t["bob"], "oublie que ma fille s'appelle Léa")
    from app import memoire
    assert "Léa" not in eva["c"].portal.call(memoire.bloc_prompt, "bob")


# ------------------------------------------------------------------ souvenirs des fichiers déposés
def test_recherche_ne_montre_que_ses_fichiers(eva, monkeypatch):
    from app import docs

    async def faux_embed(textes):
        return [[1.0, 0.0] for _ in textes]
    monkeypatch.setattr(docs, "embed", faux_embed)
    _sql(eva, "INSERT INTO doc_chunks (source, kind, chunk_index, content, embedding) VALUES ($1,'file',0,'relevé bancaire de Bob',$2)",
         "uploads/releve-bob.pdf.txt", [1.0, 0.0])
    _sql(eva, "INSERT INTO doc_chunks (source, kind, chunk_index, content, embedding) VALUES ($1,'file',0,'sauvegarde',$2)",
         "backups/notes.txt", [1.0, 0.0])
    cherche = lambda qui: [h["source"] for h in eva["c"].portal.call(lambda: docs.search("relevé", 10, owner=qui))]  # noqa: E731
    assert "uploads/releve-bob.pdf.txt" in cherche("bob")
    assert cherche("carla") == []
    assert "backups/notes.txt" not in cherche("bob")
    assert "backups/notes.txt" in cherche(None)                          # administrateur


# ------------------------------------------------------------------ mes données
def test_export_et_effacement(eva):
    c, H, t, ws, m = eva["c"], eva["H"], eva["t"], eva["ws"], eva["m"]
    assert c.post("/api/auth/users", json={"user": "dora", "password": MDP, "role": "user"}, headers=H(t["alice"])).status_code == 200
    dora = c.post("/api/auth/login", json={"user": "dora", "password": MDP}).json()["token"]
    sid = c.post("/api/sessions", json={"title": "Recettes de Dora"}, headers=H(dora)).json()["id"]
    from app.memory import save_message
    c.portal.call(save_message, sid, "user", "Ma recette secrète de tiramisu")
    _sql(eva, "INSERT INTO notes (text, owner) VALUES ('Acheter du mascarpone', 'dora')")
    nb = c.post("/api/notebooks", json={"title": "Carnet de Dora"}, headers=H(dora)).json()
    up = c.post("/api/uploads?name=tiramisu.txt", content=b"mascarpone, cafe, biscuits", headers=H(dora)).json()["path"]
    c.post("/api/memoire", json={"texte": "J'aime le café serré"}, headers=H(dora))
    from app.harness.cloisonnement import RegistreCloisonne
    reg = RegistreCloisonne(m.registry, ws, "dora", "user")
    assert "error" not in c.portal.call(lambda: reg.get("project_init").execute(slug="patisserie", name="Pâtisserie", description="Mes gâteaux"))

    inv = c.get("/api/donnees", headers=H(dora)).json()
    assert inv["conversations"] >= 1 and inv["messages"] >= 1 and inv["post_it"] == 1 and inv["carnets"] == 1
    assert inv["projets"] == ["patisserie"] and inv["fichiers"] >= 1 and inv["souvenirs"] == 1
    assert c.get("/api/donnees?personne=dora", headers=H(t["bob"])).status_code == 403
    assert c.get("/api/donnees?personne=dora", headers=H(t["alice"])).json()["post_it"] == 1

    chemin = c.post("/api/donnees/export", headers=H(dora)).json()["path"]
    assert c.get(f"/api/files/download?path={chemin}", headers=H(t["bob"])).status_code == 403
    r = c.get(f"/api/files/download?path={chemin}", headers=H(dora))
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    noms = z.namelist()
    assert "conversations.json" in noms and "memoire.json" in noms and "fichiers/" + up in noms
    assert any(n.startswith("projets/patisserie/") for n in noms)
    assert "tiramisu" in z.read("conversations.json").decode() and "café serré" in z.read("memoire.json").decode()
    assert "password" not in z.read("reglages.json").decode().lower()

    assert c.post("/api/donnees/effacer", json={"confirmation": "oui"}, headers=H(dora)).status_code == 400
    assert c.post("/api/donnees/effacer", json={"confirmation": "EFFACER", "compte": True}, headers=H(dora)).status_code == 403
    assert c.post("/api/donnees/effacer?personne=dora", json={"confirmation": "EFFACER"}, headers=H(t["bob"])).status_code == 403
    r = c.post("/api/donnees/effacer?personne=dora", json={"confirmation": "EFFACER", "compte": True}, headers=H(t["alice"]))
    assert r.status_code == 200, r.text
    assert not (ws / up).exists() and not (ws / chemin).exists() and not (ws / "projets" / "patisserie").exists()
    assert _sql(eva, "SELECT 1 FROM sessions WHERE owner='dora'") == []
    assert _sql(eva, "SELECT 1 FROM messages WHERE session_id=$1", sid) == []
    assert _sql(eva, "SELECT 1 FROM notes WHERE owner='dora'") == [] and _sql(eva, "SELECT 1 FROM memoire WHERE owner='dora'") == []
    assert _sql(eva, "SELECT 1 FROM kv WHERE key=$1", "nb:" + nb["id"]) == []
    assert c.post("/api/auth/login", json={"user": "dora", "password": MDP}).status_code in (401, 403)
    # les données des autres n'ont pas bougé
    assert c.get("/api/memoire", headers=H(t["bob"])).json()["souvenirs"]


def test_souvenirs_automatiques(eva, monkeypatch):
    from app import memoire
    reponses = []

    async def faux_chat(messages, tools=None, model=None):
        return {"role": "assistant", "content": reponses.pop(0)}
    monkeypatch.setattr("app.ollama_client.chat_once", faux_chat)
    run = lambda *a: eva["c"].portal.call(memoire.extraire, *a)                     # noqa: E731
    reponses.append('Voilà : [{"texte": "Je m\'appelle Paul", "sorte": "fait"}, {"texte": "J\'ai deux enfants : Léa et Hugo", "sorte": "fait"},'
                    ' {"texte": "Je suis marié depuis le 3 mai 2008", "sorte": "fait"}, {"texte": "Mon code de carte est 1234", "sorte": "fait"}]')
    ajoutes = run("paul", "je m'appelle Paul, j'ai deux enfants Léa et Hugo et je suis marié depuis le 3 mai 2008, mon code de carte est 1234")
    textes = [s["texte"] for s in ajoutes]
    assert textes == ["Je m'appelle Paul", "J'ai deux enfants : Léa et Hugo", "Je suis marié depuis le 3 mai 2008"]   # le code de carte : jamais
    assert all(s["source"] == "eva" for s in ajoutes)
    assert "3 mai 2008" in eva["c"].portal.call(memoire.bloc_prompt, "paul")
    assert eva["c"].portal.call(memoire.executer, "paul", {"action": "quel_nom"}) == "Tu t'appelles Paul."
    # une précision met à jour le souvenir au lieu d'en ajouter un second
    reponses.append('[{"texte": "J\'ai deux enfants : Léa et Hugo, 8 et 5 ans", "sorte": "fait"}]')
    run("paul", "mes enfants Léa et Hugo ont 8 et 5 ans")
    enfants = [s for s in eva["c"].portal.call(memoire.lister, "paul") if "enfants" in s["texte"]]
    assert len(enfants) == 1 and "8 et 5 ans" in enfants[0]["texte"]
    # une question ou une demande sans rapport : aucun appel au modèle
    assert run("paul", "quel temps fait-il demain ?") == [] and reponses == []
    # mémoire coupée : rien n'est gardé
    eva["c"].portal.call(memoire.set_active, "paul", False)
    reponses.append('[{"texte": "J\'habite à Lille", "sorte": "fait"}]')
    assert run("paul", "j'habite à Lille") == []
    eva["c"].portal.call(memoire.set_active, "paul", True)


def test_reprise_des_anciennes_conversations(eva, monkeypatch):
    """EVA relit les anciennes conversations de la personne (et seulement les siennes) et en retient les faits durables."""
    import asyncio
    from app import memoire, ollama_client
    c, H, t = eva["c"], eva["H"], eva["t"]
    for nom, phrase in (("bob", "J'habite à Lille depuis dix ans"), ("carla", "Mon chien s'appelle Rex")):
        sid = c.post("/api/sessions", json={"title": "ancienne"}, headers=H(t[nom])).json()["id"]
        _sql(eva, "INSERT INTO messages (session_id, role, content) VALUES ($1,'user',$2)", sid, phrase)

    async def faux(messages, model=None, **kw):
        txt = messages[-1]["content"]
        return {"content": '[{"texte": "J\'habite à Lille", "sorte": "fait"}]' if "Lille" in txt else "[]"}
    monkeypatch.setattr(ollama_client, "chat_once", faux)
    assert c.post("/api/memoire/reprendre", headers=H(t["bob"])).json() == {"demarre": True}
    for _ in range(50):
        r = c.get("/api/memoire", headers=H(t["bob"])).json()
        if r["reprise"] and r["reprise"]["etat"] != "en cours":
            break
        c.portal.call(asyncio.sleep, 0.1)
    assert r["reprise"]["etat"] == "fini"
    assert "J'habite à Lille" in [s["texte"] for s in r["souvenirs"]], f"reprise={r['reprise']} souvenirs={[s['texte'] for s in r['souvenirs']]}"
    assert "J'habite à Lille" not in [s["texte"] for s in c.get("/api/memoire", headers=H(t["carla"])).json()["souvenirs"]]   # cloisonné


def test_reprise_conversations_sans_proprietaire_pour_l_admin(eva):
    """Les conversations créées par l'administrateur n'ont pas de propriétaire : seule la reprise de l'administrateur les relit."""
    from app import memoire
    _sql(eva, "INSERT INTO sessions (id, title, owner) VALUES ('c-legacy','ancienne','') ON CONFLICT (id) DO NOTHING")
    _sql(eva, "INSERT INTO messages (session_id, role, content) VALUES ('c-legacy','user','Mon véritable prénom est Paul, je suis né le 14 mars 1985')")
    run = lambda **kw: eva["c"].portal.call(lambda: memoire.messages_anciens("momorie", **kw))
    assert any("Paul" in m for m in run(admin=True))
    assert not any("Paul" in m for m in run(admin=False))


def test_prompt_garde_les_souvenirs_du_sujet_au_dela_de_40(eva):
    """Au-delà de 40 souvenirs, le prompt contient les récents + ceux qui parlent du sujet du message."""
    from app import memoire
    _sql(eva, "DELETE FROM memoire WHERE lower(owner)='zoe'")
    _sql(eva, "INSERT INTO memoire (owner, kind, texte, actif, updated_at) VALUES ('zoe','fait','Mon chat s''appelle Moustache',true, now() - interval '5 days')")
    for i in range(60):
        _sql(eva, "INSERT INTO memoire (owner, kind, texte, actif) VALUES ('zoe','fait',$1,true)", f"Souvenir banal numéro {i}")
    call = eva["c"].portal.call
    assert "Moustache" not in call(memoire.bloc_prompt, "zoe")
    assert "Moustache" in call(memoire.bloc_prompt, "zoe", "comment va mon chat Moustache ?")
    assert call(memoire.bloc_prompt, "zoe", "chat").count("\n- ") <= memoire.MAX_PROMPT
