"""Canal temps reel : le serveur fait tourner la partie et diffuse l'etat.

Une boucle par partie, pas une par spectateur : le moteur avance une seule
fois, et tous les abonnes recoivent la meme image. C'est aussi ce qui garantit
qu'ouvrir un second onglet ne fait pas jouer la partie deux fois plus vite.

La boucle rattrape son retard en ticks plutot qu'en temps : si le serveur a
ete ralenti, elle rejoue les ticks manquants au lieu d'en sauter, sans quoi
deux clients verraient des parties divergentes.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from ..core.game import GameState
from ..core.rules import TICKS_PER_SECOND
from .schemas import GameStateModel
from .sessions import GameSession

#: Au-dela, on renonce a rattraper : le serveur etait trop charge, on repart
#: du temps present plutot que de rejouer des secondes entieres d'un coup.
MAX_CATCHUP_TICKS = 30


class Broadcaster:
    """Diffuse l'etat d'une partie a ses abonnes, au rythme du moteur."""

    def __init__(self, session: GameSession, *, tick_rate: int = TICKS_PER_SECOND) -> None:
        self.session = session
        self.tick_rate = tick_rate
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ cycle de vie

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------ boucle

    async def _run(self) -> None:
        interval = 1.0 / self.tick_rate
        next_tick = time.monotonic()

        while self.session.subscribers:
            now = time.monotonic()
            retard = max(0, int((now - next_tick) / interval))
            a_jouer = min(1 + retard, MAX_CATCHUP_TICKS)
            if retard >= MAX_CATCHUP_TICKS:
                next_tick = now  # trop de retard : on abandonne le rattrapage

            async with self.session.lock:
                events = self.session.tick(a_jouer)
                message = {
                    "type": "state",
                    **GameStateModel.from_game(
                        self.session.game, self.session.id, events=events
                    ).model_dump(exclude_none=True),
                }
                terminee = self.session.game.state is GameState.GAME_OVER

            await self.publish(message)
            if terminee:
                return

            next_tick += interval * a_jouer
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))

    # ------------------------------------------------------------------ diffusion

    async def publish(self, message: dict) -> None:
        """Envoie a tous les abonnes. Un client injoignable est simplement lache."""
        morts = []
        for websocket in list(self.session.subscribers):
            try:
                await websocket.send_json(message)
            except Exception:
                # Deconnexion brutale : inutile de faire echouer les autres.
                morts.append(websocket)
        for websocket in morts:
            self.session.subscribers.discard(websocket)
