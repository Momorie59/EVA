"""Livre de recettes (module activable) : droits, quantités, liste de courses, lien de partage, invité, outils d'EVA."""
from integration_pg import MDP, requiert_pg

pytestmark = requiert_pg

CREPES = {"titre": "Crêpes de grand-mère", "resume": "Les crêpes du dimanche", "personnes": 4, "prep_min": 10, "cuisson_min": 20,
          "categorie": "Dessert", "tags": ["rapide", "enfants"],
          "ingredients": ["250 g de farine", "4 œufs", "1/2 l de lait", "1 pincée de sel", "50 g de beurre fondu"],
          "etapes": [{"texte": "Mélanger la farine et les œufs."}, {"texte": "Ajouter le lait petit à petit.", "minuteur_min": 0},
                     {"texte": "Laisser reposer.", "minuteur_min": 60}],
          "video": "https://youtu.be/dQw4w9WgXcQ", "notes": "Un peu de rhum pour les grands."}


def test_recettes_complet(eva):
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    assert c.get("/api/recettes", headers=H(t["alice"])).status_code == 404                      # module coupé par défaut
    c.put("/api/modules", json={"recettes": True}, headers=H(t["alice"]))
    rec = c.post("/api/recettes", json=CREPES, headers=H(t["bob"])).json()
    assert rec["video"] == "yt:dQw4w9WgXcQ" and rec["ingredients"][0] == {"quantite": 250.0, "unite": "g", "nom": "farine", "groupe": ""}
    prive = c.post("/api/recettes", json={"titre": "Sauce secrète", "ingredients": ["1 c. à s. de miel"], "etapes": ["Mélanger."], "prive": True},
                   headers=H(t["bob"])).json()
    # lecture : tout le monde voit le livre, pas la recette privée de Bob
    titres = [r["titre"] for r in c.get("/api/recettes", headers=H(t["carla"])).json()["recettes"]]
    assert "Crêpes de grand-mère" in titres and "Sauce secrète" not in titres
    assert c.get(f"/api/recettes/{prive['id']}", headers=H(t["carla"])).status_code == 404
    # quantités pour 6
    r6 = c.get(f"/api/recettes/{rec['id']}?personnes=6", headers=H(t["carla"])).json()
    assert r6["lignes"][:4] == ["375 g de farine", "6 œufs", "¾ l de lait", "1 ½ pincées de sel"] and r6["peut_modifier"] is False
    assert c.put(f"/api/recettes/{rec['id']}", json={"titre": "Piraté"}, headers=H(t["carla"])).status_code == 403
    assert c.put(f"/api/recettes/{rec['id']}", json={"resume": "Les meilleures"}, headers=H(t["bob"])).json()["resume"] == "Les meilleures"
    # liste de courses
    co = c.post(f"/api/recettes/{rec['id']}/courses", json={"personnes": 8}, headers=H(t["carla"])).json()
    assert co["liste"] == "Courses" and "500 g de farine" in co["ajoutes"] and "1 l de lait" in co["ajoutes"]
    co2 = c.post(f"/api/recettes/{rec['id']}/courses", json={"personnes": 8, "imprimer": True}, headers=H(t["carla"])).json()
    assert "500 g de farine" in co2["deja"] and ("impression" in co2 or "impression_erreur" in co2)   # pas d'imprimante ici : erreur claire
    # partage par lien : page publique sans compte, révocable
    assert c.post(f"/api/recettes/{rec['id']}/partage", json={"actif": True}, headers=H(t["carla"])).status_code == 403
    url = c.post(f"/api/recettes/{rec['id']}/partage", json={"actif": True}, headers=H(t["bob"])).json()["url"]
    page = c.get(url)
    assert page.status_code == 200 and "Crêpes de grand-mère" in page.text and "250 g de farine" in page.text
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in page.text and "Imprimer / PDF" in page.text and "<script>alert" not in page.text
    c.post(f"/api/recettes/{rec['id']}/partage", json={"actif": False}, headers=H(t["bob"]))
    assert c.get(url).status_code == 404
    # invité : lit le livre, ne crée rien
    assert c.post("/api/auth/users", json={"user": "copine", "password": MDP, "role": "guest"}, headers=H(t["alice"])).status_code == 200
    invite = c.post("/api/auth/login", json={"user": "copine", "password": MDP}).json()["token"]
    assert c.get(f"/api/recettes/{rec['id']}", headers=H(invite)).status_code == 200
    assert c.post("/api/recettes", json=CREPES, headers=H(invite)).status_code == 403
    assert c.get("/api/papiers/etat", headers=H(invite)).status_code == 403
    # EVA
    from app import profiles
    tok = profiles.user_var.set("carla")
    try:
        trouve = c.portal.call(lambda: m.registry.get("recette_chercher").execute(q="crêpes"))
        assert trouve["recettes"][0]["titre"] == "Crêpes de grand-mère"
        lu = c.portal.call(lambda: m.registry.get("recette_lire").execute(titre="crêpes", personnes=2))
        assert lu["ingredients"][0] == "125 g de farine" and lu["pour"] == 2
    finally:
        profiles.user_var.reset(tok)
    # suppression : auteur seulement
    assert c.delete(f"/api/recettes/{rec['id']}", headers=H(t["carla"])).status_code == 403
    assert c.delete(f"/api/recettes/{rec['id']}", headers=H(t["bob"])).status_code == 200
    c.put("/api/modules", json={"recettes": False}, headers=H(t["alice"]))


def test_page_publique_echappe_le_html(eva):
    from app import recettes
    html = recettes.page_html({**{k: v for k, v in CREPES.items()}, "titre": "<script>alert(1)</script>", "resume": "", "photo": "", "video": "",
                               "ingredients": [{"quantite": 1, "unite": "", "nom": "<b>œuf</b>"}], "etapes": [{"texte": "<img src=x onerror=1>"}],
                               "difficulte": "Facile", "categorie": "Dessert", "repos_min": 0, "notes": ""})
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html and "<img src=x" not in html
