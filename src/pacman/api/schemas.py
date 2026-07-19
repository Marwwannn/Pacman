"""Modeles d'echange de l'API.

Ces schemas sont la frontiere du back-end : ils traduisent l'etat interne en
donnees stables pour le client. Le moteur peut evoluer sans casser le front
tant que cette traduction est maintenue.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.entities import Ghost, Pacman
from ..core.game import Event, Game
from ..core.geometry import Direction
from ..core.maze import Maze


class DirectionInput(BaseModel):
    """Entree du joueur."""

    direction: str = Field(description="up, down, left, right ou none")

    def to_direction(self) -> Direction:
        try:
            return Direction[self.direction.strip().upper()]
        except KeyError as exc:
            valides = ", ".join(d.name.lower() for d in Direction)
            raise ValueError(f"direction inconnue : {self.direction!r} (attendu : {valides})") from exc


class NewGameRequest(BaseModel):
    """Parametres de creation d'une partie."""

    maze: str = Field(default="classic", description="nom du labyrinthe a charger")
    level: int = Field(default=1, ge=1, le=256)
    lives: int = Field(default=3, ge=1, le=99)
    overflow_bug: bool = Field(
        default=True,
        description="reproduire le bug de ciblage de 1980 pour Pinky et Inky",
    )


class TickRequest(BaseModel):
    """Avance manuelle de la simulation."""

    ticks: int = Field(default=1, ge=1, le=600)


class MazeModel(BaseModel):
    """Plan statique du niveau, envoye une seule fois."""

    name: str
    width: int
    height: int
    rows: list[str]
    pellets: list[tuple[int, int]]
    power_pellets: list[tuple[int, int]]

    @classmethod
    def from_maze(cls, maze: Maze, name: str) -> MazeModel:
        return cls(
            name=name,
            width=maze.width,
            height=maze.height,
            rows=maze.render().splitlines(),
            pellets=sorted((p.x, p.y) for p in maze.pellets),
            power_pellets=sorted((p.x, p.y) for p in maze.power_pellets),
        )


class PacmanModel(BaseModel):
    x: int
    y: int
    direction: str
    energized: bool

    @classmethod
    def from_entity(cls, pacman: Pacman) -> PacmanModel:
        return cls(
            x=pacman.position.x,
            y=pacman.position.y,
            direction=pacman.direction.name.lower(),
            energized=pacman.energized,
        )


class GhostModel(BaseModel):
    name: str
    x: int
    y: int
    direction: str
    mode: str
    color: str
    vulnerable: bool

    @classmethod
    def from_entity(cls, ghost: Ghost) -> GhostModel:
        return cls(
            name=ghost.name,
            x=ghost.position.x,
            y=ghost.position.y,
            direction=ghost.direction.name.lower(),
            mode=ghost.mode.value,
            color=getattr(ghost, "COLOR", "#ffffff"),
            vulnerable=ghost.is_vulnerable,
        )


class EventModel(BaseModel):
    type: str
    payload: dict = {}

    @classmethod
    def from_event(cls, event: Event) -> EventModel:
        return cls(type=event.type, payload=event.payload)


class GameStateModel(BaseModel):
    """Etat dynamique d'une partie, rafraichi a chaque tick."""

    id: str
    state: str
    tick: int
    level: int
    score: int
    lives: int
    remaining_pellets: int
    frightened: bool
    pacman: PacmanModel
    ghosts: list[GhostModel]
    #: Pastilles restantes. Absentes par defaut : trop lourdes a envoyer a chaque
    #: image, le client les retire lui-meme au vu des evenements.
    pellets: list[tuple[int, int]] | None = None
    power_pellets: list[tuple[int, int]] | None = None
    events: list[EventModel] = []

    @classmethod
    def from_game(
        cls,
        game: Game,
        game_id: str,
        *,
        events: list[Event] | None = None,
        include_pellets: bool = False,
    ) -> GameStateModel:
        return cls(
            id=game_id,
            state=game.state.value,
            tick=game.tick_count,
            level=game.level,
            score=game.score,
            lives=game.lives,
            remaining_pellets=game.remaining_pellets,
            frightened=game.frightened,
            pacman=PacmanModel.from_entity(game.pacman),
            ghosts=[GhostModel.from_entity(g) for g in game.ghosts],
            pellets=sorted((p.x, p.y) for p in game.pellets) if include_pellets else None,
            power_pellets=(
                sorted((p.x, p.y) for p in game.power_pellets) if include_pellets else None
            ),
            events=[EventModel.from_event(e) for e in (events or [])],
        )


class NewGameResponse(BaseModel):
    """Reponse a la creation : le plan et l'etat initial, en un aller-retour."""

    maze: MazeModel
    state: GameStateModel
