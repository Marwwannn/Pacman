"""Description d'un couple (etat, action) par douze nombres.

L'etat brut du jeu est hors de portee d'une table : rien que la configuration
des pastilles vaut 2^244 possibilites. On decrit donc l'etat par quelques
quantites qui generalisent d'une partie a l'autre, et on apprend une valeur
lineaire sur ces quantites.

Toutes les features sont bornees dans [0, 1]. Ce n'est pas cosmetique : avec
des amplitudes heterogenes, un meme taux d'apprentissage ferait diverger un
poids pendant qu'un autre bouge a peine.

Les distances sont des distances reelles dans le labyrinthe, jamais a vol
d'oiseau : deux cases separees par un mur epais sont proches en ligne droite
et tres loin dans les faits.
"""

from __future__ import annotations

from math import inf

from ..core.entities import GhostMode
from ..core.game import Game
from ..core.geometry import Direction
from .metrics import MazeMetrics

#: Ordre des features. Sert aussi de nom des poids appris, ce qui rend un
#: modele entraine lisible : on voit ce que l'agent a retenu.
FEATURE_NAMES: tuple[str, ...] = (
    "biais",
    "mange_pastille",
    "mange_super_pastille",
    "mange_fruit",
    "proximite_pastille",
    "proximite_chasseur",
    "chasseurs_proches",
    "proximite_proie",
    "proximite_super_pastille",
    "issues",
    "demi_tour",
    "avancement",
)

#: Rayon en deca duquel un fantome est considere comme une menace immediate.
DANGER_RADIUS = 3


def extract(game: Game, action: Direction, metrics: MazeMetrics) -> tuple[float, ...]:
    """Vecteur de features du couple (etat courant, `action`)."""
    maze = game.maze
    tile = maze.step(game.pacman.position, action)

    hunters = []
    prey = []
    for ghost in game.ghosts:
        if not ghost.is_active:
            continue
        if ghost.mode is GhostMode.FRIGHTENED:
            prey.append(ghost.position)
        else:
            hunters.append(ghost.position)

    hunter_distances = [metrics.distance(tile, pos) for pos in hunters]
    nearest_hunter = min(hunter_distances, default=inf)
    close_hunters = sum(1 for value in hunter_distances if value <= DANGER_RADIUS)
    nearest_prey = min((metrics.distance(tile, pos) for pos in prey), default=inf)

    total_pellets = len(maze.pellets) + len(maze.power_pellets)
    eaten = total_pellets - game.remaining_pellets

    return (
        1.0,
        1.0 if tile in game.pellets else 0.0,
        1.0 if tile in game.power_pellets else 0.0,
        1.0 if game.fruit is not None and tile == game.fruit else 0.0,
        metrics.proximity(metrics.nearest(tile, game.pellets)),
        metrics.proximity(nearest_hunter),
        min(1.0, close_hunters / max(1, len(game.ghosts))),
        metrics.proximity(nearest_prey),
        metrics.proximity(metrics.nearest(tile, game.power_pellets)),
        min(1.0, len(metrics.options(tile, action)) / 3.0),
        1.0 if action is game.pacman.direction.opposite else 0.0,
        eaten / total_pellets if total_pellets else 1.0,
    )


def named(values: tuple[float, ...]) -> dict[str, float]:
    """Associe les features a leur nom. Pour l'inspection et les tests."""
    return dict(zip(FEATURE_NAMES, values, strict=True))
