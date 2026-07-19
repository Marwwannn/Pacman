"""Parties en cours, cote serveur.

Le moteur est synchrone et n'a aucune notion de concurrence. C'est ici qu'on
l'entoure : une partie appartient a une session, chaque session est protegee
par un verrou, et les sessions inactives sont purgees pour qu'un client
disparu ne laisse pas une partie en memoire indefiniment.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from ..core.game import Event, Game
from ..core.geometry import Direction
from ..core.maze import Maze

#: Au-dela de ce delai sans activite, une partie est consideree abandonnee.
SESSION_TIMEOUT_SECONDS = 3600.0
#: Garde-fou memoire : refus de creer une partie au-dela de cette limite.
MAX_SESSIONS = 500


class SessionError(RuntimeError):
    """Operation impossible sur les sessions."""


@dataclass
class GameSession:
    """Une partie et son contexte serveur."""

    id: str
    game: Game
    maze_name: str
    last_seen: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Abonnes temps reel (voir le canal WebSocket).
    subscribers: set = field(default_factory=set)

    def touch(self, now: float) -> None:
        self.last_seen = now

    def tick(self, count: int = 1) -> list[Event]:
        return self.game.run(count)

    def set_direction(self, direction: Direction) -> None:
        self.game.set_direction(direction)


class SessionStore:
    """Registre des parties en cours, en memoire.

    Volontairement non persistant : une partie de Pac-Man n'a pas de valeur
    au-dela de la session du joueur. Seuls les scores le seront.
    """

    def __init__(
        self,
        *,
        timeout: float = SESSION_TIMEOUT_SECONDS,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self._sessions: dict[str, GameSession] = {}
        self._timeout = timeout
        self._max_sessions = max_sessions
        self._mazes: dict[str, Maze] = {}

    # ------------------------------------------------------------------ lecture

    def __len__(self) -> int:
        return len(self._sessions)

    def __contains__(self, game_id: str) -> bool:
        return game_id in self._sessions

    def get(self, game_id: str) -> GameSession:
        session = self._sessions.get(game_id)
        if session is None:
            raise KeyError(game_id)
        return session

    def all(self) -> list[GameSession]:
        return list(self._sessions.values())

    def maze(self, name: str) -> Maze:
        """Charge un labyrinthe, une seule fois : le plan est immuable et partageable."""
        if name not in self._mazes:
            self._mazes[name] = Maze.load(name)
        return self._mazes[name]

    # ------------------------------------------------------------------ ecriture

    def create(
        self,
        *,
        now: float,
        maze_name: str = "classic",
        level: int = 1,
        lives: int = 3,
        overflow_bug: bool = True,
    ) -> GameSession:
        self.purge(now)
        if len(self._sessions) >= self._max_sessions:
            raise SessionError("trop de parties en cours, reessayez plus tard")

        game = Game(
            self.maze(maze_name),
            level=level,
            lives=lives,
            overflow_bug=overflow_bug,
        )
        session = GameSession(id=uuid4().hex, game=game, maze_name=maze_name, last_seen=now)
        self._sessions[session.id] = session
        return session

    def delete(self, game_id: str) -> None:
        self._sessions.pop(game_id, None)

    def purge(self, now: float) -> list[str]:
        """Supprime les parties inactives. Renvoie les identifiants liberes."""
        expirees = [
            game_id
            for game_id, session in self._sessions.items()
            if not session.subscribers and now - session.last_seen > self._timeout
        ]
        for game_id in expirees:
            del self._sessions[game_id]
        return expirees
