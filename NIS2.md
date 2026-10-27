# EVA et NIS2 — ce qui est vérifié, ce qui reste à ta charge

La directive européenne **NIS2** (2022/2555) impose à certaines organisations (entités « essentielles » ou « importantes ») des mesures de
cybersécurité (art. 21) et une notification des incidents (art. 23). EVA est un assistant installé chez toi : **elle n'est pas certifiée et ce
document n'est pas un avis juridique**. Il décrit ce qu'EVA contrôle ou applique, pour t'aider à tenir une base de sécurité sérieuse.

Où : **Paramètres › Sécurité & données › « Sécurité — contrôle NIS2 »** (administrateur). Le bouton « Télécharger le rapport » produit un
fichier Markdown à garder ou à montrer.

## Correspondance avec l'article 21 §2

| Lettre | Mesure | Ce qu'EVA fait / contrôle |
|---|---|---|
| a | Analyse des risques | Le contrôle donne un score et la liste des points à corriger, avec le correctif pour chacun. |
| b | Gestion des incidents | Journal d'accès (1 an), alerte Telegram après 5 échecs de connexion, **registre d'incidents** avec échéances 24 h / 72 h / 1 mois. |
| c | Continuité, sauvegardes | Vérifie qu'une sauvegarde récente existe ; rappelle la copie hors du NAS (règle 3-2-1) — EVA ne peut pas la vérifier. |
| d | Chaîne d'approvisionnement | Signale les fournisseurs cloud configurés (100 % local = rien d'envoyé) et rappelle que skills et MCP sont du code tiers. |
| e | Vulnérabilités | Présence du scanner réseau ; rappel des mises à jour (système du NAS, Docker, EVA) à faire chaque mois. |
| f | Évaluation de l'efficacité | Le contrôle se relance à volonté et s'exporte. |
| g | Hygiène de base | Surface exposée minimale (Caddy 8443 uniquement). |
| h | Cryptographie | Détecte si la page est servie en HTTPS ; en-têtes de sécurité HTTP ; mots de passe hachés (scrypt), clés stockées localement. |
| i | Contrôle d'accès | Connexion obligatoire, rôles/profils (administrateur, adulte, adolescent, enfant, invité), moindre privilège, politique de mot de passe (12 caractères). |
| j | Authentification multifacteur | **Double authentification TOTP** par compte ; le contrôle signale les administrateurs qui n'en ont pas. |

## Réglages (fichier `.env`)

- `EVA_MIN_PASSWORD` : longueur minimale des nouveaux mots de passe (12 par défaut, 8 minimum). Les comptes existants ne sont pas touchés.
- `EVA_AUDIT_DAYS` : durée de conservation du journal (365 par défaut, 30 minimum).

## Registre d'incidents (art. 23)

Pour un incident important : **alerte précoce sous 24 h**, **notification sous 72 h**, **rapport final sous un mois** à l'autorité compétente
de ton pays (en France : l'ANSSI / CERT-FR). EVA ne contacte aucune autorité : elle calcule les échéances à partir de l'heure de détection, te
montre celles qui sont dépassées et garde l'historique (dates auxquelles tu as coché chaque étape).

## Ce qu'EVA ne peut pas faire pour toi

Formation des personnes, politique écrite, gestion des fournisseurs, correctifs du système d'exploitation du NAS, copie des sauvegardes hors
site, pare-feu du routeur, notification effective aux autorités. Si tu es réellement une entité soumise à NIS2, fais-toi accompagner.
