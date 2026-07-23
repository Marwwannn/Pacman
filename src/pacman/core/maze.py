"""Labyrinthe : chargement depuis un fichier texte et interrogation de la grille.

Le labyrinthe est immuable. Ce qui se consomme en cours de partie (les pastilles
mangees) est suivi par `Game`, pas ici : on peut ainsi rejouer un niveau sans
recharger le fichier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from pathlib import Path

from .geometry import Direction, Position


class Tile(Enum):
    """Nature statique d'une case."""

    WALL = "#"
    EMPTY = " "
    PELLET = "."
    POWER_PELLET = "o"
    DOOR = "-"
    TUNNEL = "T"


#: Caracteres marquant un point de depart. La case sous-jacente est un couloir vide.
SPAWN_CHARS = {
    "P": "pacman",
    "B": "blinky",
    "Y": "pinky",
    "I": "inky",
    "C": "clyde",
}

#: Case ou apparaissent les fruits. Optionnelle : a defaut, ce sera le depart de Pac-Man.
FRUIT_CHAR = "F"


#: Noms de labyrinthe acceptes par `Maze.load`. Volontairement etroit : ni
#: separateur de chemin, ni point, donc aucune sortie du dossier possible.
NAME_PATTERN = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,31}\Z")


class MazeError(ValueError):
    """Fichier de labyrinthe invalide."""


@dataclass(frozen=True, slots=True)
class Maze:
    """Grille statique du niveau."""

    tiles: tuple[tuple[Tile, ...], ...]
    pacman_start: Position
    ghost_starts: dict[str, Position]
    pellets: frozenset[Position]
    power_pellets: frozenset[Position]
    doors: frozenset[Position]
    house: frozenset[Position] = field(default_factory=frozenset)
    fruit_start: Position | None = None

    # ------------------------------------------------------------------ dimensions

    @property
    def height(self) -> int:
        return len(self.tiles)

    @property
    def width(self) -> int:
        return len(self.tiles[0])

    def contains(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    # ------------------------------------------------------------------ lecture

    def tile_at(self, pos: Position) -> Tile:
        """Case a `pos`. Hors grille, tout est mur."""
        if not self.contains(pos):
            return Tile.WALL
        return self.tiles[pos.y][pos.x]

    def is_wall(self, pos: Position) -> bool:
        return self.tile_at(pos) is Tile.WALL

    def is_door(self, pos: Position) -> bool:
        return self.tile_at(pos) is Tile.DOOR

    def is_tunnel(self, pos: Position) -> bool:
        return self.tile_at(pos) is Tile.TUNNEL

    def in_house(self, pos: Position) -> bool:
        return pos in self.house

    def is_walkable(self, pos: Position, *, through_door: bool = False) -> bool:
        """Peut-on occuper `pos` ? La porte n'est franchissable que par les fantomes."""
        tile = self.tile_at(pos)
        if tile is Tile.WALL:
            return False
        if tile is Tile.DOOR:
            return through_door
        return True

    # ------------------------------------------------------------------ deplacement

    def wrap(self, pos: Position) -> Position:
        """Replie une position sortie par un tunnel sur le bord oppose."""
        if self.contains(pos):
            return pos
        return Position(pos.x % self.width, pos.y % self.height)

    def step(self, pos: Position, direction: Direction) -> Position:
        """Case atteinte depuis `pos` en allant vers `direction`, tunnels compris."""
        return self.wrap(pos.moved(direction))

    def neighbors(
        self, pos: Position, *, through_door: bool = False
    ) -> list[tuple[Direction, Position]]:
        """Cases adjacentes accessibles, dans l'ordre de priorite du jeu."""
        result = []
        for direction in Direction.moves():
            target = self.step(pos, direction)
            if self.is_walkable(target, through_door=through_door):
                result.append((direction, target))
        return result

    def is_intersection(self, pos: Position) -> bool:
        """Vrai si plus de deux couloirs se rejoignent : un fantome y decide."""
        return len(self.neighbors(pos)) > 2

    # ------------------------------------------------------------------ chargement

    @classmethod
    def from_text(cls, text: str) -> Maze:
        lines = [line.rstrip("\n") for line in text.splitlines() if line.strip()]
        if not lines:
            raise MazeError("labyrinthe vide")

        widths = {len(line) for line in lines}
        if len(widths) != 1:
            raise MazeError(f"lignes de largeurs differentes : {sorted(widths)}")

        rows: list[tuple[Tile, ...]] = []
        pacman_start: Position | None = None
        fruit_start: Position | None = None
        ghost_starts: dict[str, Position] = {}
        pellets: set[Position] = set()
        power_pellets: set[Position] = set()
        doors: set[Position] = set()

        for y, line in enumerate(lines):
            row: list[Tile] = []
            for x, char in enumerate(line):
                pos = Position(x, y)
                if char == FRUIT_CHAR:
                    fruit_start = pos
                    row.append(Tile.EMPTY)
                    continue
                if char in SPAWN_CHARS:
                    name = SPAWN_CHARS[char]
                    if name == "pacman":
                        pacman_start = pos
                    else:
                        ghost_starts[name] = pos
                    row.append(Tile.EMPTY)
                    continue

                try:
                    tile = Tile(char)
                except ValueError as exc:
                    raise MazeError(
                        f"caractere inconnu {char!r} en ligne {y}, colonne {x}"
                    ) from exc

                if tile is Tile.PELLET:
                    pellets.add(pos)
                elif tile is Tile.POWER_PELLET:
                    power_pellets.add(pos)
                elif tile is Tile.DOOR:
                    doors.add(pos)
                row.append(tile)
            rows.append(tuple(row))

        if pacman_start is None:
            raise MazeError("aucun depart Pac-Man ('P') dans le labyrinthe")
        if not ghost_starts:
            raise MazeError("aucun depart de fantome dans le labyrinthe")

        tiles = tuple(rows)
        house = _find_house(tiles, doors)
        return cls(
            tiles=tiles,
            pacman_start=pacman_start,
            ghost_starts=ghost_starts,
            pellets=frozenset(pellets),
            power_pellets=frozenset(power_pellets),
            doors=frozenset(doors),
            house=frozenset(house),
            fruit_start=fruit_start or pacman_start,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> Maze:
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def load(cls, name: str = "classic") -> Maze:
        """Charge un labyrinthe livre avec le paquet (`src/pacman/mazes/`).

        `name` designe un fichier du paquet, jamais un chemin. Le nom vient de
        l'exterieur (corps de requete, parametre d'URL) : sans cette garde,
        `../../secret` sortirait du dossier et le parseur renverrait le contenu
        du fichier, caractere par caractere, dans ses messages d'erreur.
        """
        if not NAME_PATTERN.match(name):
            raise MazeError(f"nom de labyrinthe invalide : {name!r}")
        try:
            source = resources.files("pacman.mazes").joinpath(f"{name}.txt")
            return cls.from_text(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MazeError(f"labyrinthe inconnu : {name!r}") from exc

    # ------------------------------------------------------------------ debug

    def render(self) -> str:  # pragma: no cover - confort de debug
        return "\n".join("".join(tile.value for tile in row) for row in self.tiles)


def _find_house(tiles: tuple[tuple[Tile, ...], ...], doors: set[Position]) -> set[Position]:
    """Cases de la maison des fantomes : l'espace clos derriere la porte.

    On part de la case situee juste sous chaque porte et on remplit tant qu'on
    reste sur des cases libres, sans jamais traverser la porte elle-meme.
    """
    height = len(tiles)
    width = len(tiles[0])
    inside: set[Position] = set()
    stack = [Position(door.x, door.y + 1) for door in doors]

    while stack:
        pos = stack.pop()
        if pos in inside or pos in doors:
            continue
        if not (0 <= pos.x < width and 0 <= pos.y < height):
            continue
        if tiles[pos.y][pos.x] is Tile.WALL:
            continue
        inside.add(pos)
        for direction in Direction.moves():
            stack.append(pos.moved(direction))

    return inside
