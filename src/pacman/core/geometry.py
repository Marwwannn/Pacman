"""Primitives geometriques : positions sur la grille et directions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class Position:
    """Coordonnees entieres sur la grille du labyrinthe (colonne, ligne)."""

    x: int
    y: int

    def moved(self, direction: Direction) -> Position:
        """Nouvelle position apres un pas dans `direction`."""
        return Position(self.x + direction.dx, self.y + direction.dy)

    def manhattan(self, other: Position) -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def squared_distance(self, other: Position) -> int:
        """Distance euclidienne au carre.

        Le Pac-Man original compare les distances sans jamais extraire la racine :
        on garde la meme convention, c'est exact et sans flottants.
        """
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def __str__(self) -> str:  # pragma: no cover - confort de debug
        return f"({self.x}, {self.y})"


class Direction(Enum):
    """Les quatre directions cardinales, plus l'immobilite."""

    UP = (0, -1)
    LEFT = (-1, 0)
    DOWN = (0, 1)
    RIGHT = (1, 0)
    NONE = (0, 0)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]

    @property
    def opposite(self) -> Direction:
        if self is Direction.NONE:
            return Direction.NONE
        return _OPPOSITES[self]

    @classmethod
    def moves(cls) -> tuple[Direction, ...]:
        """Directions de deplacement reelles, dans l'ordre de priorite d'origine.

        En cas d'egalite de distance, un fantome choisit haut, puis gauche,
        puis bas, puis droite. Cet ordre est la source de plusieurs
        comportements emblematiques du jeu : il ne doit pas changer.
        """
        return (cls.UP, cls.LEFT, cls.DOWN, cls.RIGHT)


_OPPOSITES = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}
