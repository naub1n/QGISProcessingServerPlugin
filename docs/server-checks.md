# Endpoint de vérification côté serveur

Le plugin interroge cet endpoint avant de créer un job ou une planification, pour
s'assurer que l'algorithme (y compris un modèle `model:<nom>`) est bien enregistré
sur le serveur.

L'endpoint est sous le préfixe OGC API (`/oapi` par défaut) et est protégé
par Traefik OIDC comme le reste de l'API.

| Méthode | Chemin | Rôle |
|---------|--------|------|
| GET | `/oapi/worker/algorithms/{algorithm_id:path}` | L'algorithme est-il enregistré dans le registre Processing du serveur ? |

## Contrat

L'endpoint répond **toujours `200`** avec un corps JSON contenant un booléen
`exists`. Un `404` ne doit pas être utilisé pour dire « absent » : le plugin
interprète toute réponse autre que `200` + `exists` comme « vérification indisponible »
(l'utilisateur peut alors choisir d'envoyer quand même).

```jsonc
// GET /oapi/worker/algorithms/native:httprequest
{ "id": "native:httprequest", "exists": true, "name": "HTTP(S) POST/GET request" }

// GET /oapi/worker/algorithms/model:inconnu
{ "id": "model:inconnu", "exists": false }
```

## Règles appliquées par le plugin

1. `GET /worker/algorithms/{algorithm}` (le `:` n'est pas encodé). Les modèles
   (`model:<nom>`) sont vérifiés par ce même appel, il n'y a pas de vérification séparée.
2. `exists: false` → envoi bloqué. Vérification indisponible → confirmation demandée.
