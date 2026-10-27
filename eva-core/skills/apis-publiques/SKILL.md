---
name: apis-publiques
description: Interroger des API publiques gratuites sans clé (pays, devises, jours fériés, recettes, Wikipédia, livres, soleil, ISS…) avec api_get, ou en trouver d'autres avec api_search.
---
# API publiques

1. Si l'une des API ci-dessous convient, appelle-la directement avec `api_get` (jamais de clé, jamais de secret dans l'adresse).
2. Sinon `api_search` (catalogue de ~2000 API ; par défaut sans clé), lis sa documentation avec `web_fetch`, puis `api_get`.
3. Réponse trop longue ? Ajoute `fields`, `limit` ou un filtre. Réponds en français, en quelques lignes, et cite la source.
4. Une API qui exige une clé (`key` ≠ aucune) : dis-le à l'utilisateur, ne l'invente pas.

## Prêtes à l'emploi (sans clé)
- Pays : `https://restcountries.com/v3.1/name/france?fields=name,capital,population,languages,currencies`
- Taux de change : `https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,GBP`
- Jours fériés : `https://date.nager.at/api/v3/PublicHolidays/2026/FR`
- Wikipédia (résumé) : `https://fr.wikipedia.org/api/rest_v1/page/summary/Dauphin`
- Recettes : `https://www.themealdb.com/api/json/v1/1/search.php?s=Arrabiata`
- Cocktails : `https://www.thecocktaildb.com/api/json/v1/1/search.php?s=margarita`
- Livres : `https://openlibrary.org/search.json?q=le+petit+prince&limit=3`
- Lever / coucher du soleil : `https://api.sunrise-sunset.org/json?lat=46.7&lng=5.5&formatted=0`
- Position de la station spatiale : `http://api.open-notify.org/iss-now.json`
- Âge / prénom, blagues, faits : voir `api_search`.
