# Claimd

Vérifie en un coup d'œil si un pseudo est libre sur plusieurs plateformes.
Tu tapes `yexo`, Claimd interroge toutes les plateformes **en parallèle** et affiche,
pour chacune : **libre**, **pris** ou **incertain**, avec la fiabilité de la vérification.

Claimd tourne **sur ta machine** : tu clones, tu lances une commande, tu ouvres
`http://localhost:8000`. Pas de service hébergé, pas de compte, aucun coût.

> **Avancement** : étapes 1 à 3 faites (socle FastAPI + frontend, checker Twitch,
> route agrégée). YouTube, Instagram, TikTok, la case Gmail et le travail de design et
> d'animation arrivent dans les étapes suivantes (voir [Feuille de route](#feuille-de-route)).

---

## Démarrage rapide

### Avec Docker (une commande)

```bash
git clone https://github.com/Yexo0/Claimd.git
```

```bash
cd Claimd
```

```bash
cp .env.example .env
```

Renseigne tes clés Twitch dans `.env` (facultatif, voir [Clés Twitch](#clés-twitch)), puis :

```bash
docker compose up -d --build
```

Ouvre <http://localhost:8000>. Pour arrêter : `docker compose down`.

Le port est publié sur `127.0.0.1` uniquement : l'app n'est pas visible depuis ton réseau.
Pour changer de port, mets `PORT=9000` dans `.env`.

### Sans Docker

Il faut **Python 3.10 ou plus récent**.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

(Sous Windows : `.venv\Scripts\activate`.)

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
python -m claimd
```

Ouvre <http://localhost:8000>. `python -m claimd` lit `HOST` et `PORT` dans `.env`
(par défaut `127.0.0.1:8000`). Tu peux aussi lancer uvicorn directement, par exemple avec
le rechargement automatique pendant le développement :

```bash
uvicorn claimd.main:app --reload
```

---

## Clés Twitch

Twitch est vérifié par son **API officielle (Helix)**, qui demande les identifiants
d'une application Twitch. C'est gratuit et ça prend deux minutes :

1. Connecte-toi sur <https://dev.twitch.tv/console/apps>
   (Twitch exige que l'authentification à deux facteurs soit activée sur ton compte).
2. **Register Your Application** :
   - *Name* : ce que tu veux, par exemple `claimd-local-tonpseudo` (le nom doit être unique sur Twitch) ;
   - *OAuth Redirect URLs* : `http://localhost` (non utilisé, mais obligatoire) ;
   - *Category* : `Other` ;
   - *Client Type* : **Confidential**.
3. Ouvre l'application créée (**Manage**), copie le **Client ID**, puis clique **New Secret**
   et copie le secret.
4. Colle-les dans `.env` :

   ```dotenv
   TWITCH_CLIENT_ID=ton_client_id
   TWITCH_CLIENT_SECRET=ton_secret
   ```

5. Redémarre Claimd.

Sans clés, l'app fonctionne quand même : la carte Twitch affiche « incertain » avec
un message qui indique quoi configurer. `.env` est dans `.gitignore`, tes clés ne
partent jamais dans le dépôt.

---

## Comment ça marche

```
navigateur ──GET /check/yexo──▶ FastAPI ──┬─▶ checkers/twitch.py    (API Helix)
   ▲                                      ├─▶ checkers/youtube.py   (étape 4)
   │                                      ├─▶ checkers/instagram.py (étape 4)
   └──────────── JSON agrégé ◀────────────┴─▶ checkers/tiktok.py    (étape 4)
```

- Un navigateur ne peut pas interroger ces sites directement (CORS) : les vérifications
  tournent donc côté serveur, dans le backend **FastAPI** (Python, `httpx` en async).
- Le même serveur sert le frontend statique (`frontend/`) : un seul process, un seul port.
- Tous les checkers partent **en même temps** (`asyncio.gather`). Chacun a son propre
  **timeout de 5 s** et sa propre gestion d'erreurs : une plateforme qui plante, bloque ou
  ne répond pas donne une carte « incertain », jamais une erreur 500 pour toute la page.
- Comme chacun lance Claimd chez soi, les requêtes partent de **ton** IP :
  pas de serveur central qui se fait bannir, pas de quota partagé.

### Arborescence

```
claimd/
  main.py          routes HTTP + service du frontend
  runner.py        exécution parallèle, timeouts, résumé
  models.py        modèle Result commun
  config.py        lecture de .env
  http.py          client HTTP partagé
  checkers/
    __init__.py    registre des plateformes (ordre d'affichage)
    base.py        Platform : métadonnées + construction des résultats
    twitch.py
frontend/          HTML/CSS/JS vanilla, sans étape de build
tests/
```

---

## Plateformes et fiabilité

Toutes les plateformes ne se vérifient pas avec la même certitude. Chaque résultat
indique `available` (`true` / `false` / `null`), la méthode utilisée et une fiabilité
(`high` / `medium` / `low`). **Un résultat incertain n'est jamais deviné** : en cas de
doute, `available` vaut `null`.

| Plateforme | Méthode | Fiabilité | État |
|---|---|---|---|
| Twitch | API officielle Helix (`GET /helix/users`) | haute | ✅ disponible |
| YouTube | Sonde de `youtube.com/@pseudo` (200 = pris, 404 = libre) | moyenne | étape 4 |
| Instagram | Sonde de la page profil, au mieux | faible | étape 4 |
| TikTok | Sonde de la page profil, au mieux | faible | étape 4 |
| Gmail | Aucune : non vérifiable | — | étape 5 |

### Twitch

- **Règles du pseudo** : 4 à 25 caractères, lettres, chiffres et `_`, sans `_` en
  première position. Un pseudo hors règles est signalé « invalide ici » sans appel réseau.
- **Pris** : l'API renvoie un compte actif à ce nom. Certain.
- **Libre** : l'API ne renvoie aucun compte. Limite connue : Helix ne renvoie pas les
  comptes **suspendus ou désactivés**, et Twitch garde un temps les noms libérés
  récemment. « Libre » veut donc dire « aucun compte actif » ; la carte le précise.
- Le jeton d'application est mis en cache jusqu'à son expiration et renouvelé
  automatiquement s'il est refusé.
- Clés absentes ou refusées, quota dépassé, réseau coupé, réponse illisible :
  « incertain » avec la raison.

### Gmail (à venir, étape 5)

Savoir si une adresse Gmail existe **n'est pas faisable de façon fiable et légitime** :
pas d'API publique, le sondage SMTP est bloqué par Gmail, et le formulaire d'inscription
est protégé par captcha et interdit à l'automatisation par les conditions de Google.
Claimd n'implémentera donc **ni énumération SMTP ni scraping** du formulaire : la case
Gmail sera affichée « non vérifiable », avec l'explication au survol.

---

## API

La documentation interactive est sur <http://localhost:8000/docs>.

### `GET /check/{username}`

Lance tous les checkers en parallèle et renvoie un résultat par plateforme, dans
l'ordre d'affichage. Les espaces autour du pseudo et un `@` initial sont retirés.

```json
{
  "username": "yexo",
  "elapsed_ms": 231,
  "summary": { "total": 1, "checkable": 1, "available": 0, "taken": 1, "uncertain": 0, "invalid": 0 },
  "results": [
    {
      "platform": "twitch",
      "label": "Twitch",
      "username": "yexo",
      "status": "taken",
      "available": false,
      "method": "helix_api",
      "reliability": "high",
      "reason": null,
      "detail": "Compte « Yexo », créé en 2016.",
      "url": "https://www.twitch.tv/yexo",
      "elapsed_ms": 228
    }
  ]
}
```

| `status` | `available` | Sens |
|---|---|---|
| `available` | `true` | Le pseudo semble libre |
| `taken` | `false` | Un compte l'utilise |
| `uncertain` | `null` | Blocage, timeout, captcha, réponse ambiguë : pas de conclusion |
| `invalid` | `null` | La plateforme refuserait ce pseudo (longueur, caractères) |
| `unverifiable` | `null` | Aucune méthode légitime de vérification (Gmail) |

Pour un résultat `uncertain`, `reason` donne la cause : `timeout`, `network_error`,
`rate_limited`, `not_configured`, `auth_failed`, `unexpected_response`, `ambiguous`,
`internal_error`.

Le résumé « libre sur X/N plateformes » correspond à `summary.available` / `summary.checkable`.

Une entrée vide ou de plus de 64 caractères renvoie `422` avec un message lisible.

### `GET /platforms`

Liste des plateformes (nom, méthode, fiabilité, règles, clés configurées ou non) :
le frontend s'en sert pour afficher ses cartes avant toute recherche.

### `GET /health`

`{"status": "ok"}`, utilisé par le healthcheck Docker.

---

## Ajouter ou retirer une plateforme

1. Crée `claimd/checkers/maplateforme.py` :

   ```python
   from claimd.checkers.base import Platform
   from claimd.models import Result

   PLATFORM = Platform(
       id="maplateforme",
       label="Ma Plateforme",
       method="http_probe",
       reliability="medium",
       profile_url="https://example.com/{username}",
       rules="3 à 30 caractères : lettres, chiffres et _.",
   )

   async def check(username: str) -> Result:
       ...
       return PLATFORM.taken(username)  # ou available(), uncertain(reason=...), invalid()
   ```

2. Ajoute le module au tuple `CHECKERS` de `claimd/checkers/__init__.py`.
   L'ordre du tuple est l'ordre d'affichage. Pour retirer une plateforme, enlève-la du tuple.

Le runner s'occupe du timeout, des exceptions et du temps de réponse : un checker n'a
qu'à décider quel résultat s'applique. Utilise `claimd.http.get_client()` pour les
requêtes HTTP.

---

## Déployer sur un VPS

Le dépôt peut aussi tourner sur un serveur :

- dans `docker-compose.yml`, remplace `"127.0.0.1:${PORT:-8000}:8000"` par
  `"${PORT:-8000}:8000"`, ou mieux, garde `127.0.0.1` et place un reverse proxy HTTPS
  (Caddy, nginx, Traefik) devant ;
- Claimd n'a **pas d'authentification** : une instance publique peut être utilisée par
  n'importe qui. Protège-la (authentification basique sur le reverse proxy, VPN…).

> ⚠️ **Avertissement** : toutes les vérifications partent alors de l'IP du serveur.
> Avec beaucoup de trafic, Instagram et TikTok finiront par la limiter ou la bloquer
> (les cartes passeront en « incertain »), et les IP de datacenter sont souvent
> traitées plus sévèrement qu'une connexion résidentielle. L'usage local reste le
> mode recommandé.

---

## Tests

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

Les tests n'appellent aucun service réel : les réponses de Twitch sont simulées avec
`respx` (pseudo pris, libre, jeton expiré, clés refusées, quota, timeout, réponses
malformées…), et l'API est testée avec des checkers factices (plantage, blocage,
ordre des résultats, entrées invalides).

---

## Feuille de route

1. ✅ Socle : FastAPI qui sert le frontend, structure `checkers/`, modèle `Result`, Docker.
2. ✅ Checker Twitch de bout en bout.
3. ✅ `GET /check/{username}` : tous les checkers en parallèle, JSON agrégé.
4. YouTube (sonde du handle), puis Instagram et TikTok (au mieux, gestion propre des blocages).
5. Gmail : case « non vérifiable » avec explication.
6. Design et animations : skeletons, apparition en cascade, micro-animations par état
   (GSAP), copie du pseudo, `prefers-reduced-motion`.

---

## Limites et usage responsable

- Claimd fait **une requête par plateforme et par recherche**, depuis ta connexion, comme
  si tu ouvrais la page toi-même. Pas de contournement de captcha ni de rotation d'IP.
- Les conditions d'utilisation des plateformes s'appliquent : garde un usage personnel
  et raisonnable.
- Un résultat « libre » n'est pas une réservation : le pseudo peut être pris entre la
  vérification et ton inscription, et une plateforme peut réserver des noms qu'elle
  n'expose pas publiquement.

Les logos des plateformes proviennent de [Simple Icons](https://simpleicons.org) (CC0)
et appartiennent à leurs propriétaires respectifs ; ils ne servent qu'à les identifier.
