"""« Que sais-tu sur moi ? » sous toutes ses formes doit être compris sans modèle."""
import pytest
from app.memoire import detect


@pytest.mark.parametrize("t", ["que sais tu sur moi", "Que sais-tu de moi ?", "qu'est-ce que tu sais sur moi", "Que retiens-tu de moi", "qu'as-tu retenu sur moi ?"])
def test_lister(t):
    assert detect(t) == {"action": "lister"}


@pytest.mark.parametrize("t", ["Que sais-tu sur la guerre", "que sais tu du Wi-Fi 7"])
def test_pas_une_demande_de_memoire(t):
    assert detect(t) is None


def test_reprendre_detecte():
    for t in ["relis mes conversations", "Eva, reprends toutes mes anciennes conversations", "analyse mes conversations passées"]:
        assert detect(t) == {"action": "reprendre"}
    assert detect("relis ce fichier") is None


def test_blocs_et_filtre():
    from app.memoire import blocs, parle_de_soi
    ms = ["J'habite à Lille depuis dix ans"] * 80
    assert all(parle_de_soi(m) for m in ms)
    b = blocs(ms)
    assert 1 < len(b) <= 40 and all(len(x) <= 1500 for x in b)
