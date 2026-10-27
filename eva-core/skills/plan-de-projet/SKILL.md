---
name: plan-de-projet
description: Démarre un projet dans le workspace avec sa documentation Markdown (objectifs, décisions, tâches) à partir d'une idée.
---
# Plan de projet

1. Reformule l'idée en 2 phrases et déduis un nom court en minuscules (ex. `potager-connecte`).
2. Crée le projet avec `project_init` (nom et description). Ne le recrée pas s'il existe déjà : vérifie avec `fs_list` sur `projets/`.
3. Note les premiers choix évidents avec `project_log_decision` (un appel par décision claire seulement).
4. Écris une première liste de tâches dans `projets/<nom>/TODO.md` avec `fs_append` : 5 à 8 étapes concrètes, de la plus urgente à la moins urgente.
5. Résume à l'utilisateur ce que tu as créé et propose la première étape.
