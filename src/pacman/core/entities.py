"""Entites mobiles : Pac-Man et les fantomes.

Le deplacement est discret, case par case. Chaque entite accumule sa vitesse
(en cases par tick) et avance d'une case des que l'accumulateur atteint 1 :
un fantome ralenti dans un tunnel avance donc moins souvent, sans que la
grille ait besoin de coordonnees flottantes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Protocol

from .geometry import Direction, Position
from .maze import Maze


class GhostContext(Protocol):
    """Ce qu'un fantome a le droit de savoir de la partie pour viser sa cible.

    Volontairement etroit : l'IA ne doit dependre que de ca, jamais de `Game`
    en entier. Cela garde `ai/` testable en isolation.
    """

    maze: Maze

    @property
    def pacman_position(self) -> Position: ...

    @property
    def pacman_direction(self) -> Direction: ...

    @property
    def blinky_position(self) -> Position: ...


class Entity(ABC):
    """Base commune a tout ce qui se deplace dans le labyrinthe."""

    def __init__(self, name: str, start: Position, speed: float = 1.0) -> None:
        self.name = name
        self.start = start
        self.position = start
        self.direction = Direction.NONE
        self.base_speed = speed
        self._progress = 0.0

    # ------------------------------------------------------------------ vitesse

    @property
    def speed(self) -> float:
        """Vitesse effective, en cases par tick. Les sous-classes la modulent."""
        return self.base_speed

    def effective_speed(self, maze: Maze) -> float:
        """Vitesse reelle sur la case occupee. Surchargee pour les ralentissements."""
        return self.speed

    def _consume_step(self, maze: Maze) -> bool:
        """Accumule la vitesse et indique si l'entite avance d'une case ce tick."""
        self._progress += self.effective_speed(maze)
        if self._progress < 1.0:
            return False
        self._progress -= 1.0
        return True

    # ------------------------------------------------------------------ deplacement

    @abstractmethod
    def plan_direction(self, context: GhostContext) -> Direction:
        """Direction choisie pour le prochain pas. Implementee par chaque sous-classe."""

    def can_enter(self, maze: Maze, pos: Position) -> bool:
        """Par defaut, la porte de la maison est infranchissable."""
        return maze.is_walkable(pos)

    def update(self, context: GhostContext) -> bool:
        """Fait avancer l'entite d'au plus une case. Renvoie True si elle a bouge."""
        maze = context.maze
        if not self._consume_step(maze):
            return False

        direction = self.plan_direction(context)
        if direction is Direction.NONE:
            self.direction = Direction.NONE
            return False

        target = maze.step(self.position, direction)
        if not self.can_enter(maze, target):
            return False

        self.direction = direction
        self.position = target
        return True

    def reset(self) -> None:
        """Replace l'entite a son point de depart."""
        self.position = self.start
        self.direction = Direction.NONE
        self._progress = 0.0

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"{type(self).__name__}({self.name!r}, {self.position}, {self.direction.name})"


class Pacman(Entity):
    """Pac-Man. Sa direction vient du joueur, avec memorisation de l'intention.

    Si le joueur demande un virage impossible (mur), la demande est conservee :
    des qu'une case le permet, le virage se fait. C'est ce qui rend le controle
    agreable plutot que frustrant.
    """

    BASE_SPEED = 0.8

    def __init__(self, start: Position, speed: float = BASE_SPEED) -> None:
        super().__init__("pacman", start, speed)
        self.desired_direction = Direction.NONE
        self.energized = False

    @property
    def speed(self) -> float:
        # Pac-Man est legerement plus rapide sous l'effet d'une super-pastille.
        return self.base_speed * (1.1 if self.energized else 1.0)

    def request(self, direction: Direction) -> None:
        """Enregistre l'intention du joueur ; elle s'appliquera des que possible."""
        self.desired_direction = direction

    def plan_direction(self, context: GhostContext) -> Direction:
        maze = context.maze
        if self.desired_direction is not Direction.NONE:
            target = maze.step(self.position, self.desired_direction)
            if self.can_enter(maze, target):
                return self.desired_direction

        # Virage impossible pour l'instant : on continue tout droit si on peut.
        if self.direction is not Direction.NONE:
            ahead = maze.step(self.position, self.direction)
            if self.can_enter(maze, ahead):
                return self.direction

        return Direction.NONE

    def reset(self) -> None:
        super().reset()
        self.desired_direction = Direction.NONE
        self.energized = False


class GhostMode(Enum):
    """Etat de comportement d'un fantome."""

    HOUSE = "house"          # enferme dans la maison, attend son tour
    LEAVING = "leaving"      # remonte vers la porte pour sortir
    SCATTER = "scatter"      # rejoint son coin, ignore Pac-Man
    CHASE = "chase"          # poursuit selon sa personnalite
    FRIGHTENED = "frightened"  # fuit, vulnerable
    EATEN = "eaten"          # yeux seuls, retourne a la maison


class Ghost(Entity):
    """Base des quatre fantomes.

    Regle de deplacement d'origine, respectee ici : a chaque case le fantome
    regarde les directions possibles sauf le demi-tour, et prend celle qui
    rapproche le plus de sa case cible (distance a vol d'oiseau). Il ne
    « voit » pas les murs au-dela : c'est cette myopie qui rend les fantomes
    battables. Le demi-tour n'est autorise que lors d'un changement de mode.
    """

    BASE_SPEED = 0.75
    FRIGHTENED_SPEED = 0.5
    EATEN_SPEED = 1.5
    TUNNEL_SPEED = 0.4

    def __init__(
        self,
        name: str,
        start: Position,
        scatter_target: Position,
        speed: float = BASE_SPEED,
    ) -> None:
        super().__init__(name, start, speed)
        self.scatter_target = scatter_target
        self.mode = GhostMode.HOUSE
        self.pending_reverse = False

    # ------------------------------------------------------------------ etat

    @property
    def is_vulnerable(self) -> bool:
        return self.mode is GhostMode.FRIGHTENED

    @property
    def is_active(self) -> bool:
        """Le fantome circule-t-il dans le labyrinthe (par opposition a la maison) ?"""
        return self.mode in (GhostMode.SCATTER, GhostMode.CHASE, GhostMode.FRIGHTENED)

    def set_mode(self, mode: GhostMode, *, reverse: bool = True) -> None:
        """Change de mode. Tout changement impose un demi-tour, comme dans l'original."""
        if mode is self.mode:
            return
        if reverse and self.is_active and mode in (GhostMode.SCATTER, GhostMode.CHASE, GhostMode.FRIGHTENED):
            self.pending_reverse = True
        self.mode = mode

    # ------------------------------------------------------------------ vitesse

    @property
    def speed(self) -> float:
        if self.mode is GhostMode.EATEN:
            return self.EATEN_SPEED
        if self.mode is GhostMode.FRIGHTENED:
            return self.FRIGHTENED_SPEED
        return self.base_speed

    def effective_speed(self, maze: Maze) -> float:
        """Vitesse tenant compte du ralentissement dans les tunnels."""
        if self.mode is not GhostMode.EATEN and maze.is_tunnel(self.position):
            return min(self.speed, self.TUNNEL_SPEED)
        return self.speed

    # ------------------------------------------------------------------ cible

    @abstractmethod
    def chase_target(self, context: GhostContext) -> Position:
        """Case visee en mode poursuite. C'est la personnalite du fantome."""

    def target_tile(self, context: GhostContext) -> Position:
        """Case visee selon le mode courant."""
        if self.mode is GhostMode.EATEN:
            return self.start
        if self.mode is GhostMode.SCATTER:
            return self.scatter_target
        if self.mode is GhostMode.CHASE:
            return self.chase_target(context)
        return self.position

    # ------------------------------------------------------------------ deplacement

    def can_enter(self, maze: Maze, pos: Position) -> bool:
        # Seuls les yeux qui rentrent, et un fantome qui sort, franchissent la porte.
        through_door = self.mode in (GhostMode.EATEN, GhostMode.LEAVING)
        return maze.is_walkable(pos, through_door=through_door)

    def plan_direction(self, context: GhostContext) -> Direction:
        maze = context.maze

        if self.mode is GhostMode.HOUSE:
            return Direction.NONE

        options = maze.neighbors(
            self.position,
            through_door=self.mode in (GhostMode.EATEN, GhostMode.LEAVING),
        )
        if not options:
            return Direction.NONE

        # Le demi-tour est interdit, sauf juste apres un changement de mode.
        if self.pending_reverse:
            self.pending_reverse = False
            reverse = self.direction.opposite
            if any(direction is reverse for direction, _ in options):
                return reverse

        forward = [
            (direction, target)
            for direction, target in options
            if direction is not self.direction.opposite
        ] or options

        if len(forward) == 1:
            return forward[0][0]

        target = self.target_tile(context)
        # `Direction.moves()` fixe l'ordre : a egalite, haut > gauche > bas > droite.
        return min(forward, key=lambda item: item[1].squared_distance(target))[0]

    def reset(self) -> None:
        super().reset()
        self.mode = GhostMode.HOUSE
        self.pending_reverse = False
