"""Plugin d'exemple : un outil qui tire au sort (pile ou face, un dé, un nom dans une liste).
Copie ce dossier pour écrire le tien (voir PLUGINS.md), puis active-le dans Paramètres › Modules › Plugins."""
import random

from app.plugin_api import Permission, Tool

API = 1
NOM = "exemple"
DESCRIPTION = "Tirage au sort : pile ou face, dé, ou un nom au hasard dans une liste."
MOTS = ["pile ou face", "tire au sort", "tirage au sort", "lance un dé", "au hasard"]


class TirageTool(Tool):
    name = "exemple_tirage"
    description = "Tire au sort : pile ou face, un dé (faces = 6 par défaut), ou un élément au hasard dans une liste."
    parameters = {"type": "object", "properties": {
        "sorte": {"type": "string", "enum": ["piece", "de", "liste"], "description": "piece, de ou liste"},
        "faces": {"type": "integer", "description": "Nombre de faces du dé"},
        "choix": {"type": "array", "items": {"type": "string"}, "description": "Éléments parmi lesquels choisir"}},
        "required": ["sorte"]}
    permission = Permission.AUTO

    async def execute(self, sorte: str = "piece", faces: int = 6, choix: list | None = None, **_) -> dict:
        if sorte == "de":
            return {"resultat": random.randint(1, max(2, min(1000, int(faces or 6))))}
        if sorte == "liste":
            if not choix:
                return {"error": "Donne la liste des choix."}
            return {"resultat": random.choice([str(c) for c in choix])}
        return {"resultat": random.choice(["pile", "face"])}


def outils(contexte: dict) -> list[Tool]:
    return [TirageTool()]
