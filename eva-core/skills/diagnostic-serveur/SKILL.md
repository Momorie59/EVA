---
name: diagnostic-serveur
description: Diagnostique un problème sur le serveur (lenteur, service en panne) en vérifiant ressources, conteneurs Docker et logs.
---
# Diagnostic du serveur

1. `system_stats` : repère CPU, mémoire ou disque au-dessus de 85 %.
2. `docker_ps` avec `all=true` : repère les conteneurs arrêtés ou qui redémarrent en boucle.
3. Pour chaque conteneur en cause, `docker_logs` (50 lignes) et cherche la première erreur, pas la dernière.
4. Conclus en trois lignes : **Constat**, **Cause probable**, **Action proposée**.
5. Ne redémarre jamais un conteneur sans l'avoir proposé : `docker_restart` demande de toute façon la confirmation de l'utilisateur.
