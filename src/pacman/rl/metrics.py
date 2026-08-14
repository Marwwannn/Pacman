"""Mesures statiques d'un labyrinthe, calculees une fois et partagees.

Rien ici ne depend d'une partie en cours : ce sont des proprietes du plan. Les
calculer a chaque episode couterait plus cher que tout le reste de
l'apprentissage reuni, d'ou le cache par labyrinthe.

Le chiffre qui structure tout le paquet est ici : sur les ~300 cases
praticables du labyrinthe classique, seules ~34 offrent un vrai choix. Decider
a chaque tick produirait donc plus de 95 % de decisions nulles.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import inf
from typing import Iterable

from ..core.geometry import Direction, Position
from ..core.maze import Maze
from ..core.pathfinding import distance_map


@dataclass(frozen=True, slots=True)
class MazeMetrics:
    """Distances et topologie d'un labyrinthe."""

    maze: Maze
    #: Cases atteignables par Pac-Man depuis son depart (la maison est exclue).
    walkable: frozenset[Position]
    #: Cases ou au moins trois couloirs se rejoignent.
    decision_tiles: frozenset[Position]
    #: Distance reelle entre toutes les paires de cases praticables.
    distances: dict[Position, dict[Position, int]]
    #: Plus grande distance entre deux cases : sert a normaliser les features.
    max_distance: int

    # ------------------------------------------------------------------ distances

    def distance(self, start: Position, goal: Position) -> float:
        """Distance reelle entre deux cases, `inf` si l'une est inatteignable."""
        return self.distances.get(start, {}).get(goal, inf)

    def nearest(self, start: Position, targets: Iterable[Position]) -> float:
        """Distance a la plus proche des `targets`, `inf` s'il n'y en a aucune.

        Parcours en largeur arrete au premier but rencontre : sur des pastilles
        denses il s'arrete en quelques cases, la ou parcourir les 240 cibles
        dans la table de distances serait systematiquement plus long.
        """
        goals = targets if isinstance(targets, (set, frozenset)) else set(targets)
        if not goals:
            return inf
        if start in goals:
            return 0.0

        seen = {start}
        queue: deque[tuple[Position, int]] = deque([(start, 0)])
        while queue:
            pos, depth = queue.popleft()
            for _, neighbor in self.maze.neighbors(pos):
                if neighbor in seen:
                    continue
                if neighbor in goals:
                    return float(depth + 1)
                seen.add(neighbor)
                queue.append((neighbor, depth + 1))
        return inf

    @staticmethod
    def proximity(distance: float) -> float:
        """Proximite dans [0, 1] : 1 sur la case meme, 0 pour une cible absente.

        Preferee a la distance normalisee pour les features. Deux raisons :
        une cible absente y vaut 0, donc elle ne contribue pas au total au lieu
        de se confondre avec le biais ; et la courbe se resserre la ou tout se
        joue — passer de deux a une case d'un fantome compte bien plus que
        passer de vingt a dix-neuf.
        """
        if distance == inf:
            return 0.0
        return 1.0 / (1.0 + max(0.0, distance))

    # ------------------------------------------------------------------ topologie

    def options(self, tile: Position, heading: Direction) -> list[Direction]:
        """Directions praticables depuis `tile` sans faire demi-tour.

        C'est ce qui separe un vrai choix d'un couloir : zero option = impasse,
        une seule = couloir force, deux ou plus = point de decision.
        """
        back = heading.opposite
        return [
            direction
            for direction, _ in self.maze.neighbors(tile)
            if direction is not back
        ]

    def is_decision(self, tile: Position, heading: Direction) -> bool:
        return len(self.options(tile, heading)) >= 2

    def exits(self, tile: Position) -> int:
        """Nombre de couloirs partant de `tile`, demi-tour compris."""
        return len(self.maze.neighbors(tile))


_CACHE: dict[str, MazeMetrics] = {}


def metrics_for(maze: Maze) -> MazeMetrics:
    """Mesures de `maze`, calculees au premier appel puis reutilisees."""
    key = _signature(maze)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    metrics = _build(maze)
    _CACHE[key] = metrics
    return metrics


def _signature(maze: Maze) -> str:
    """Empreinte du plan. `render()` seul ne suffit pas : il perd les departs."""
    starts = ",".join(f"{name}:{pos.x}x{pos.y}" for name, pos in sorted(maze.ghost_starts.items()))
    return f"{maze.render()}|{maze.pacman_start.x}x{maze.pacman_start.y}|{starts}"


def _build(maze: Maze) -> MazeMetrics:
    reachable = distance_map(maze, maze.pacman_start)
    walkable = frozenset(reachable)

    distances: dict[Position, dict[Position, int]] = {}
    longest = 1
    for tile in walkable:
        table = {
            target: value
            for target, value in distance_map(maze, tile).items()
            if target in walkable
        }
        distances[tile] = table
        longest = max(longest, max(table.values(), default=1))

    decision_tiles = frozenset(tile for tile in walkable if len(maze.neighbors(tile)) >= 3)

    return MazeMetrics(
        maze=maze,
        walkable=walkable,
        decision_tiles=decision_tiles,
        distances=distances,
        max_distance=longest,
    )
