from abc import ABC, abstractmethod
from typing import Optional


class Monitor(ABC):
    name: str
    interval_seconds: float = 60.0

    @abstractmethod
    async def check(self) -> Optional[str]:
        """Exécute une vérification. Retourne un texte de notification si
        quelque chose mérite d'être signalé, sinon None. Ne doit jamais
        lever d'exception "normale" — un souci d'accès, par exemple, doit
        juste faire retourner None (on ne veut pas spammer sur une erreur
        répétée), sauf si le monitor lui-même veut le signaler une fois."""
