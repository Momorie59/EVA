# Partager les projets d'EVA sur le réseau (Windows / Mac / Linux)

Tout se fait dans EVA : page **Projets › Partage réseau**.

1. Choisis un mot de passe (ou garde celui proposé) et clique **Activer le partage**. Le premier démarrage télécharge le serveur de partage (Samba, ~1 minute).
2. La page affiche l'adresse à utiliser :
   - **Windows** : Explorateur → barre d'adresse → `\\ADRESSE-DU-NAS\projets`, utilisateur `eva` et ton mot de passe.
   - **Mac / Linux** : `smb://ADRESSE-DU-NAS/projets`.
3. Tu y retrouves un dossier par projet. Ce que tu enregistres apparaît chez EVA (et dans la page Projets) ; ce qu'EVA écrit apparaît chez toi.

Pour arrêter : **Désactiver**. Les fichiers restent dans EVA. Le partage se relance tout seul si EVA redémarre.

## Si ça ne démarre pas
- **« Le port 445 est déjà utilisé »** : le service SMB d'OpenMediaVault occupe ce port. Soit tu le désactives dans OMV (Services › SMB/CIFS), soit tu choisis un autre port (ex. 4445) dans la page. Avec un autre port, Windows 11 récent se connecte avec la commande affichée dans la page (`net use … /TCPPORT:4445`) ; Mac/Linux avec `smb://ADRESSE:4445/projets`.
- **Docker refuse** : EVA a besoin de l'accès Docker (déjà utilisé pour le bac à sable).
- Le partage est protégé par mot de passe, réservé au réseau local : ne l'expose pas sur Internet.

NFS n'est pas proposé (il demande des droits spéciaux sur le NAS) ; le partage SMB fonctionne aussi sous Linux.
