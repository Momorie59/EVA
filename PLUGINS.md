# Plugins : ajouter des outils à EVA

Un plugin ajoute des outils à EVA **sans toucher à son code** : il survit aux mises à jour et peut se partager.

## Principe

- Un plugin est un dossier `plugins/<nom>/` à la racine d'EVA, avec un fichier `plugin.py`.
- Le dossier `plugins/` est monté **en lecture seule** dans eva-core : EVA ne peut ni écrire ni modifier un plugin.
- Rien n'est chargé tant que l'administrateur ne l'a pas activé : **Paramètres › Modules › Plugins**.
- Un plugin cassé est ignoré, avec son erreur affichée ; il n'empêche jamais EVA de démarrer.
- Un plugin est du code Python qui tourne avec les droits d'EVA : n'installe que ceux dont tu as lu le code.

## Écrire un plugin

Copie `plugins/exemple/` sous un autre nom (lettres minuscules, chiffres, `_`), puis adapte `plugin.py` :

```python
from app.plugin_api import Permission, Tool      # la SEULE importation d'EVA autorisée : API stable

API = 1                                            # version de plugin_api visée
NOM = "arrosage"
DESCRIPTION = "Pilote l'arrosage du jardin."
MOTS = ["arrosage", "arroser", "jardin"]           # mots qui font proposer ces outils au modèle

class ArroserTool(Tool):
    name = "arrosage_lancer"                       # commence toujours par « <nom>_ »
    description = "Lance l'arrosage pendant N minutes."   # c'est ce que lit le modèle : sois précis
    parameters = {"type": "object", "properties": {"minutes": {"type": "integer"}}, "required": ["minutes"]}
    permission = Permission.CONFIRM                # AUTO (lecture, sans risque), CONFIRM (demande l'accord) ou FORBIDDEN

    async def execute(self, minutes: int = 10, **_) -> dict:
        ...                                        # appelle ton matériel, une API…
        return {"ok": True, "minutes": minutes}    # en cas d'échec normal : {"error": "explication"}, jamais d'exception

def outils(contexte: dict) -> list[Tool]:          # contexte : {"workspace": Path, "dossier": Path du plugin}
    return [ArroserTool()]
```

Règles :
- `execute` est asynchrone et renvoie un dictionnaire sérialisable en JSON.
- Pour un appel réseau, utilise `httpx.AsyncClient` (déjà installé) avec un délai (`timeout=`).
- Les dépendances Python en plus ne sont pas installées automatiquement : reste sur la bibliothèque standard et ce
  qu'EVA a déjà (`httpx`, `pillow`, `numpy`…).

## Installer et activer

1. Dépose le dossier dans `plugins/` à côté de `docker-compose.yml` (sur le NAS : `/home/eva/eva/plugins/`).
2. Paramètres › Modules › Plugins : **↻ Relire**, puis active-le. Ses outils sont disponibles tout de suite.
3. Pour un nouveau fichier `plugin.py` modifié : **↻ Relire** suffit.

## Compatibilité

`app.plugin_api` (classes `Tool` et `Permission`, constante `API_VERSION`) ne change pas sans nouvelle version
d'API annoncée dans `CHANGELOG.md`. Le reste du code d'EVA peut changer à chaque version : ne l'importe pas.
