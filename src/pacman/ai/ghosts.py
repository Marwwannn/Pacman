"""Les quatre personnalites de fantomes.

Chaque fantome n'a qu'une seule chose qui lui est propre : la case qu'il vise
en mode poursuite. Tout le reste (choix de la direction, demi-tours, vitesse)
est mutualise dans `Ghost`. C'est ce decoupage qui donne au jeu d'origine
quatre comportements tres differents avec une seule regle de deplacement.
"""

from __future__ import annotations

from ..core.entities import Ghost, GhostContext
from ..core.geometry import Direction, Position
from ..core.maze import Maze


class PersonalityGhost(Ghost):
    """Fantome dote d'une personnalite, construit uniformement par le moteur.

    `build` evite au moteur d'avoir a savoir quelles sous-classes acceptent
    quelles options : chacune prend ce qui la concerne et ignore le reste.
    """

    COLOR = "#ffffff"

    @classmethod
    def build(
        cls, name: str, start: Position, corner: Position, *, overflow_bug: bool = True
    ) -> Ghost:
        return cls(name, start, corner)


class Blinky(PersonalityGhost):
    """Le rouge. Fonce droit sur Pac-Man : il vise sa case, sans detour.

    C'est le seul dont la cible est exactement la position du joueur, ce qui en
    fait le poursuivant direct — les autres se coordonnent autour de lui.
    """

    COLOR = "#ff0000"

    def chase_target(self, context: GhostContext) -> Position:
        return context.pacman_position


class LookaheadGhost(PersonalityGhost):
    """Fantome dont la cible se calcule devant Pac-Man, avec ou sans le bug d'origine."""

    LOOKAHEAD = 0

    def __init__(self, *args, overflow_bug: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.overflow_bug = overflow_bug

    @classmethod
    def build(
        cls, name: str, start: Position, corner: Position, *, overflow_bug: bool = True
    ) -> Ghost:
        return cls(name, start, corner, overflow_bug=overflow_bug)

    def pivot(self, context: GhostContext) -> Position:
        return ahead_of(
            context.pacman_position,
            context.pacman_direction,
            self.LOOKAHEAD,
            overflow_bug=self.overflow_bug,
        )


class Pinky(LookaheadGhost):
    """Le rose. Vise quatre cases devant Pac-Man, pour lui couper la route.

    Reproduit le debordement d'origine : quand Pac-Man regarde vers le haut,
    la cible part aussi de quatre cases vers la gauche. C'etait un bug de 1980,
    mais il fait partie du comportement attendu du jeu — d'ou l'option pour le
    desactiver.
    """

    COLOR = "#ffb8ff"
    LOOKAHEAD = 4

    def chase_target(self, context: GhostContext) -> Position:
        return self.pivot(context)


class Inky(LookaheadGhost):
    """Le cyan. Le plus imprevisible : sa cible depend aussi de Blinky.

    On prend la case a deux devant Pac-Man, puis on symetrise la position de
    Blinky par rapport a ce point. Inky tend donc a prendre Pac-Man en tenaille
    quand Blinky est proche, et part au loin quand Blinky est distant.
    """

    COLOR = "#00ffff"
    LOOKAHEAD = 2

    def chase_target(self, context: GhostContext) -> Position:
        pivot = self.pivot(context)
        blinky = context.blinky_position
        return Position(2 * pivot.x - blinky.x, 2 * pivot.y - blinky.y)


class Clyde(PersonalityGhost):
    """L'orange. Poursuit de loin, mais se defile des qu'il approche.

    Au-dela de huit cases il vise Pac-Man comme Blinky ; en deca il repart vers
    son coin. Il oscille donc autour du joueur sans jamais vraiment l'attaquer.
    """

    COLOR = "#ffb851"
    SHY_DISTANCE = 8

    def chase_target(self, context: GhostContext) -> Position:
        pacman = context.pacman_position
        if self.position.squared_distance(pacman) >= self.SHY_DISTANCE**2:
            return pacman
        return self.scatter_target


def ahead_of(
    position: Position,
    direction: Direction,
    distance: int,
    *,
    overflow_bug: bool = True,
) -> Position:
    """Case situee `distance` cases devant `position`.

    Avec `overflow_bug`, la direction UP decale aussi vers la gauche : c'est le
    debordement d'adressage du jeu de 1980, conserve pour la fidelite.
    """
    target = Position(
        position.x + direction.dx * distance,
        position.y + direction.dy * distance,
    )
    if overflow_bug and direction is Direction.UP:
        target = Position(target.x - distance, target.y)
    return target


#: Ordre de sortie de la maison, et classe associee a chaque nom de depart.
GHOST_TYPES: dict[str, type[PersonalityGhost]] = {
    "blinky": Blinky,
    "pinky": Pinky,
    "inky": Inky,
    "clyde": Clyde,
}


def scatter_targets(maze: Maze) -> dict[str, Position]:
    """Coins de repli. Chaque fantome tourne autour du sien en mode scatter.

    Les cibles sont volontairement hors du labyrinthe : inatteignables, elles
    forcent le fantome a boucler dans le coin au lieu de s'arreter.
    """
    right = maze.width - 3
    bottom = maze.height - 1
    return {
        "blinky": Position(right, 0),
        "pinky": Position(2, 0),
        "inky": Position(maze.width - 1, bottom),
        "clyde": Position(0, bottom),
    }


def create_ghosts(maze: Maze, *, overflow_bug: bool = True) -> list[Ghost]:
    """Instancie les fantomes declares dans le labyrinthe, dans l'ordre de sortie."""
    corners = scatter_targets(maze)
    ghosts: list[Ghost] = []

    for name, ghost_type in GHOST_TYPES.items():
        start = maze.ghost_starts.get(name)
        if start is None:
            continue
        corner = corners.get(name, Position(0, 0))
        ghosts.append(ghost_type.build(name, start, corner, overflow_bug=overflow_bug))

    return ghosts
