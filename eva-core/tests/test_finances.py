"""Finances personnelles : import CSV/OFX sans doublon, catégories apprises, budgets, tableau, confidentialité, module coupé."""
from datetime import date

from integration_pg import requiert_pg

pytestmark = requiert_pg

M = date.today().strftime("%Y-%m")
J = date.today().strftime("%d/%m/%Y")

CSV_DEBIT_CREDIT = f"""Téléchargement du {J}
Compte courant n° 123

Date;Libellé;Débit euros;Crédit euros;
{J};"CB CARREFOUR MARKET LONS 12/10";54,30;;
{J};"PRLV SEPA EDF CLIENTS";82,00;;
{J};"VIR SEPA SALAIRE ACME";;2 150,00;
{J};"CB LE PETIT BISTROT";38,50;;
{J};"CB BOULANGERIE DUPAIN";3,20;;
{J};"CB BOULANGERIE DUPAIN";3,20;;
""".encode("cp1252")

OFX = f"""OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{date.today().strftime('%Y%m%d')}<TRNAMT>-12.99<FITID>A1<NAME>NETFLIX.COM
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{date.today().strftime('%Y%m%d')}<TRNAMT>-45.00<FITID>A2<NAME>CINEMA PATHE
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>""".encode()


def test_finances(eva):
    c, H, t, m = eva["c"], eva["H"], eva["t"], eva["m"]
    A, B = H(t["alice"]), H(t["bob"])
    assert c.get("/api/finances/comptes", headers=A).status_code == 404                     # module coupé
    c.put("/api/modules", json={"finances": True}, headers=A)
    cid = c.post("/api/finances/comptes", json={"nom": "Compte courant", "solde_initial": "1 000,00"}, headers=A).json()["id"]
    r = c.post(f"/api/finances/comptes/{cid}/import?nom=releve.csv", content=CSV_DEBIT_CREDIT, headers=A).json()
    assert r == {"lues": 6, "ajoutees": 6, "deja_la": 0}, r                                   # deux cafés identiques : deux opérations
    assert c.post(f"/api/finances/comptes/{cid}/import?nom=releve.csv", content=CSV_DEBIT_CREDIT, headers=A).json()["ajoutees"] == 0
    assert c.post(f"/api/finances/comptes/{cid}/import?nom=releve.ofx", content=OFX, headers=A).json()["ajoutees"] == 2
    ops = {o["libelle"]: o for o in c.get(f"/api/finances/operations?mois={M}", headers=A).json()["operations"]}
    assert ops["CB CARREFOUR MARKET LONS 12/10"]["categorie"] == "Alimentation" and ops["CB CARREFOUR MARKET LONS 12/10"]["montant"] == -54.3
    assert ops["PRLV SEPA EDF CLIENTS"]["categorie"] == "Énergie" and ops["VIR SEPA SALAIRE ACME"]["categorie"] == "Revenus"
    assert ops["NETFLIX.COM"]["categorie"] == "Abonnements" and ops["CINEMA PATHE"]["categorie"] == "Loisirs"
    assert ops["CB LE PETIT BISTROT"]["categorie"] == "Restaurants"
    boul = [o for o in c.get(f"/api/finances/operations?mois={M}&q=DUPAIN", headers=A).json()["operations"]]
    assert boul[0]["categorie"] == "Alimentation"
    r = c.patch(f"/api/finances/operations/{boul[0]['id']}", json={"categorie": "Restaurants"}, headers=A).json()
    assert r["semblables"] == 1                                                              # l'autre café suit
    csv2 = f"Date;Libellé;Montant\n{J};CB BOULANGERIE DUPAIN AUTRE;-4,10\n".encode()
    c.post(f"/api/finances/comptes/{cid}/import?nom=b.csv", content=csv2, headers=A)
    assert c.get(f"/api/finances/operations?mois={M}&q=AUTRE", headers=A).json()["operations"][0]["categorie"] == "Restaurants"   # règle apprise
    c.put("/api/finances/budgets", json={"categorie": "Restaurants", "montant": "40"}, headers=A)
    tb = c.get(f"/api/finances/tableau?mois={M}", headers=A).json()
    resto = next(x for x in tb["par_categorie"] if x["categorie"] == "Restaurants")
    assert resto["depense"] == 49.0 and resto["budget"] == 40.0 and "Restaurants" in tb["depassements"]
    assert tb["revenus"] == 2150.0 and tb["comptes"][0]["solde"] == round(1000 + 2150 - 54.3 - 82 - 38.5 - 3.2 * 2 - 12.99 - 45 - 4.1, 2)
    # confidentialité : bob ne voit rien de Paul, même avec l'identifiant
    assert c.get("/api/finances/comptes", headers=B).json()["comptes"] == []
    assert c.post(f"/api/finances/comptes/{cid}/import?nom=x.csv", content=csv2, headers=B).status_code == 400
    assert c.patch(f"/api/finances/operations/{boul[0]['id']}", json={"categorie": "Autre"}, headers=B).status_code == 400
    from app import profiles
    tok = profiles.user_var.set("bob")
    try:
        assert c.portal.call(lambda: m.registry.get("finances_resume").execute())["revenus"] == 0
    finally:
        profiles.user_var.reset(tok)
    tok = profiles.user_var.set("alice")
    try:
        r = c.portal.call(lambda: m.registry.get("finances_operations").execute(categorie="Restaurants"))
        assert r["nombre"] == 4 and r["total"] == -49.0
    finally:
        profiles.user_var.reset(tok)
    assert "Format CSV non reconnu" in c.post(f"/api/finances/comptes/{cid}/import?nom=x.csv", content=b"a;b\n1;2", headers=A).json()["detail"]
