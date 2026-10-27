# EVA — assistante IA personnelle locale

EVA tourne sur ton NAS (Docker) et utilise les modèles Ollama du serveur IA. Tout reste sur ton réseau.

## Ce qu'EVA sait faire
- **Conversation** : texte, voix (micro, synthèse vocale) et image (caméra), historique par conversation.
- **Outils** : fichiers du workspace, projets documentés (README, décisions, journal), météo, web, Docker, Git, terminal, état du système.
- **Permissions** : AUTO (sans risque), CONFIRM (tu valides), FORBIDDEN (jamais).
- **Agents** : tâches autonomes à la demande ou planifiées (briefing du matin, recherche, veille système). Ils n'utilisent que des outils sûrs.
- **Skills** : savoir-faire en Markdown (`skills/<nom>/SKILL.md`) chargés quand ta demande y correspond ; installables depuis GitHub.
- **Documents et mémoire** : EVA indexe les fichiers texte du workspace (et de `/eva-docs` si monté) et tes conversations ; l'outil `docs_search` retrouve un passage par le sens.
- **Traces** : chaque tour et chaque exécution d'agent enregistre ses étapes, durées et tokens.

## Où EVA travaille
Son espace s'appelle `/eva-workspace`. Il ne voit rien d'autre sur le NAS, sauf si tu montes un dossier en lecture seule dans `/eva-docs`.

## Pages de l'interface
EVA (accueil), Conversation, Tableau de bord, Agents, Skills, Sources, Projets, Mémoire, Journal, Paramètres.
