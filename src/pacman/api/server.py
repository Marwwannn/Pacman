"""API REST du back-end Pac-Man.

Le serveur ne fait qu'exposer le moteur : aucune regle de jeu ici. Chaque
requete prend le verrou de sa partie, ce qui garantit qu'un tick n'est jamais
entrelace avec une entree du joueur.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from ..core.maze import MazeError
from ..core.rules import TICKS_PER_SECOND
from .schemas import (
    DirectionInput,
    GameStateModel,
    MazeModel,
    NewGameRequest,
    NewGameResponse,
    TickRequest,
)
from .sessions import GameSession, SessionError, SessionStore

app = FastAPI(
    title="Pac-Man — back-end",
    version="0.1.0",
    summary="Moteur de jeu Pac-Man expose en REST et WebSocket",
)

# Le front est servi depuis une autre origine en developpement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.sessions = SessionStore()


def get_store(request: Request) -> SessionStore:
    return request.app.state.sessions


StoreDep = Annotated[SessionStore, Depends(get_store)]
GameId = Annotated[str, Path(description="identifiant de la partie")]


def get_session(store: SessionStore, game_id: str) -> GameSession:
    try:
        session = store.get(game_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"partie inconnue : {game_id}") from None
    session.touch(time.monotonic())
    return session


# ===================================================================== service


@app.get("/health", tags=["service"])
async def health(store: StoreDep) -> dict:
    """Etat du serveur. Utilise par les sondes de disponibilite."""
    return {
        "status": "ok",
        "games": len(store),
        "tick_rate": TICKS_PER_SECOND,
    }


@app.get("/api/mazes/{name}", response_model=MazeModel, tags=["service"])
async def read_maze(store: StoreDep, name: str = Path(description="nom du labyrinthe")) -> MazeModel:
    """Plan d'un labyrinthe, sans creer de partie."""
    try:
        return MazeModel.from_maze(store.maze(name), name)
    except MazeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ===================================================================== parties


@app.post(
    "/api/games",
    response_model=NewGameResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["parties"],
)
async def create_game(store: StoreDep, body: NewGameRequest = Body(default=NewGameRequest())) -> NewGameResponse:
    """Cree une partie et renvoie le plan avec l'etat initial.

    Le plan n'est envoye qu'ici : il est immuable, le client le garde.
    """
    try:
        session = store.create(
            now=time.monotonic(),
            maze_name=body.maze,
            level=body.level,
            lives=body.lives,
            overflow_bug=body.overflow_bug,
        )
    except MazeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SessionError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return NewGameResponse(
        maze=MazeModel.from_maze(session.game.maze, session.maze_name),
        state=GameStateModel.from_game(session.game, session.id, include_pellets=True),
    )


@app.get("/api/games/{game_id}", response_model=GameStateModel, tags=["parties"])
async def read_game(
    store: StoreDep,
    game_id: GameId,
    include_pellets: bool = Query(
        default=False,
        description="joindre les pastilles restantes (lourd : a reserver a une resynchronisation)",
    ),
) -> GameStateModel:
    """Etat courant de la partie."""
    session = get_session(store, game_id)
    async with session.lock:
        return GameStateModel.from_game(
            session.game, session.id, include_pellets=include_pellets
        )


@app.post("/api/games/{game_id}/tick", response_model=GameStateModel, tags=["parties"])
async def tick_game(
    store: StoreDep,
    game_id: GameId,
    body: TickRequest = Body(default=TickRequest()),
) -> GameStateModel:
    """Avance la simulation. Reserve aux clients qui pilotent leur propre cadence.

    Un client temps reel n'en a pas besoin : le canal WebSocket avance la
    partie tout seul.
    """
    session = get_session(store, game_id)
    async with session.lock:
        events = session.tick(body.ticks)
        return GameStateModel.from_game(session.game, session.id, events=events)


@app.post("/api/games/{game_id}/input", response_model=GameStateModel, tags=["parties"])
async def send_input(
    store: StoreDep,
    game_id: GameId,
    body: DirectionInput,
) -> GameStateModel:
    """Enregistre la direction voulue par le joueur.

    L'entree n'avance pas le jeu : elle est prise en compte au tick suivant.
    """
    session = get_session(store, game_id)
    try:
        direction = body.to_direction()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    async with session.lock:
        session.set_direction(direction)
        return GameStateModel.from_game(session.game, session.id)


@app.post("/api/games/{game_id}/pause", response_model=GameStateModel, tags=["parties"])
async def pause_game(store: StoreDep, game_id: GameId) -> GameStateModel:
    session = get_session(store, game_id)
    async with session.lock:
        session.game.pause()
        return GameStateModel.from_game(session.game, session.id)


@app.post("/api/games/{game_id}/resume", response_model=GameStateModel, tags=["parties"])
async def resume_game(store: StoreDep, game_id: GameId) -> GameStateModel:
    session = get_session(store, game_id)
    async with session.lock:
        session.game.resume()
        return GameStateModel.from_game(session.game, session.id)


@app.delete("/api/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["parties"])
async def delete_game(store: StoreDep, game_id: GameId) -> None:
    """Abandonne la partie et libere sa memoire."""
    get_session(store, game_id)
    store.delete(game_id)


def main() -> None:  # pragma: no cover - point d'entree
    """Lance le serveur (`pacman-server`)."""
    import uvicorn

    uvicorn.run("pacman.api.server:app", host="127.0.0.1", port=8000, reload=False)
