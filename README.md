# Claimd

Vérifie en un coup d'œil si un pseudo est libre sur **Twitch, YouTube, Instagram et TikTok**.
Tu tapes `yexo`, Claimd interroge toutes les plateformes **en parallèle** et affiche,
carte par carte, **libre**, **pris** ou **incertain**, avec la fiabilité de chaque vérification.

Claimd tourne **sur ta machine** : tu clones, tu lances une commande, tu ouvres
`http://localhost:8000`. Pas de service hébergé, pas de compte, aucun coût.

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

Il faut **Python 3.10 ou plus récent**. Aucun Node ni étape de build : le frontend est servi tel quel.

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
(par défaut `127.0.0.1:8000`). Pour développer avec rechargement automatique :

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
un message qui indique quoi configurer. Les autres plateformes n'ont besoin d'aucune clé.
`.env` est dans `.gitignore`, tes clés ne partent jamais dans le dépôt.

---

## Plateformes et fiabilité

Toutes les plateformes ne se vérifient pas avec la même certitude. Chaque résultat
indique `available` (`true` / `false` / `null`), la méthode utilisée et une fiabilité
(`high` / `medium` / `low`). **Un résultat incertain n'est jamais deviné** : blocage,
captcha, mur de connexion, timeout ou réponse ambiguë donnent `available: null`.

| Plateforme | Méthode | « Pris » | « Libre » | Quand c'est « incertain » |
|---|---|---|---|---|
| **Twitch** | API officielle Helix | haute | haute | clés absentes/refusées, quota, réseau |
| **YouTube** | `HEAD youtube.com/@pseudo` | moyenne | moyenne | redirection hors YouTube (consentement, vérification), 429 |
| **Instagram** | page profil, au mieux | moyenne | faible | mur de connexion (très fréquent), challenge, page sans indice |
| **TikTok** | données publiques de la page profil | moyenne | faible | captcha, page sans données, code inconnu |
| **Gmail** | aucune : **non vérifiable** | — | — | toujours, sauf pseudo contraire aux règles de Gmail |

Chaque carte affiche la fiabilité sous forme de jauge ; un survol (ou un focus clavier)
explique comment la plateforme est vérifiée et ses limites.

### Twitch : fiable

- `POST id.twitch.tv/oauth2/token` (jeton d'application, gardé en cache jusqu'à
  expiration, renouvelé une fois s'il est refusé), puis `GET api.twitch.tv/helix/users?login=…`.
- **Pris** : l'API renvoie un compte actif à ce nom. **Libre** : aucun compte renvoyé.
- Limite : Helix ne renvoie pas les comptes **suspendus ou désactivés**, et Twitch garde
  un temps les noms libérés. « Libre » veut donc dire « aucun compte actif », la carte le précise.
- Règles : 4 à 25 caractères, lettres, chiffres et `_`, pas de `_` en premier.

### YouTube : moyen

- Une simple requête `HEAD` sur `youtube.com/@pseudo` : **200 = pris, 404 = libre**,
  sans télécharger la page (2 Mo). Un cookie de consentement « tout refuser » évite la
  page de consentement européenne.
- Une redirection vers un autre domaine (consentement, « trafic inhabituel ») donne « incertain ».
- Limite : un handle réservé, ou celui d'une chaîne supprimée, peut être refusé sans
  que rien ne soit visible.
- Règles : 3 à 30 caractères, lettres (75 langues) et chiffres, `_ - . ·` mais pas au début ni à la fin.

### Instagram : au mieux

- `GET instagram.com/pseudo/`, sans suivre les redirections.
- **Pris** seulement si la page décrit explicitement ce profil (lien `instagram://user?username=…`,
  titre « Nom (@pseudo) », JSON du profil). **Libre** seulement sur un vrai 404.
- Instagram redirige souvent les visiteurs non connectés vers sa page de connexion
  (systématiquement depuis une IP de datacenter, parfois depuis une connexion
  résidentielle). C'est un contrôle d'accès : Claimd **ne le contourne pas** et affiche
  « incertain » avec un lien pour vérifier soi-même.
- Règles : 1 à 30 caractères, lettres, chiffres, `_` et `.`, pas de point au début, à la
  fin ni deux à la suite.

### TikTok : au mieux

- `GET tiktok.com/@pseudo` : TikTok répond 200 pour tout, mais la page embarque un JSON
  public (`__UNIVERSAL_DATA_FOR_REHYDRATION__` → `webapp.user-detail`).
- `statusCode 0` avec le même `uniqueId` → **pris** ; `10222` (compte privé) → **pris**.
- `statusCode 10221` → **libre, fiabilité faible** : TikTok utilise ce code pour un pseudo
  inexistant *mais aussi* pour un compte banni ou supprimé, qui peut encore bloquer le nom.
- Pas de JSON (captcha, page de vérification) ou code inconnu → « incertain ».
- Règles : 2 à 24 caractères, lettres, chiffres, `_` et `.`, pas de point à la fin.

### Gmail : non vérifiable, volontairement

Savoir si une adresse Gmail existe **n'est pas faisable de façon fiable et légitime** :
pas d'API publique, le sondage SMTP est bloqué par Gmail, et le formulaire d'inscription
est protégé par captcha et interdit à l'automatisation par les conditions de Google.
Claimd n'implémente donc **ni énumération SMTP ni scraping** et **n'envoie rien à Google**.

La case Gmail affiche « non vérifiable » avec l'explication au survol. Seule exception,
locale et certaine : si le pseudo enfreint les règles publiques de Gmail (6 à 30 caractères,
lettres, chiffres et points), la case indique « invalide ici ». Gmail n'entre jamais dans
le compte « libre sur X/4 ».

---

## Comment ça marche

```
navigateur ──GET /check/yexo/stream──▶ FastAPI ──┬─▶ twitch     (API Helix)
   ▲                                             ├─▶ youtube    (HEAD du handle)
   │   une ligne JSON par plateforme,            ├─▶ instagram  (page profil)
   └──── dès qu'elle a répondu ◀─────────────────┼─▶ tiktok     (JSON de la page)
                                                 └─▶ gmail      (règles locales uniquement)
```

- Un navigateur ne peut pas interroger ces sites directement (CORS) : les vérifications
  tournent dans le backend **FastAPI** (`httpx` en async), qui sert aussi le frontend.
  Un seul process, un seul port.
- Tous les checkers partent **en même temps**. Chacun a son **timeout de 5 s** et sa
  propre gestion d'erreurs : une plateforme qui plante, bloque ou ne répond pas donne une
  carte « incertain », jamais une erreur 500 pour toute la page.
- Les résultats sont **diffusés au fil de l'eau** (NDJSON) : la carte Twitch s'affiche
  dès que Twitch a répondu, sans attendre la plateforme la plus lente.
- Les requêtes s'identifient honnêtement (`User-Agent: Claimd/<version> (+lien du dépôt)`),
  sans se faire passer pour un navigateur, et sans garder de cookies d'une vérification à l'autre.
- Comme chacun lance Claimd chez soi, les requêtes partent de **ton** IP : pas de serveur
  central qui se fait bannir, pas de quota partagé.

### Arborescence

```
claimd/
  main.py            routes HTTP (dont le streaming) + service du frontend
  runner.py          exécution parallèle, timeouts, flux, résumé
  models.py          modèle Result commun
  config.py          lecture de .env
  http.py            client HTTP partagé (User-Agent, sans cookies)
  checkers/
    __init__.py      registre des plateformes (ordre d'affichage)
    base.py          Platform : métadonnées + construction des résultats
    twitch.py  youtube.py  instagram.py  tiktok.py  gmail.py
frontend/
  index.html
  css/style.css      tokens, états des cartes, boucles d'attente
  js/app.js          orchestration (recherche, file de révélation, résumé, copie)
  js/api.js          client du flux NDJSON (repli sur la route agrégée)
  js/motion.js       toutes les animations GSAP
  js/tooltip.js      infobulles accessibles
  js/icons.js        logos + icônes d'état animables
  vendor/gsap/       GSAP 3 (non modifié)
  fonts/             Geist et Geist Mono
tests/
```

---

## Interface

- **Une seule page** : un grand champ central (bordure animée au focus), une carte par
  plateforme vérifiable, la case Gmail à part, et un résumé « `@yexo` est libre sur 2/4 plateformes »
  avec une barre segmentée et un bouton pour **copier le pseudo**.
- **Chargement** : chaque carte passe en squelette animé, avec un halo qui se propage
  d'une carte à l'autre et un anneau de progression.
- **Résultats** : les cartes se révèlent une par une, dans l'ordre où les plateformes
  répondent, avec un léger espacement. Une coche se dessine pour « libre », une croix
  pour « pris », un point d'interrogation pour « incertain ».
- **Couleur = sens** : vert libre, rouge pris, ambre incertain, gris invalide ou non
  vérifiable. Le violet est réservé à l'identité (champ, bouton, chargement).
- **Stabilité** : chaque zone a sa hauteur réservée, rien ne saute quand les résultats arrivent.
- **`prefers-reduced-motion`** : les grosses animations et les boucles sont coupées, les
  résultats s'affichent dès qu'ils arrivent, sans délai artificiel.
- Raccourcis : `/` pour revenir au champ, `Échap` pour le vider. L'URL garde le pseudo
  (`?u=yexo`) : une recherche se partage ou se relance au rechargement.

---

## API

La documentation interactive est sur <http://localhost:8000/docs>.

### `GET /check/{username}`

Lance tous les checkers en parallèle et renvoie un résultat par plateforme, dans
l'ordre d'affichage, une fois la plus lente terminée. Les espaces autour du pseudo et
un `@` initial sont retirés.

```json
{
  "username": "yexo",
  "elapsed_ms": 812,
  "summary": { "total": 5, "checkable": 4, "available": 2, "taken": 1, "uncertain": 1, "invalid": 1 },
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
`rate_limited`, `blocked`, `login_wall`, `not_configured`, `auth_failed`,
`unexpected_response`, `ambiguous`, `internal_error`.

Le résumé « libre sur X/N » correspond à `summary.available` / `summary.checkable`
(les plateformes non vérifiables ne comptent jamais dans N).

Une entrée vide ou de plus de 64 caractères renvoie `422` avec un message lisible.

### `GET /check/{username}/stream`

Mêmes vérifications, diffusées en **NDJSON** (une ligne JSON par événement) au fur et
à mesure que les plateformes répondent. C'est ce qu'utilise l'interface.

```
{"type": "start", "username": "yexo", "platforms": ["twitch", "youtube", "instagram", "tiktok", "gmail"]}
{"type": "result", "result": { …même forme que ci-dessus… }}
…
{"type": "done", "username": "yexo", "elapsed_ms": 812, "summary": { … }}
```

Si le client se déconnecte, les vérifications encore en cours sont annulées.

### `GET /platforms`

Liste des plateformes : nom, méthode, fiabilité, règles de pseudo, explication (`note`),
vérifiable ou non, clés configurées ou non. Le frontend s'en sert pour afficher ses
cartes avant toute recherche.

### `GET /health`

`{"status": "ok", "version": "…"}`, utilisé par le healthcheck Docker et l'indicateur « local » de l'interface.

---

## Ajouter ou retirer une plateforme

1. Crée `claimd/checkers/maplateforme.py` :

   ```python
   from claimd.checkers.base import Platform
   from claimd.http import PAGE_HEADERS, get_client
   from claimd.models import Result

   PLATFORM = Platform(
       id="maplateforme",
       label="Ma Plateforme",
       method="http_probe",
       reliability="medium",
       profile_url="https://example.com/{username}",
       rules="3 à 30 caractères : lettres, chiffres et _.",
       note="Comment c'est vérifié, et les limites (affiché au survol).",
   )

   async def check(username: str) -> Result:
       ...
       return PLATFORM.taken(username)  # ou available(), uncertain(reason=...), invalid()
   ```

2. Ajoute le module au tuple `CHECKERS` de `claimd/checkers/__init__.py`.
   L'ordre du tuple est l'ordre d'affichage. Pour retirer une plateforme, enlève-la du tuple.

Le runner s'occupe du timeout, des exceptions et du temps de réponse : un checker n'a
qu'à décider quel résultat s'applique. L'interface crée la carte toute seule (logo :
ajoute son tracé dans `frontend/js/icons.js`, sinon l'initiale est affichée).

---

## Déployer sur un VPS

Le dépôt peut aussi tourner sur un serveur :

- dans `docker-compose.yml`, remplace `"127.0.0.1:${PORT:-8000}:8000"` par
  `"${PORT:-8000}:8000"`, ou mieux, garde `127.0.0.1` et place un reverse proxy HTTPS
  (Caddy, nginx, Traefik) devant. Le flux NDJSON envoie déjà `X-Accel-Buffering: no`
  pour que nginx ne le mette pas en mémoire tampon ;
- Claimd n'a **pas d'authentification** : une instance publique peut être utilisée par
  n'importe qui. Protège-la (authentification basique sur le reverse proxy, VPN…).

> ⚠️ **Avertissement** : toutes les vérifications partent alors de l'IP du serveur.
> Avec beaucoup de trafic, Instagram et TikTok finiront par la limiter ou la bloquer
> (les cartes passeront en « incertain »), et les IP de datacenter sont souvent
> traitées plus sévèrement qu'une connexion résidentielle (Instagram y affiche quasiment
> toujours son mur de connexion). L'usage local reste le mode recommandé.

---

## Tests

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

Les tests n'utilisent **jamais le réseau** : toute connexion réelle est refusée pendant
la suite, et les réponses des plateformes sont simulées avec `respx` d'après la forme
des vraies réponses (pseudo pris, libre, mur de connexion, captcha, JSON TikTok, jeton
Twitch expiré, quotas, timeouts, réponses malformées…). L'API est testée avec des
checkers factices (plantage, blocage, ordre, flux NDJSON, entrées invalides).

---

## Limites et usage responsable

- Claimd fait **une requête par plateforme et par recherche**, depuis ta connexion, comme
  si tu ouvrais la page toi-même. Pas de contournement de captcha ni de mur de connexion,
  pas de rotation d'IP, pas d'usurpation de navigateur.
- Les conditions d'utilisation des plateformes s'appliquent : garde un usage personnel
  et raisonnable.
- Un résultat « libre » n'est pas une réservation : le pseudo peut être pris entre la
  vérification et ton inscription, et une plateforme peut réserver des noms qu'elle
  n'expose pas publiquement.

---

## Crédits et licences des ressources embarquées

- Logos des plateformes : [Simple Icons](https://simpleicons.org) (CC0). Les marques
  appartiennent à leurs propriétaires et ne servent qu'à les identifier.
- Animations : [GSAP](https://gsap.com) 3, fichier non modifié dans `frontend/vendor/gsap/`,
  sous la [licence standard sans frais de GreenSock](https://gsap.com/standard-license).
- Polices : [Geist et Geist Mono](https://github.com/vercel/geist-font) (SIL Open Font
  License 1.1, voir `frontend/fonts/OFL-Geist.txt`).
