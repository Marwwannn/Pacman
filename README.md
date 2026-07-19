# Pac-Man — Back-end

Moteur de jeu Pac-Man écrit en Python (POO), exposé via une API REST + WebSocket.
Aucun rendu graphique ici : le back-end simule la partie et diffuse l'état, un
front quelconque se charge de l'affichage.

## Architecture

```
src/pacman/
├── core/          # modèle du jeu, sans dépendance externe
│   ├── geometry.py    Direction, Position
│   ├── maze.py        labyrinthe, murs, pastilles, tunnels
│   ├── entities.py    Entity, Pacman, Ghost
│   ├── pathfinding.py BFS / A* sur la grille
│   ├── rules.py       équilibrage : vitesses, points, progression
│   └── game.py        boucle de jeu, score, vies, états
├── ai/            # comportements des fantômes
├── api/           # FastAPI : REST, WebSocket, scores
└── mazes/         # labyrinthes au format texte
```

Deux principes structurent le projet :

- **`core/` ne connaît ni FastAPI ni le réseau.** Il est testable seul et avance
  par `tick()`.
- **Le moteur est déterministe.** Aucune horloge, aucun aléatoire non maîtrisé :
  un même état plus une même suite d'entrées redonne toujours le même résultat.
  Même l'errance des fantômes effrayés passe par un générateur pseudo-aléatoire
  propre à chaque fantôme. C'est ce qui rend une partie rejouable et testable.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -e ".[dev]"
```

## Lancer le serveur

```bash
pacman-server               # http://127.0.0.1:8000
```

Documentation interactive de l'API : http://127.0.0.1:8000/docs

## Tests

```bash
pytest                                  # 160 tests
pytest --cov=pacman --cov-report=term   # 97 % de couverture
ruff check src tests
```

## API

### REST

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/health` | état du serveur |
| `GET` | `/api/mazes/{name}` | plan d'un labyrinthe |
| `POST` | `/api/games` | créer une partie → plan + état initial |
| `GET` | `/api/games/{id}` | état courant (`?include_pellets=true` pour resynchroniser) |
| `POST` | `/api/games/{id}/tick` | avancer la simulation manuellement |
| `POST` | `/api/games/{id}/input` | `{"direction": "left"}` |
| `POST` | `/api/games/{id}/pause` · `/resume` | mettre en pause / reprendre |
| `DELETE` | `/api/games/{id}` | abandonner |
| `GET` · `POST` | `/api/scores` | meilleurs scores |

### WebSocket

`ws://host/ws/games/{id}` — le serveur fait tourner la partie à 60 ticks/s et
diffuse une image par tick.

À la connexion, le client reçoit un message `init` avec le plan et l'état
complet, puis des messages `state` ne contenant que l'état dynamique et les
événements. Les 240 pastilles ne transitent qu'une fois : le client retire
les siennes au vu des événements `pellet`.

Commandes du client :

```json
{"action": "input", "direction": "up"}
{"action": "pause"}
{"action": "resume"}
{"action": "ping"}
```

Une seule boucle de simulation par partie : ouvrir un second onglet ne fait pas
jouer la partie deux fois plus vite. Sans aucun abonné, plus rien ne tourne.

### Événements

`round_start`, `level_start`, `level_complete`, `pellet`, `power_pellet`,
`frightened`, `frightened_end`, `ghost_released`, `ghost_eaten`, `fruit_spawn`,
`fruit_eaten`, `fruit_gone`, `pacman_died`, `extra_life`, `wave`, `game_over`.

## Fidélité au jeu d'origine

- Les fantômes gardent la **règle myope** de 1980 : à chaque case ils prennent la
  direction qui réduit la distance à vol d'oiseau vers leur cible, sans voir les
  murs au-delà. C'est cette myopie qui les rend battables. Le demi-tour est
  interdit, sauf lors d'un changement de mode.
- Les quatre personnalités ne diffèrent que par **la case visée** : Blinky vise
  Pac-Man, Pinky quatre cases devant, Inky symétrise Blinky par rapport à deux
  cases devant Pac-Man, Clyde fuit vers son coin dès qu'il passe sous huit cases.
- Le **bug d'adressage de 1980** (cible décalée vers la gauche quand Pac-Man
  regarde en haut) est reproduit, et désactivable via `overflow_bug`.
- Exceptions assumées : rentrer à la maison et en sortir utilisent un vrai plus
  court chemin, la règle myope y bloquait les fantômes dans les impasses.

## Format de labyrinthe

Fichier texte, un caractère par case :

| Char | Signification        |
|------|----------------------|
| `#`  | mur                  |
| `.`  | pastille             |
| `o`  | super-pastille       |
| ` `  | couloir vide         |
| `P`  | départ Pac-Man       |
| `B`  | départ Blinky        |
| `I`  | départ Inky          |
| `Y`  | départ Pinky         |
| `C`  | départ Clyde         |
| `F`  | apparition des fruits (optionnel) |
| `-`  | porte de la maison   |
| `T`  | tunnel (téléporte)   |

Toutes les lignes doivent avoir la même largeur. La maison des fantômes est
déduite automatiquement par remplissage depuis la porte.

## Feuille de route

- [x] 1 — structure du projet
- [x] 2 — modèle : géométrie et labyrinthe
- [x] 3 — entités (Pac-Man, fantômes)
- [x] 4 — IA des fantômes (4 personnalités)
- [x] 5 — boucle de jeu, score, vies, modes
- [x] 6 — pathfinding BFS / A*
- [x] 7 — tests unitaires
- [x] 8 — API REST
- [x] 9 — WebSocket temps réel
- [x] 10 — fruits, meilleurs scores, polish

Back-end terminé. Pistes si le projet continue : niveaux supplémentaires,
mode multijoueur, ou fantômes « chasseurs » exploitant `pathfinding` pour un
mode difficile.
