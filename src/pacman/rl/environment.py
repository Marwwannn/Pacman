"""Environnement d'apprentissage par renforcement autour du moteur de jeu.

Deux partis pris portent tout le reste.

**Un pas = une intersection.** Le moteur avance case par case et 89 % des cases
n'offrent aucun choix : y demander une decision reviendrait a apprendre sur un
horizon de ~2500 pas dont 2440 sans consequence. L'environnement pilote donc
lui-meme les couloirs et ne rend la main que la ou il y a vraiment a choisir,
ce qui ramene l'horizon a ~100 pas par partie.

**Le determinisme du moteur est traite comme un piege.** Meme labyrinthe, memes
fantomes, meme depart, generateurs jamais resemes : un agent y memorise une
suite de coups qui donne un excellent score en apprentissage et s'effondre au
premier changement. Chaque episode part donc d'une graine qui decale le depart
de Pac-Man et l'errance des fantomes — la partie reste rejouable a l'identique,
mais deux graines donnent deux parties differentes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from ..core.game import Game, GameState
from ..core.geometry import Direction, Position
from ..core.maze import Maze
from .metrics import MazeMetrics, metrics_for
from .rewards import RewardConfig


@dataclass(frozen=True, slots=True)
class EnvConfig:
    """Reglages d'un environnement."""

    maze: str = "classic"
    level: int = 1
    #: Une seule vie par defaut : la mort termine l'episode, ce qui rend
    #: l'attribution du credit beaucoup plus nette qu'avec trois vies.
    lives: int = 1
    #: Curriculum : 1 fantome pour demarrer, 4 pour le jeu complet.
    ghosts: int = 4
    randomize_start: bool = True
    randomize_ghosts: bool = True
    #: Garde-fou : un agent qui tourne en rond ne doit pas bloquer une session.
    max_ticks: int = 12_000
    #: Terminer des le niveau fini plutot que d'enchainer les niveaux.
    stop_at_level_complete: bool = True


@dataclass(frozen=True, slots=True)
class StepResult:
    """Resultat d'un pas de decision."""

    reward: float
    done: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.done or self.truncated


class PacmanEnv:
    """Une partie de Pac-Man vue comme un probleme de decision sequentielle."""

    def __init__(
        self,
        config: EnvConfig | None = None,
        rewards: RewardConfig | None = None,
    ) -> None:
        self.config = config or EnvConfig()
        self.rewards = rewards or RewardConfig()
        self._maze: Maze = Maze.load(self.config.maze)
        self.metrics: MazeMetrics = metrics_for(self._maze)

        self.game: Game = self._new_game()
        self.seed: int = 0
        self.ticks = 0
        self.decisions = 0
        self.deaths = 0
        self._finished = True

    # ================================================================ cycle de vie

    def reset(self, seed: int) -> Game:
        """Demarre une partie tiree de `seed` et s'arrete au premier choix."""
        self.seed = int(seed)
        self.ticks = 0
        self.decisions = 0
        self.deaths = 0
        self._finished = False
        self.game = self._new_game()
        self._randomize(random.Random(self.seed))

        # Le depart tire au sort peut tomber dans un couloir : on avance
        # jusqu'au premier vrai choix avant de rendre la main.
        if not self._at_decision():
            self._drive()
        return self.game

    def _new_game(self) -> Game:
        game = Game(self._maze, level=self.config.level, lives=self.config.lives)
        game.limit_ghosts(self.config.ghosts)
        return game

    def _randomize(self, rng: random.Random) -> None:
        """Casse le determinisme d'une partie a l'autre, pas a l'interieur d'une partie."""
        if self.config.randomize_ghosts:
            for index, ghost in enumerate(self.game.ghosts):
                ghost.seed_rng(self.seed * 1_000 + index * 7 + 1)

        if not self.config.randomize_start:
            return

        start = rng.choice(sorted(self.metrics.walkable, key=lambda p: (p.y, p.x)))
        pacman = self.game.pacman
        pacman.start = start
        pacman.reset()
        # Sans cela, la case de depart porterait une pastille que la partie
        # d'origine n'a pas, et le total de pastilles varierait avec la graine.
        self.game.pellets.discard(start)
        self.game.power_pellets.discard(start)

    # ================================================================ interaction

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def position(self) -> Position:
        return self.game.pacman.position

    def legal_actions(self) -> list[Direction]:
        """Directions praticables depuis la case courante, demi-tour compris.

        Le demi-tour est autorise : c'est souvent la seule fuite possible quand
        un fantome arrive de face. Son cout est porte par le malus de pas, pas
        par une interdiction.
        """
        return [direction for direction, _ in self._maze.neighbors(self.position)]

    def step(self, action: Direction) -> StepResult:
        """Applique un choix, traverse le couloir qui suit, revient au choix suivant."""
        if self._finished:
            raise RuntimeError("episode termine : appeler reset() avant step()")
        if action not in self.legal_actions():
            raise ValueError(f"action illegale depuis {self.position} : {action.name}")

        self.decisions += 1
        self.game.set_direction(action)
        return self._drive(step_cost=True)

    # ---------------------------------------------------------------- pilotage

    def _drive(self, *, step_cost: bool = False) -> StepResult:
        """Avance le moteur jusqu'au prochain point de decision ou a la fin."""
        reward = self.rewards.step if step_cost else 0.0
        died = False
        won = False

        while True:
            before = self.position
            events = self.game.tick()
            self.ticks += 1
            reward += self.rewards.from_events(events)

            for event in events:
                if event.type == "pacman_died":
                    self.deaths += 1
                    died = True
                elif event.type == "level_complete":
                    won = True

            if self.game.is_over or (won and self.config.stop_at_level_complete):
                self._finished = True
                return self._result(reward, done=True, died=died, won=won)

            if self.ticks >= self.config.max_ticks:
                self._finished = True
                return self._result(reward, done=False, died=died, won=won)

            # L'animation de mort ne se decide pas : on la traverse jusqu'a la
            # reapparition, sinon l'agent se verrait demander une action depuis
            # la case ou il vient de se faire manger.
            if self.game.state is GameState.DYING:
                continue

            position = self.position
            if position == before:
                continue  # pas encore change de case (attente, ou pas partiel)

            if self._at_decision():
                return self._result(reward, done=False, died=died, won=won)

            # Couloir : le seul chemin possible est impose, personne n'a rien a
            # decider. Sans ce pilotage, l'intention memorisee de Pac-Man le
            # ferait s'arreter au premier virage.
            forced = self._forced_direction()
            if forced is not Direction.NONE:
                self.game.set_direction(forced)

    def _at_decision(self) -> bool:
        return self.metrics.is_decision(self.position, self.game.pacman.direction)

    def _forced_direction(self) -> Direction:
        """Unique direction possible, ou demi-tour au fond d'une impasse."""
        options = self.metrics.options(self.position, self.game.pacman.direction)
        if len(options) == 1:
            return options[0]
        if not options:
            return self.game.pacman.direction.opposite
        return Direction.NONE

    def _result(self, reward: float, *, done: bool, died: bool, won: bool) -> StepResult:
        return StepResult(
            reward=reward,
            done=done,
            truncated=not done and self._finished,
            info={
                "score": self.game.score,
                "ticks": self.ticks,
                "decisions": self.decisions,
                "died": died,
                "deaths": self.deaths,
                "won": won,
                "remaining_pellets": self.game.remaining_pellets,
                "state": self.game.state.value,
            },
        )

    # ================================================================ confort

    def run_episode(self, agent, seed: int) -> dict[str, Any]:
        """Deroule une partie entiere avec `agent`. Renvoie le bilan de l'episode."""
        self.reset(seed)
        total = 0.0
        last: StepResult | None = None

        while not self._finished:
            actions = self.legal_actions()
            if not actions:
                break
            action = agent.act(self.game, actions, self)
            last = self.step(action)
            total += last.reward

        info = dict(last.info) if last is not None else {}
        info.update(
            {
                "seed": seed,
                "return": total,
                "score": self.game.score,
                "ticks": self.ticks,
                "decisions": self.decisions,
                "remaining_pellets": self.game.remaining_pellets,
                # Au niveau de l'episode, « mort » veut dire « au moins une
                # fois », pas « au dernier pas ».
                "died": self.deaths > 0,
                "deaths": self.deaths,
                "won": self.game.state is GameState.LEVEL_COMPLETE,
                "truncated": last.truncated if last is not None else True,
            }
        )
        return info
