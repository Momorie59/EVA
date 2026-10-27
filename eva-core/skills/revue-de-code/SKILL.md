---
name: revue-de-code
description: Relit un fichier ou les changements Git en cours et signale bugs, risques de sécurité et améliorations, par ordre de gravité.
---
# Revue de code

1. Si l'utilisateur désigne un fichier : `fs_read`. Sinon regarde l'état avec `git_status` puis `git_diff`.
2. Lis tout avant de juger. Cherche d'abord ce qui peut casser : erreurs de logique, cas limites, gestion d'erreurs absente, secrets en dur, entrées non validées.
3. Réponds avec trois sections courtes :
   - **Problèmes sérieux** (à corriger avant de livrer) — avec le nom du fichier et la ligne ou la fonction.
   - **Risques et fragilités** (peuvent poser problème plus tard).
   - **Améliorations** (lisibilité, simplification), seulement si utiles.
4. Ne réécris pas tout le code : propose des correctifs ciblés. Si tout est correct, dis-le simplement.
