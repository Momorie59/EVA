"""API stable des plugins d'EVA (version 1). Un plugin n'importe QUE ce module :

    from app.plugin_api import Tool, Permission, API_VERSION

Tout le reste du code d'EVA peut changer d'une version à l'autre ; ce module, non (sauf nouvelle version d'API,
annoncée dans CHANGELOG.md). Voir PLUGINS.md pour écrire un plugin."""
from .harness.permissions import Permission
from .harness.tools.base import Tool

API_VERSION = 1

__all__ = ["API_VERSION", "Permission", "Tool"]
