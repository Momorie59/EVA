"""Cockpit de finances personnelles (comme Jarvis) — module activable, STRICTEMENT privé : chaque personne ne voit que ses comptes.

Pas de connexion à la banque : on importe les relevés téléchargés depuis son espace bancaire (CSV ou OFX). Les opérations
déjà importées ne sont jamais doublées. Les catégories sont devinées (supermarché → Alimentation, EDF → Énergie…) et
EVA retient tes corrections pour la suite. Budgets par catégorie et par mois, tableau de bord, et EVA répond aux questions
(« combien j'ai dépensé en restaurants ce mois-ci ? ») en lecture seule. Rien ne quitte le NAS."""
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .db import get_pool

SCHEMA = """
CREATE TABLE IF NOT EXISTS fin_comptes (
    id SERIAL PRIMARY KEY,
    qui TEXT NOT NULL,
    nom TEXT NOT NULL,
    solde_initial NUMERIC(14,2) NOT NULL DEFAULT 0,
    cree TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fin_comptes_qui ON fin_comptes(qui);
CREATE TABLE IF NOT EXISTS fin_operations (
    id SERIAL PRIMARY KEY,
    qui TEXT NOT NULL,
    compte_id INTEGER NOT NULL REFERENCES fin_comptes(id) ON DELETE CASCADE,
    jour DATE NOT NULL,
    libelle TEXT NOT NULL,
    montant NUMERIC(14,2) NOT NULL,
    categorie TEXT NOT NULL DEFAULT 'Autre',
    note TEXT NOT NULL DEFAULT '',
    empreinte TEXT NOT NULL,
    cree TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (qui, empreinte)
);
CREATE INDEX IF NOT EXISTS fin_operations_qui_jour ON fin_operations(qui, jour);
CREATE TABLE IF NOT EXISTS fin_regles (
    qui TEXT NOT NULL,
    motif TEXT NOT NULL,
    categorie TEXT NOT NULL,
    PRIMARY KEY (qui, motif)
);
CREATE TABLE IF NOT EXISTS fin_budgets (
    qui TEXT NOT NULL,
    categorie TEXT NOT NULL,
    montant NUMERIC(14,2) NOT NULL,
    PRIMARY KEY (qui, categorie)
);
"""

CATEGORIES = ["Alimentation", "Restaurants", "Logement", "Énergie", "Transport", "Santé", "Enfants", "Loisirs", "Abonnements",
              "Shopping", "Banque & assurances", "Impôts & taxes", "Épargne", "Revenus", "Virements internes", "Autre"]
_REGLES_BASE = [
    ("Revenus", r"salaire|paie|virement de .*employeur|caf\b|allocation|pole emploi|france travail|remboursement|pension|retraite"),
    ("Alimentation", r"carrefour|leclerc|lidl|aldi|intermarche|auchan|super ?u|hyper ?u|casino|monoprix|franprix|netto|grand frais|biocoop|picard|boulangerie|boucherie|marche"),
    ("Restaurants", r"restaurant|resto|bistro|bistrot|brasserie|creperie|pizzeria|sushi|kebab|traiteur|snack|mcdo|mc ?donald|burger king|kfc|quick|subway|uber ?eats|deliveroo|just ?eat|pizza|brasserie|cafe|bar\b"),
    ("Énergie", r"\bedf\b|engie|total ?energies|eni\b|ekwateur|gaz|electricite|\beau\b|veolia|saur"),
    ("Transport", r"sncf|ouigo|ratp|\btcl\b|uber(?! ?eats)|bolt|blablacar|peage|autoroute|aprr|sanef|vinci autoroutes|esso|shell|avia|station|carburant|parking|total(?! ?energies)"),
    ("Santé", r"pharmacie|medecin|docteur|dentiste|kine|hopital|clinique|laboratoire|cpam|ameli|mutuelle|opticien|doctolib"),
    ("Abonnements", r"netflix|spotify|deezer|disney|canal\+|prime video|amazon prime|apple\.com|google|free\b|free mobile|orange|sfr|bouygues|sosh|red by|youtube|icloud"),
    ("Shopping", r"amazon|fnac|darty|boulanger|ikea|leroy merlin|castorama|decathlon|zara|h&m|kiabi|action\b|cdiscount|vinted|ebay|aliexpress|temu|shein"),
    ("Logement", r"loyer|pret immo|credit immo|syndic|charges copro|foncia|nexity|assurance habitation"),
    ("Impôts & taxes", r"impots|dgfip|tresor public|taxe|amende|antai"),
    ("Banque & assurances", r"frais bancaires|cotisation carte|commission|agios|assurance(?! habitation)|maif|macif|matmut|axa|allianz|groupama|gmf"),
    ("Enfants", r"creche|nounou|cantine|ecole|college|lycee|periscolaire|centre de loisirs|pajemploi"),
    ("Loisirs", r"cinema|ugc|pathe|gaumont|fnac spectacles|ticketmaster|steam|playstation|nintendo|xbox|sport|piscine|salle de sport|basic fit|voyage|hotel|airbnb|booking"),
    ("Épargne", r"livret|epargne|assurance vie|pea\b|bourse"),
    ("Virements internes", r"virement (?:interne|vers|de) (?:mon|ma|compte)|vir(?:ement)? sepa (?:emis|recu) .*moi"),
]


class FinancesError(RuntimeError):
    pass


def _plat(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")


def motif_de(libelle: str) -> str:
    """« CB CARREFOUR MARKET 12/10 LONS » → « carrefour market lons » : sert de règle apprise (sans dates ni numéros)."""
    t = re.sub(r"\b(cb|carte|prlv|prelevement|vir|virement|sepa|paiement|achat|retrait|dab|facture|du|le|fact)\b", " ", _plat(libelle))
    t = re.sub(r"[\d/.:*#-]+", " ", t)
    return " ".join(w for w in t.split() if len(w) > 1)[:60]


async def categoriser(qui: str, libelle: str, montant: Decimal) -> str:
    m = motif_de(libelle)
    async with get_pool().acquire() as conn:
        regles = await conn.fetch("SELECT motif, categorie FROM fin_regles WHERE qui=$1", qui)
    for r in sorted(regles, key=lambda r: -len(r["motif"])):          # règles apprises d'abord (la plus précise gagne)
        if r["motif"] and r["motif"] in m:
            return r["categorie"]
    p = _plat(libelle)
    for cat, motif in _REGLES_BASE:
        if re.search(motif, p):
            if cat == "Revenus" and montant < 0:
                continue
            return cat
    return "Revenus" if montant > 0 else "Autre"


# ---------------------------------------------------------------- import des relevés

def _nombre(t: str) -> Decimal | None:
    t = (t or "").strip().replace(" ", "").replace(" ", "").replace(" ", "").replace("€", "").replace("EUR", "")
    if not t:
        return None
    if "," in t and "." in t:                                      # 1.234,56 ou 1,234.56
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _jour(t: str) -> date | None:
    t = (t or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(t[:10] if f != "%Y%m%d" else t[:8], f).date()
        except ValueError:
            continue
    return None


def lire_csv(texte: str) -> list[dict]:
    """CSV des banques françaises : séparateur ; ou , ; colonnes date / libellé / montant, ou débit + crédit ; lignes d'en-tête ignorées."""
    lignes = [l for l in texte.replace("\r\n", "\n").split("\n") if l.strip()]
    sep = ";" if sum(l.count(";") for l in lignes[:20]) >= sum(l.count(",") for l in lignes[:20]) else ","
    rows = list(csv.reader(io.StringIO("\n".join(lignes)), delimiter=sep))
    entete_i, cols = None, {}
    for i, r in enumerate(rows[:30]):
        noms = [_plat(c) for c in r]
        if any("date" in n for n in noms) and any(k in n for n in noms for k in ("montant", "debit", "credit", "libelle", "operation")):
            entete_i = i
            for j, n in enumerate(noms):
                if "date" in n and "date" not in cols and "valeur" not in n:
                    cols["date"] = j
                elif "date" in n and "date" not in cols:
                    cols["date"] = j
                elif any(k in n for k in ("libelle", "detail", "operation", "description", "intitule")) and "libelle" not in cols:
                    cols["libelle"] = j
                elif "debit" in n:
                    cols["debit"] = j
                elif "credit" in n:
                    cols["credit"] = j
                elif "montant" in n or n in ("amount", "somme"):
                    cols["montant"] = j
            break
    if entete_i is None or "date" not in cols:
        raise FinancesError("Format CSV non reconnu : il faut au moins une colonne « Date », un libellé et un montant (ou débit/crédit).")
    ops = []
    for r in rows[entete_i + 1:]:
        if len(r) <= cols["date"]:
            continue
        j = _jour(r[cols["date"]])
        if not j:
            continue
        if "montant" in cols and cols["montant"] < len(r) and _nombre(r[cols["montant"]]) is not None:
            m = _nombre(r[cols["montant"]])
        else:
            deb = _nombre(r[cols["debit"]]) if "debit" in cols and cols["debit"] < len(r) else None
            cre = _nombre(r[cols["credit"]]) if "credit" in cols and cols["credit"] < len(r) else None
            if deb is None and cre is None:
                continue
            m = (cre or Decimal(0)) - abs(deb or Decimal(0))
        lib = r[cols["libelle"]] if "libelle" in cols and cols["libelle"] < len(r) else " ".join(r)
        ops.append({"jour": j, "libelle": " ".join(lib.split())[:200], "montant": m})
    return ops


def lire_ofx(texte: str) -> list[dict]:
    ops = []
    for bloc in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", texte, re.S | re.I):
        champ = lambda nom: (re.search(rf"<{nom}>([^<\r\n]*)", bloc, re.I) or [None, ""])[1].strip()  # noqa: E731
        j, m = _jour(champ("DTPOSTED")[:8]), _nombre(champ("TRNAMT"))
        if j and m is not None:
            lib = " ".join(x for x in (champ("NAME"), champ("MEMO")) if x)
            ops.append({"jour": j, "libelle": " ".join(lib.split())[:200] or "(sans libellé)", "montant": m, "fitid": champ("FITID")})
    if not ops:
        raise FinancesError("Aucune opération trouvée dans ce fichier OFX.")
    return ops


async def importer(qui: str, compte_id: int, nom_fichier: str, donnees: bytes) -> dict:
    await _compte(qui, compte_id)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = donnees.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    ops = lire_ofx(texte) if nom_fichier.lower().endswith((".ofx", ".qfx")) or "<OFX>" in texte[:2000].upper() else lire_csv(texte)
    ajoutees = 0
    vus: dict[str, int] = {}
    async with get_pool().acquire() as conn:
        for o in ops:
            base = o.get("fitid") or f"{o['jour']}|{o['montant']}|{_plat(o['libelle'])}"
            vus[base] = vus.get(base, 0) + 1                           # deux cafés identiques le même jour : deux opérations
            emp = hashlib.sha256(f"{compte_id}|{base}|{vus[base]}".encode()).hexdigest()
            cat = await categoriser(qui, o["libelle"], o["montant"])
            r = await conn.execute("INSERT INTO fin_operations (qui, compte_id, jour, libelle, montant, categorie, empreinte) "
                                   "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (qui, empreinte) DO NOTHING",
                                   qui, compte_id, o["jour"], o["libelle"], o["montant"], cat, emp)
            ajoutees += r.endswith("1")
    return {"lues": len(ops), "ajoutees": ajoutees, "deja_la": len(ops) - ajoutees}


# ---------------------------------------------------------------- comptes, opérations, budgets

async def _compte(qui: str, cid: int) -> dict:
    async with get_pool().acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM fin_comptes WHERE id=$1 AND qui=$2", int(cid), qui)
    if not r:
        raise FinancesError("Compte introuvable.")
    return dict(r)


async def comptes(qui: str) -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT c.id, c.nom, c.solde_initial, COALESCE(SUM(o.montant), 0) AS mouvements, COUNT(o.id) AS operations, "
                                "MAX(o.jour) AS dernier FROM fin_comptes c LEFT JOIN fin_operations o ON o.compte_id=c.id "
                                "WHERE c.qui=$1 GROUP BY c.id ORDER BY c.nom", qui)
    return [{"id": r["id"], "nom": r["nom"], "solde_initial": float(r["solde_initial"]), "solde": float(r["solde_initial"] + r["mouvements"]),
             "operations": r["operations"], "dernier": r["dernier"].isoformat() if r["dernier"] else None} for r in rows]


async def creer_compte(qui: str, nom: str, solde_initial=0) -> dict:
    nom = " ".join(str(nom or "").split())[:60]
    if not nom:
        raise FinancesError("Donne un nom au compte (ex. Compte courant).")
    s = _nombre(str(solde_initial)) or Decimal(0)
    async with get_pool().acquire() as conn:
        cid = await conn.fetchval("INSERT INTO fin_comptes (qui, nom, solde_initial) VALUES ($1,$2,$3) RETURNING id", qui, nom, s)
    return {"id": cid, "nom": nom}


async def modifier_compte(qui: str, cid: int, nom: str | None = None, solde_initial=None) -> None:
    await _compte(qui, cid)
    async with get_pool().acquire() as conn:
        if nom:
            await conn.execute("UPDATE fin_comptes SET nom=$1 WHERE id=$2 AND qui=$3", " ".join(nom.split())[:60], cid, qui)
        if solde_initial is not None:
            await conn.execute("UPDATE fin_comptes SET solde_initial=$1 WHERE id=$2 AND qui=$3", _nombre(str(solde_initial)) or Decimal(0), cid, qui)


async def supprimer_compte(qui: str, cid: int) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM fin_comptes WHERE id=$1 AND qui=$2", cid, qui)


def _mois(m: str | None) -> tuple[date, date, str]:
    m = (m or date.today().strftime("%Y-%m"))[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", m):
        raise FinancesError("Mois attendu au format AAAA-MM.")
    a, n = int(m[:4]), int(m[5:])
    debut = date(a, n, 1)
    fin = date(a + (n == 12), n % 12 + 1, 1)
    return debut, fin, m


async def operations(qui: str, mois: str | None = None, categorie: str = "", recherche: str = "", limite: int = 500) -> list[dict]:
    debut, fin, _m = _mois(mois)
    q = ["qui=$1", "jour >= $2", "jour < $3"]
    args: list = [qui, debut, fin]
    if categorie:
        args.append(categorie)
        q.append(f"categorie=${len(args)}")
    if recherche:
        args.append(f"%{recherche}%")
        q.append(f"libelle ILIKE ${len(args)}")
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(f"SELECT id, compte_id, jour, libelle, montant, categorie, note FROM fin_operations WHERE {' AND '.join(q)} "
                                f"ORDER BY jour DESC, id DESC LIMIT {int(limite)}", *args)
    return [{**dict(r), "jour": r["jour"].isoformat(), "montant": float(r["montant"])} for r in rows]


async def recategoriser(qui: str, oid: int, categorie: str, retenir: bool = True) -> dict:
    if categorie not in CATEGORIES:
        raise FinancesError("Catégorie inconnue.")
    async with get_pool().acquire() as conn:
        lib = await conn.fetchval("SELECT libelle FROM fin_operations WHERE id=$1 AND qui=$2", oid, qui)
        if lib is None:
            raise FinancesError("Opération introuvable.")
        await conn.execute("UPDATE fin_operations SET categorie=$1 WHERE id=$2 AND qui=$3", categorie, oid, qui)
        autres = 0
        motif = motif_de(lib)
        if retenir and len(motif) >= 3:                               # EVA retient : les opérations semblables suivront
            await conn.execute("INSERT INTO fin_regles (qui, motif, categorie) VALUES ($1,$2,$3) ON CONFLICT (qui, motif) DO UPDATE SET categorie=$3",
                               qui, motif, categorie)
            rows = await conn.fetch("SELECT id, libelle FROM fin_operations WHERE qui=$1 AND id<>$2 AND categorie<>$3", qui, oid, categorie)
            ids = [r["id"] for r in rows if motif in motif_de(r["libelle"])]
            if ids:
                await conn.execute("UPDATE fin_operations SET categorie=$1 WHERE qui=$2 AND id = ANY($3::int[])", categorie, qui, ids)
            autres = len(ids)
    return {"ok": True, "semblables": autres}


async def budgets(qui: str) -> dict:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT categorie, montant FROM fin_budgets WHERE qui=$1", qui)
    return {r["categorie"]: float(r["montant"]) for r in rows}


async def regler_budget(qui: str, categorie: str, montant) -> dict:
    if categorie not in CATEGORIES:
        raise FinancesError("Catégorie inconnue.")
    v = _nombre(str(montant)) if montant not in (None, "") else None
    async with get_pool().acquire() as conn:
        if not v:
            await conn.execute("DELETE FROM fin_budgets WHERE qui=$1 AND categorie=$2", qui, categorie)
        else:
            await conn.execute("INSERT INTO fin_budgets (qui, categorie, montant) VALUES ($1,$2,$3) ON CONFLICT (qui, categorie) DO UPDATE SET montant=$3",
                               qui, categorie, abs(v))
    return await budgets(qui)


async def tableau(qui: str, mois: str | None = None) -> dict:
    """Tableau de bord du mois : revenus, dépenses, par catégorie avec budget, évolution sur 6 mois, plus grosses dépenses."""
    debut, fin, m = _mois(mois)
    async with get_pool().acquire() as conn:
        cats = await conn.fetch("SELECT categorie, SUM(montant) AS total, COUNT(*) AS n FROM fin_operations "
                                "WHERE qui=$1 AND jour >= $2 AND jour < $3 AND categorie <> 'Virements internes' GROUP BY categorie", qui, debut, fin)
        evol = await conn.fetch("SELECT to_char(jour, 'YYYY-MM') AS mois, SUM(CASE WHEN montant > 0 THEN montant ELSE 0 END) AS revenus, "
                                "SUM(CASE WHEN montant < 0 THEN -montant ELSE 0 END) AS depenses FROM fin_operations "
                                "WHERE qui=$1 AND categorie <> 'Virements internes' AND jour >= ($2::date - interval '5 months') AND jour < $3 "
                                "GROUP BY 1 ORDER BY 1", qui, debut, fin)
        grosses = await conn.fetch("SELECT jour, libelle, montant, categorie FROM fin_operations WHERE qui=$1 AND jour >= $2 AND jour < $3 "
                                   "AND montant < 0 AND categorie <> 'Virements internes' ORDER BY montant ASC LIMIT 5", qui, debut, fin)
    b = await budgets(qui)
    revenus = sum(float(r["total"]) for r in cats if r["total"] > 0)
    depenses = -sum(float(r["total"]) for r in cats if r["total"] < 0)
    par_cat = sorted(({"categorie": r["categorie"], "depense": round(-float(r["total"]), 2), "operations": r["n"], "budget": b.get(r["categorie"])}
                      for r in cats if r["total"] < 0), key=lambda x: -x["depense"])
    for c, v in b.items():                                            # budgets sans dépense ce mois-ci
        if not any(x["categorie"] == c for x in par_cat):
            par_cat.append({"categorie": c, "depense": 0.0, "operations": 0, "budget": v})
    return {"mois": m, "revenus": round(revenus, 2), "depenses": round(depenses, 2), "solde_mois": round(revenus - depenses, 2),
            "par_categorie": par_cat, "depassements": [x["categorie"] for x in par_cat if x["budget"] and x["depense"] > x["budget"]],
            "evolution": [{"mois": r["mois"], "revenus": round(float(r["revenus"]), 2), "depenses": round(float(r["depenses"]), 2)} for r in evol],
            "plus_grosses": [{"jour": r["jour"].isoformat(), "libelle": r["libelle"], "montant": float(r["montant"]), "categorie": r["categorie"]} for r in grosses],
            "comptes": await comptes(qui)}


async def exporter(qui: str) -> dict:
    """Pour « Mes données » : tout ce qui appartient à la personne."""
    async with get_pool().acquire() as conn:
        ops = await conn.fetch("SELECT compte_id, jour, libelle, montant, categorie, note FROM fin_operations WHERE qui=$1 ORDER BY jour", qui)
    return {"comptes": await comptes(qui), "operations": [{**dict(r), "jour": r["jour"].isoformat(), "montant": float(r["montant"])} for r in ops],
            "budgets": await budgets(qui)}


async def effacer(qui: str) -> None:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fin_comptes WHERE qui=$1", qui)
            await conn.execute("DELETE FROM fin_regles WHERE qui=$1", qui)
            await conn.execute("DELETE FROM fin_budgets WHERE qui=$1", qui)


async def noter(qui: str, libelle: str, montant, jour: str = "", compte: str = "", categorie: str = "") -> dict:
    """Opération ajoutée à la main (paiement en espèces, remboursement d'un ami…) ; compte « Espèces » créé au besoin."""
    m = _nombre(str(montant))
    if m is None or m == 0:
        raise FinancesError("Montant attendu (négatif pour une dépense, ex. -12,50).")
    lib = " ".join(str(libelle or "").split())[:200]
    if not lib:
        raise FinancesError("Donne un libellé (« marché », « remboursement de Paul »…).")
    j = _jour(jour) if jour else date.today()
    if not j:
        raise FinancesError("Date attendue au format AAAA-MM-JJ ou JJ/MM/AAAA.")
    lst = await comptes(qui)
    c = next((x for x in lst if _plat(x["nom"]) == _plat(compte)), None) if compte else None
    if c is None and compte:
        c = next((x for x in lst if _plat(compte) in _plat(x["nom"])), None)
    if c is None:
        c = next((x for x in lst if _plat(x["nom"]) == "especes"), None) or await creer_compte(qui, "Espèces", 0)
    cat = categorie if categorie in CATEGORIES else await categoriser(qui, lib, m)
    emp = hashlib.sha256(f"manuel|{qui}|{datetime.now().timestamp()}|{lib}|{m}".encode()).hexdigest()
    async with get_pool().acquire() as conn:
        oid = await conn.fetchval("INSERT INTO fin_operations (qui, compte_id, jour, libelle, montant, categorie, empreinte) "
                                  "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id", qui, c["id"], j, lib, m, cat, emp)
    return {"id": oid, "compte": c["nom"], "jour": j.isoformat(), "libelle": lib, "montant": float(m), "categorie": cat}
