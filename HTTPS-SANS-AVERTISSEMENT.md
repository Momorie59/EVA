# Sans nom de domaine : installer le certificat une fois

Ouvre `https://<IP-du-NAS>:8443/api/https/install` (accepte l'avertissement une dernière fois) : la page propose un installateur Windows en un clic et les étapes pour Android, iPhone et Mac. Ensuite plus aucun avertissement sur cet appareil.

---

# HTTPS sans avertissement (vrai certificat)

Un navigateur ne fait confiance qu'aux certificats vendus par des autorités connues : pour une simple adresse IP (192.168.1.10) c'est impossible, d'où l'écran « Votre connexion n'est pas privée ». Pour qu'EVA s'ouvre comme n'importe quel site, il lui faut un **nom** et un certificat Let's Encrypt. Gratuit avec DuckDNS, sans ouvrir aucun port sur Internet.

## Une seule fois (5 minutes)

1. Va sur https://www.duckdns.org, connecte-toi, crée un nom, par exemple `eva-maison` (donne `eva-maison.duckdns.org`).
2. Sur la ligne de ce nom, mets dans « current ip » l'adresse du NAS : `192.168.1.10`, puis « update ip ». Copie aussi ton **token** (en haut de la page).
3. Sur le NAS :
   ```
   cd /home/eva/eva
   ./eva-https.sh domain eva-maison.duckdns.org TON_TOKEN
   ```
4. Attends 1 à 2 minutes, puis ouvre `https://eva-maison.duckdns.org:8443/` : cadenas normal, plus d'avertissement, sur tous les appareils (PC, téléphone, amis via Tailscale), sans rien installer. Le certificat se renouvelle tout seul.

## Si ça ne s'ouvre pas
- Certaines box bloquent les noms publics qui pointent vers une adresse privée (« protection contre le rebind DNS »). Dans ce cas, désactive cette protection pour `duckdns.org` dans la box.
- L'adresse IP continue de marcher (avec l'avertissement).
- `./eva-https.sh status` indique le mode actif ; `./eva-https.sh on` revient au certificat local.
