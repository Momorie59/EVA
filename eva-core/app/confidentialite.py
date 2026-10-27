"""Filtre avant de parler à voix haute (comme core/confidentialite.py de Jarvis).

Ce qu'EVA lit sur un haut-parleur s'entend dans toute la pièce, et une annonce dans toute la maison. Dernière barrière :
on masque les motifs évidemment sensibles (clés et jetons, mots de passe, numéros de carte, IBAN), et pour une annonce
(diffusée partout) aussi les adresses mail et les numéros de téléphone. Ce n'est pas un pare-feu parfait : la consigne
du modèle reste la première protection. L'écrit (interface, fenêtre du PC) n'est pas touché."""
import re

_SECRETS = [
    (re.compile(r"\b(?:eva(?:sat|mcp|rac|interne)_|sk-|ghp_|gho_|xox[bpa]-|AKIA|AIza)[A-Za-z0-9_\-]{8,}"), "une clé secrète"),
    (re.compile(r"\b(?=[A-Za-z0-9_\-]{28,}\b)(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{28,}\b"), "une longue clé"),
    (re.compile(r"(?i)\b(mot de passe|mdp|password|code secret|code pin|code d'accès)\s*(?:est|:|=)?\s*[«\"']?\S+"), r"\1 : masqué"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b"), "un IBAN"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "un numéro de carte"),
]
_ANNONCE = [
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "une adresse mail"),
    (re.compile(r"(?:\+\d{1,3}[\s.]?|\b0)\d(?:[\s.-]?\d{2}){4}\b"), "un numéro de téléphone"),
]


def caviarder(texte: str, annonce: bool = False) -> str:
    t = texte or ""
    for motif, rempl in _SECRETS + (_ANNONCE if annonce else []):
        t = motif.sub(rempl, t)
    return t
