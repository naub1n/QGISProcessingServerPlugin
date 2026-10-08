# QGIS Processing Server Manager (plugin)

Plugin QGIS pour gérer, depuis une interface graphique, les **jobs** et **planifications**
d'un serveur QGIS Processing exposé en OGC API Processes.

## Fonctionnalités

- **Jobs** : liste (`GET /oapi/jobs`), détail/résultat (`GET /oapi/jobs/{jobId}`),
  création (`POST /oapi/processes/qgis/execution`, avec outputs / response / subscriber optionnels).
- **Planifications** : liste (`GET /schedules`), détail (`GET /schedules/{id}`),
  création (`POST /schedules`, déclencheurs `cron` / `interval` / `date`), puis, par ligne,
  boutons **Activer** (`POST /schedules/{id}/enable`), **Désactiver** (`POST /schedules/{id}/disable`)
  et **Supprimer** (`DELETE /schedules/{id}`, avec confirmation). Le nom d'une planification
  n'accepte que lettres, chiffres, `_` et `-`.
- **Fenêtre d'exécution d'un algorithme** : un bouton « Exécuter sur le serveur ... », à droite de
  « Exécuter comme processus de lot ... », ouvre un menu **Exécuter une seule fois** (crée un job)
  ou **Planifier** (ouvre la création de planification pré-remplie). Les couches sont transmises
  par leur source : elle doit être accessible depuis le serveur.
- **Publication d'un modèle** : dans la boîte à outils Processing, le menu contextuel d'un modèle
  (fournisseurs « Modèles » et « Projet ») propose **Publier le modèle sur le serveur ...**. Le plugin
  vérifie si le modèle existe déjà (demande de confirmation avant remplacement), contrôle que tous
  ses algorithmes sont disponibles sur le worker (`GET /worker/algorithms`, sinon la publication est
  annulée), puis envoie le fichier `.model3` (`POST /worker/models`). Le modèle est ensuite
  exécutable via `model:<nom>`.
- Le process est toujours `qgis` : il n'est pas modifiable.
- **Vérifications serveur** avant création : présence de l'algorithme et, pour `model:<nom>`,
  du fichier `.model3` — voir [docs/server-checks.md](docs/server-checks.md).
- **Authentification** : Traefik (OIDC) protège l'API. Le plugin s'appuie sur une
  configuration d'authentification QGIS (OAuth2 ou jeton Bearer), avec en secours des
  en-têtes personnalisés (`Authorization`, `Cookie`). Une redirection vers le
  fournisseur d'identité est détectée et signalée.

## Installation (développement)

Lier ou copier le dossier `qgis_processing_server_manager/` dans le dossier des plugins du profil QGIS
(`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` sous Windows), puis activer le plugin.
L'URL du serveur et l'authentification se règlent dans l'onglet **Connexion**.
