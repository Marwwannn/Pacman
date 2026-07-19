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
│   └── game.py        boucle de jeu, score, vies, états
├── ai/            # comportements des fantômes
├── api/           # FastAPI : REST + WebSocket
└── mazes/         # labyrinthes au format texte
```

Le cœur (`core/`) ne connaît ni FastAPI ni le réseau : il est testable seul et
avance par `tick()` déterministe.

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

## Tests

```bash
pytest
```

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
| `-`  | porte de la maison   |
| `T`  | tunnel (téléporte)   |

## Feuille de route

- [x] 1 — structure du projet
- [ ] 2 — modèle : géométrie et labyrinthe
- [ ] 3 — entités (Pac-Man, fantômes)
- [ ] 4 — boucle de jeu, score, vies
- [ ] 5 — pathfinding
- [ ] 6 — IA des fantômes (scatter / chase / frightened)
- [ ] 7 — tests unitaires
- [ ] 8 — API REST
- [ ] 9 — WebSocket temps réel
- [ ] 10 — équilibrage et polish
