from enum import Enum


class Permission(str, Enum):
    """Niveau de permission d'un outil.

    AUTO      — exécuté sans rien demander (lecture, actions sans risque)
    CONFIRM   — le Harness met la conversation en pause et attend une
                confirmation explicite du client avant d'exécuter
    FORBIDDEN — jamais exécuté, même si le modèle le demande
    """

    AUTO = "auto"
    CONFIRM = "confirm"
    FORBIDDEN = "forbidden"
