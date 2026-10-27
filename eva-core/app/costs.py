"""Estimations de coût et d'énergie. Ce sont des ORDRES DE GRANDEUR, pas des mesures :
- énergie = puissance moyenne du GPU × temps passé dans le modèle ;
- « équivalent cloud » = tokens × tarifs publics approximatifs (USD par million de tokens)."""
from .config import settings

# (nom, $ / M tokens en entrée, $ / M tokens en sortie) — tarifs approximatifs, à ajuster.
CLOUD_PRICES = [
    ("Modèle cloud économique", 0.25, 1.25),
    ("Modèle cloud intermédiaire", 3.0, 15.0),
    ("Modèle cloud haut de gamme", 15.0, 75.0),
]


def energy_kwh(llm_ms: int) -> float:
    return settings.gpu_watts * (llm_ms / 1000.0) / 3_600_000.0


def local_cost_eur(llm_ms: int) -> float:
    return energy_kwh(llm_ms) * settings.kwh_price


def cloud_equivalents(prompt_tokens: int, completion_tokens: int) -> list[dict]:
    return [
        {"name": n, "usd": round(prompt_tokens / 1e6 * pin + completion_tokens / 1e6 * pout, 4)}
        for n, pin, pout in CLOUD_PRICES
    ]
