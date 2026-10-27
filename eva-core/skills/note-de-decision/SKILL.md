---
name: note-de-decision
description: Consigne proprement une décision prise (choix technique, nom, architecture) dans la documentation du projet.
---
# Noter une décision

1. Vérifie que la décision est claire et prise (pas une hypothèse). Sinon demande confirmation en une question.
2. Identifie le projet concerné ; s'il n'existe pas, propose d'abord `project_init`.
3. Appelle `project_log_decision` avec : la décision en une phrase, **pourquoi** (1 à 2 phrases) et les alternatives écartées si on les connaît.
4. Si la décision change du code ou de la config, ajoute aussi `project_log_change`.
5. Confirme en une phrase à l'utilisateur ce qui a été noté et où.
