---
name: resume-de-page-web
description: Résume une page web ou un article à partir de son adresse (URL), avec les points clés et ce qu'il faut retenir.
---
# Résumer une page web

Quand l'utilisateur donne une URL (ou demande de résumer un article) :

1. Appelle `web_fetch` avec l'URL. Si la page est vide ou en erreur, dis-le clairement et propose une autre source via `web_search`.
2. Rédige en français :
   - **En une phrase** : de quoi parle la page.
   - **Points clés** : 3 à 6 puces, fidèles au texte (pas d'invention).
   - **À retenir** : ce qui est actionnable ou important pour l'utilisateur.
3. Termine par l'URL source. Si le texte est long et tronqué, précise que le résumé porte sur le début de la page.
