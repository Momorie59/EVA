"""Outils fichiers cloisonnés pour une personne qui n'est pas administratrice (voir acces.py).

Le registre enveloppe chaque outil qui touche à un chemin du workspace : avant d'exécuter, il vérifie que la personne
a le droit d'ouvrir (ou de modifier) ce chemin ; après, il filtre les listes de dossiers et note les fichiers qu'EVA
livre pour elle. Un refus est rendu comme une erreur normale : le modèle l'explique, rien n'est lu ni écrit."""
from pathlib import Path
from typing import Any

from .. import acces, project_acl

LECTURE = {"fs_list", "fs_read", "fs_tree", "fs_grep", "dev_check", "zip_make", "print_file", "document_modifier"}
ECRITURE = {"fs_write", "fs_append", "fs_delete", "fs_edit"}
PAR_SLUG = {"project_log_decision", "project_log_change", "project_init", "code_agent"}
LIVRAISON = {"file_deliver", "zip_make", "document_creer", "document_modifier"}


class _Cloisonne:
    def __init__(self, outil, workspace: Path, personne: str, role: str):
        self._outil, self._ws, self._qui, self._role = outil, Path(workspace), personne, role

    def __getattr__(self, nom):                          # nom, description, parameters, permission, schema()…
        return getattr(self._outil, nom)

    def _refus(self, chemin: str) -> dict:
        return {"error": f"Accès refusé à « {chemin} » : ce n'est pas un de tes projets ou de tes fichiers. "
                         "Tu peux travailler dans tes projets (projets/…) et dans les fichiers que tu as envoyés."}

    async def execute(self, **kw: Any) -> dict:
        nom = self._outil.name
        if nom in PAR_SLUG:
            slug = str(kw.get("slug", "")).strip().strip("/")
            meta = (await project_acl.load()).get(slug)
            if nom == "project_init" and meta is None:
                pass                                       # nouveau projet : il sera à elle
            elif not slug or not project_acl.can_open(meta, self._qui, self._role):
                return self._refus(f"projets/{slug}")
        elif nom in LECTURE or nom in ECRITURE:
            chemin = str(kw.get("path", "") or ".")
            propre = acces.normaliser(self._ws, chemin)
            racine_dossier = propre is not None and propre.count("/") == 0 and propre in ("projets", *acces.DOSSIERS_PERSONNELS)
            if racine_dossier and nom != "fs_list":
                return self._refus(chemin)                 # parcourir tous les projets ou tous les dépôts : non
            if not await acces.autorise(self._ws, chemin, self._qui, self._role, ecriture=nom in ECRITURE):
                return self._refus(chemin)

        res = await self._outil.execute(**kw)

        if isinstance(res, dict) and "error" not in res:
            if nom == "fs_list" and isinstance(res.get("entries"), list):
                res["entries"] = await acces.filtrer_liste(self._ws, str(kw.get("path", ".")), res["entries"], self._qui, self._role)
            if nom == "project_init":
                slug = str(kw.get("slug", "")).strip().strip("/")
                if slug and (await project_acl.load()).get(slug) is None:
                    await project_acl.set_owner(slug, self._qui)
            if nom in LIVRAISON and isinstance(res.get("path"), str):
                acces.enregistrer(self._ws, res["path"], self._qui)
        return res


class RegistreCloisonne:
    def __init__(self, base, workspace: Path, personne: str, role: str):
        self._base, self._ws, self._qui, self._role = base, workspace, personne, role

    def get(self, name):
        outil = self._base.get(name)
        if outil is None or name not in (LECTURE | ECRITURE | PAR_SLUG | LIVRAISON):
            return outil
        return _Cloisonne(outil, self._ws, self._qui, self._role)

    def names(self):
        return self._base.names()

    def schemas(self):
        return self._base.schemas()
