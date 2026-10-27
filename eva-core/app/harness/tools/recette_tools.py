"""Outils « recettes » : EVA cherche et lit le livre de recettes de la famille, envoie les ingrédients d'une recette à la
liste de courses (quantités pour le nombre de personnes voulu), et enregistre une recette quand on le lui demande."""
from typing import Any

import re
from pathlib import Path

from ... import illustrations, medias, modules, profiles, recettes
from ..permissions import Permission
from .base import Tool


def _qui() -> tuple[str, str]:
    return profiles.user_var.get() or "", profiles.role_var.get() or "admin"


def _coupe() -> dict | None:
    return None if modules.actif("recettes") else {"error": "Le livre de recettes n'est pas activé (Paramètres › Modules)."}


class RecetteChercherTool(Tool):
    name = "recette_chercher"
    description = ("Liste ou cherche les recettes du LIVRE DE RECETTES de la famille (pas des fichiers) : q vide = toutes les recettes "
                   "(« liste mes recettes ») ; sinon par nom, ingrédient, catégorie ou étiquette (« crêpes », « poulet », « dessert », « rapide »). "
                   "Préfère les recettes du livre aux recettes d'Internet.")
    parameters = {"type": "object", "properties": {"q": {"type": "string", "description": "Vide pour toutes les recettes"}}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, q: str = "", **_: Any) -> dict:
        if (c := _coupe()):
            return c
        res = await recettes.chercher(_qui()[0], q)
        if not res:
            return {"recettes": [], "info": "Le livre de recettes est vide." if not (q or "").strip() else "Aucune recette du livre ne correspond."}
        return {"recettes": [{"id": r["id"], "titre": r["titre"], "categorie": r["categorie"], "personnes": r["personnes"],
                              "temps_min": r["prep_min"] + r["cuisson_min"], "resume": r["resume"][:200]} for r in res]}


class RecetteLireTool(Tool):
    name = "recette_lire"
    description = "Lit une recette du livre (ingrédients pour le nombre de personnes voulu, étapes, notes)."
    parameters = {"type": "object", "properties": {"titre": {"type": "string"}, "id": {"type": "integer"},
                                                   "personnes": {"type": "integer"}}, "required": []}
    permission = Permission.AUTO
    agent_safe = True

    async def execute(self, titre: str = "", id: Any = None, personnes: Any = None, **_: Any) -> dict:   # noqa: A002
        if (c := _coupe()):
            return c
        qui = _qui()[0]
        try:
            rec = await recettes.lire(qui, int(id)) if id not in (None, "") else await recettes.par_titre(qui, titre)
        except (recettes.RecetteError, ValueError, TypeError):
            rec = None
        if not rec:
            return {"error": f"Pas de recette « {titre or id} » dans le livre."}
        n = int(personnes) if str(personnes or "").isdigit() else rec["personnes"]
        return {"id": rec["id"], "titre": rec["titre"], "pour": n,
                "ingredients": [recettes.ligne(i) for i in recettes.mise_a_echelle(rec["ingredients"], rec["personnes"], n)],
                "etapes": [e["texte"] for e in rec["etapes"]], "notes": rec["notes"]}


class RecetteCoursesTool(Tool):
    name = "recette_courses"
    description = ("Ajoute les ingrédients d'une recette du livre à la liste de courses, avec les quantités pour le nombre "
                   "de personnes voulu (« fais-moi la liste de courses pour les crêpes, pour 6 »). Pour l'imprimer ensuite : print_list.")
    parameters = {"type": "object", "properties": {"titre": {"type": "string"}, "id": {"type": "integer"},
                                                   "personnes": {"type": "integer"}}, "required": []}
    permission = Permission.AUTO

    async def execute(self, titre: str = "", id: Any = None, personnes: Any = None, **_: Any) -> dict:   # noqa: A002
        if (c := _coupe()):
            return c
        qui = _qui()[0]
        try:
            rec = await recettes.lire(qui, int(id)) if id not in (None, "") else await recettes.par_titre(qui, titre)
            if not rec:
                return {"error": f"Pas de recette « {titre or id} » dans le livre."}
            n = int(personnes) if str(personnes or "").isdigit() else None
            return await recettes.vers_courses(qui, rec["id"], n)
        except recettes.RecetteError as e:
            return {"error": str(e)}


_PHOTO = {"type": "string", "description": "Photo : « generer » = EVA dessine le plat avec le serveur d'images ; « derniere » = la dernière image "
                                         "de la galerie ; « img-….png » = une image de la galerie ; ou le chemin d'une photo envoyée (uploads/…). "
                                         "Vide = pas de photo."}
_CHAMPS = {"titre": {"type": "string"}, "resume": {"type": "string"}, "personnes": {"type": "integer"},
           "prep_min": {"type": "integer"}, "cuisson_min": {"type": "integer"}, "repos_min": {"type": "integer"},
           "difficulte": {"type": "string", "enum": recettes.DIFFICULTES},
           "categorie": {"type": "string", "enum": recettes.CATEGORIES},
           "ingredients": {"type": "array", "items": {"type": "string"}}, "etapes": {"type": "array", "items": {"type": "string"}},
           "notes": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}


async def _photo(source: str, titre: str) -> tuple[str, str]:
    """(nom du média, message) ; nom vide si la photo n'a pas pu être faite (la recette est enregistrée quand même)."""
    try:
        donnees, ext, origine = await illustrations.obtenir(source, titre, "recettes", Path(medias._racine))
        return illustrations.ranger("recettes", donnees, ext), f"Photo ajoutée ({origine})."
    except (illustrations.IllustrationError, medias.MediaError) as e:
        return "", f"Recette enregistrée, mais sans photo : {e}"


async def _trouver(qui: str, recette) -> dict | dict:
    try:
        if isinstance(recette, int) or str(recette).isdigit():
            return await recettes.lire(qui, int(recette))
    except recettes.RecetteError as e:
        return {"error": str(e)}
    rec = await recettes.par_titre(qui, str(recette or ""))
    return rec or {"error": f"Recette « {recette} » introuvable (recette_chercher pour la trouver)."}


class RecetteCreerTool(Tool):
    name = "recette_creer"
    description = ("Enregistre une recette dans le livre de la famille, quand la personne le demande (« garde cette recette »). "
                   "ingredients : une ligne par ingrédient avec quantité et unité (« 200 g de farine »). etapes : une phrase par étape. "
                   "photo : EVA PEUT illustrer la recette (« generer » la dessine avec le serveur d'images, ou une image existante) : "
                   "ne dis jamais que tu ne peux pas ajouter de photo.")
    parameters = {"type": "object", "properties": {**_CHAMPS, "photo": _PHOTO}, "required": ["titre", "ingredients", "etapes"]}
    permission = Permission.CONFIRM

    async def execute(self, photo: str = "", **kw: Any) -> dict:
        if (c := _coupe()):
            return c
        qui, role = _qui()
        try:
            rec = await recettes.creer(qui, kw, role)
        except recettes.RecetteError as e:
            return {"error": str(e)}
        out = {"creee": {"id": rec["id"], "titre": rec["titre"], "categorie": rec.get("categorie")}}
        if photo and photo.strip().lower() not in ("non", "aucune", "sans"):
            nom, msg = await _photo(photo, rec["titre"])
            if nom:
                await recettes.modifier(qui, rec["id"], {"photo": nom}, role)
            out["photo"] = msg
        else:
            out["info"] = "Recette ajoutée au livre. Propose d'ajouter une photo : tu peux la dessiner (photo « generer »)."
        return out


def _motif(mot: str) -> "re.Pattern":
    """« moules » trouve aussi « moule », « Moules » : singulier/pluriel, sans tenir compte des majuscules."""
    base = re.escape(mot.strip().lower().rstrip("sx"))
    return re.compile(rf"(?<!\w){base}(?:s|x)?(?!\w)", re.I)


def _ligne(i: dict) -> str:
    q = i.get("quantite")
    q = ("" if q in (None, "", 0) else (str(int(q)) if isinstance(q, (int, float)) and float(q).is_integer() else str(q)))
    return " ".join(x for x in (q, i.get("unite") or "", i.get("nom") or "") if x).strip()


class RecetteModifierTool(Tool):
    name = "recette_modifier"
    description = ("Modifie une recette du livre (titre ou id). Pour REMPLACER un ingrédient partout (liste ET étapes) : "
                   "remplacer=« moules », par=« 300 g de crevettes » (par vide = l'enlever). Ajouter : ajouter_ingredients, ajouter_etapes. "
                   "Aussi : personnes, temps, notes, catégorie, titre, listes complètes d'ingrédients ou d'étapes, et la PHOTO "
                   "(« generer » = EVA la dessine, « derniere » = dernière image de la galerie, img-….png, ou photo envoyée). "
                   "Seuls les champs donnés changent. Ne recrée jamais une recette pour la modifier.")
    parameters = {"type": "object", "properties": {
        "recette": {"type": "string", "description": "Titre (ou id) de la recette"},
        "remplacer": {"type": "string", "description": "Ingrédient ou mot à remplacer partout (ex. « moules »)"},
        "par": {"type": "string", "description": "Ce qui le remplace (ex. « 300 g de crevettes », « poulet ») ; vide = l'enlever"},
        "ajouter_ingredients": {"type": "array", "items": {"type": "string"}},
        "ajouter_etapes": {"type": "array", "items": {"type": "string"}},
        **_CHAMPS, "photo": _PHOTO}, "required": ["recette"]}
    permission = Permission.CONFIRM

    async def execute(self, recette: str = "", photo: str = "", remplacer: str = "", par: str = "",
                      ajouter_ingredients: list | None = None, ajouter_etapes: list | None = None, **kw: Any) -> dict:
        if (c := _coupe()):
            return c
        qui, role = _qui()
        rec = await _trouver(qui, recette)
        if "error" in rec:
            return rec
        champs = {k: v for k, v in kw.items() if k in _CHAMPS and v not in (None, "", [])}
        notes = []
        remplacer, par = str(remplacer or "").strip(), str(par or "").strip()
        if remplacer:
            m = _motif(remplacer)
            ings = list(champs.get("ingredients") or rec.get("ingredients") or [])
            etapes = list(champs.get("etapes") or rec.get("etapes") or [])
            nv_ings, touche = [], 0
            for i in ings:
                txt = i if isinstance(i, str) else _ligne(i)
                if not m.search(txt):
                    nv_ings.append(i)
                    continue
                touche += 1
                if not par:
                    continue
                if re.match(r"\s*\d", par) or isinstance(i, str):        # « 300 g de crevettes » : nouvelle ligne complète
                    nv_ings.append(par if re.match(r"\s*\d", par) else m.sub(par, txt))
                else:                                                       # « poulet » : même quantité, autre ingrédient
                    nv_ings.append({**i, "nom": m.sub(par, i.get("nom") or "")})
            nv_etapes, dans_etapes = [], 0
            for e in etapes:
                t = e if isinstance(e, str) else (e.get("texte") or "")
                n = len(m.findall(t))
                dans_etapes += n
                t2 = m.sub(par, t) if par else re.sub(r"\s{2,}", " ", re.sub(rf"(?:\s*,)?\s*(?:les |la |le |l'|des |du |de la |de )?{m.pattern}", "", t, flags=re.I)).strip()
                nv_etapes.append(t2 if isinstance(e, str) else {**e, "texte": t2})
            if not touche and not dans_etapes:
                return {"error": f"« {remplacer} » n'apparaît pas dans la recette « {rec['titre']} ».",
                        "ingredients_actuels": [i if isinstance(i, str) else _ligne(i) for i in ings]}
            champs["ingredients"], champs["etapes"] = nv_ings, nv_etapes
            notes.append(f"« {remplacer} » {'remplacé par « ' + par + ' »' if par else 'retiré'} "
                         f"({touche} ingrédient{'s' if touche > 1 else ''}, {dans_etapes} mention{'s' if dans_etapes > 1 else ''} dans les étapes)")
        if ajouter_ingredients:
            champs["ingredients"] = list(champs.get("ingredients") or rec.get("ingredients") or []) + [str(x) for x in ajouter_ingredients if str(x).strip()]
        if ajouter_etapes:
            champs["etapes"] = list(champs.get("etapes") or rec.get("etapes") or []) + [str(x) for x in ajouter_etapes if str(x).strip()]
        msg = ""
        if photo:
            nom, msg = await _photo(photo, champs.get("titre") or rec["titre"])
            if nom:
                champs["photo"] = nom
        if not champs:
            return {"error": msg or "Rien à modifier : précise ce qui change (remplacer/par, personnes, ingredients…).",
                    "ingredients_actuels": [_ligne(i) for i in rec.get("ingredients") or []]}
        try:
            apres = await recettes.modifier(qui, rec["id"], champs, role)
        except recettes.RecetteError as e:
            return {"error": str(e)}
        if rec.get("photo") and apres.get("photo") != rec.get("photo"):
            medias.supprimer([rec["photo"]])                       # ancienne photo remplacée : effacée du NAS
        out = {"modifiee": {"id": apres["id"], "titre": apres["titre"]}, "champs": sorted(champs),
               "ingredients": [_ligne(i) for i in apres.get("ingredients") or []]}
        if notes:
            out["changement"] = "; ".join(notes)
        if msg:
            out["photo"] = msg
        return out


class RecettePartagerTool(Tool):
    name = "recette_partager"
    description = ("Crée (ou retire) un lien de partage d'une recette, à envoyer à un ami : il voit la recette sans compte EVA. "
                   "Donne le lien sous forme de lien Markdown.")
    parameters = {"type": "object", "properties": {"recette": {"type": "string"}, "retirer": {"type": "boolean"}}, "required": ["recette"]}
    permission = Permission.CONFIRM

    async def execute(self, recette: str = "", retirer: bool = False, **_: Any) -> dict:
        if (c := _coupe()):
            return c
        qui, role = _qui()
        rec = await _trouver(qui, recette)
        if "error" in rec:
            return rec
        try:
            r = await recettes.partager(qui, rec["id"], role, not retirer)
        except recettes.RecetteError as e:
            return {"error": str(e)}
        if retirer:
            return {"ok": True, "info": f"Lien de partage de « {r['titre']} » retiré."}
        return {"ok": True, "titre": r["titre"], "lien": f"/api/public/recettes/{r['partage']}",
                "info": "Lien relatif à l'adresse d'EVA : donne-le en lien Markdown [titre](lien)."}


def all_tools() -> list[Tool]:
    return [RecetteChercherTool(), RecetteLireTool(), RecetteCoursesTool(), RecetteCreerTool(), RecetteModifierTool(), RecettePartagerTool()]
