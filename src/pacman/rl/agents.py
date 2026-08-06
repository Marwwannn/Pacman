"""Les trois joueurs : le hasard, la regle ecrite a la main, l'agent appris.

Les deux premiers ne sont pas du decor. Un score d'agent entraine ne veut rien
dire seul : il faut un plancher (que fait-on sans aucune intelligence ?) et un
plafond raisonnable (que fait-on avec de bonnes regles evidentes ?). C'est
entre ces deux bornes que l'apprentissage se juge.
"""

from __future__ import annotations

import json
import random
from math import inf
from pathlib import Path
from typing import Protocol

from ..core.entities import GhostMode
from ..core.game import Game
from ..core.geometry import Direction
from .features import FEATURE_NAMES, extract
from .metrics import MazeMetrics, metrics_for


class Agent(Protocol):
    """Ce que l'environnement attend d'un joueur."""

    name: str

    def act(self, game: Game, actions: list[Direction], env) -> Direction: ...


class RandomAgent:
    """Plancher : tire une direction au sort a chaque intersection."""

    def __init__(self, seed: int = 0) -> None:
        self.name = "aleatoire"
        self._rng = random.Random(seed)

    def act(self, game: Game, actions: list[Direction], env) -> Direction:
        return self._rng.choice(actions)


class HeuristicAgent:
    """Plafond raisonnable : des regles ecrites a la main, aucune apprentissage.

    Trois priorites, dans cet ordre : ne pas mourir, manger un fantome effraye
    tant que c'est possible, sinon aller a la pastille la plus proche. C'est
    volontairement simple — le but est d'avoir une reference honnete, pas de
    gagner le concours.
    """

    #: En deca de cette distance, une case occupee par un chasseur est un piege.
    LETHAL = 2
    #: Au-dela, la position des chasseurs n'influence plus le choix.
    CAUTION = 8

    def __init__(self, metrics: MazeMetrics | None = None, seed: int = 0) -> None:
        self.name = "heuristique"
        self._metrics = metrics
        self._rng = random.Random(seed)

    def act(self, game: Game, actions: list[Direction], env) -> Direction:
        metrics = self._metrics or (env.metrics if env is not None else metrics_for(game.maze))
        scored = [(self._score(game, action, metrics), action) for action in actions]
        best = max(score for score, _ in scored)
        candidates = [action for score, action in scored if score == best]
        return candidates[0] if len(candidates) == 1 else self._rng.choice(candidates)

    def _score(self, game: Game, action: Direction, metrics: MazeMetrics) -> float:
        tile = game.maze.step(game.pacman.position, action)
        score = 0.0

        hunters = [
            ghost.position
            for ghost in game.ghosts
            if ghost.is_active and ghost.mode is not GhostMode.FRIGHTENED
        ]
        nearest_hunter = min((metrics.distance(tile, pos) for pos in hunters), default=inf)
        if nearest_hunter <= self.LETHAL:
            score -= 1000.0
        if nearest_hunter != inf:
            score += 8.0 * min(nearest_hunter, self.CAUTION)

        prey = [
            ghost.position
            for ghost in game.ghosts
            if ghost.mode is GhostMode.FRIGHTENED
        ]
        nearest_prey = min((metrics.distance(tile, pos) for pos in prey), default=inf)
        if nearest_prey != inf:
            score -= 6.0 * nearest_prey

        pellet = metrics.nearest(tile, game.pellets)
        if pellet != inf:
            score -= 2.0 * pellet

        # Une super-pastille ne vaut d'etre visee que si une menace approche :
        # la gober au calme gaspille les six secondes de vulnerabilite.
        if hunters and nearest_hunter <= self.CAUTION:
            power = metrics.nearest(tile, game.power_pellets)
            if power != inf:
                score -= 3.0 * power

        if not metrics.options(tile, action):
            score -= 30.0  # impasse
        if action is game.pacman.direction.opposite:
            score -= 5.0
        return score


class ApproximateQAgent:
    """Q-learning approxime : une valeur lineaire sur les douze features.

    Le tabulaire est hors de question ici (l'etat brut se compte en 2^244) et
    un reseau profond demanderait dix a cent fois plus d'episodes pour une
    boite noire. Douze poids se lisent, s'entrainent en quelques minutes, et
    suffisent a un labyrinthe dont on a deja extrait la structure dans les
    features.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        *,
        metrics: MazeMetrics | None = None,
        seed: int = 0,
    ) -> None:
        self.name = "q-approxime"
        self.weights = {name: 0.0 for name in FEATURE_NAMES}
        if weights:
            self.weights.update({k: float(v) for k, v in weights.items() if k in self.weights})
        self._metrics = metrics
        self._rng = random.Random(seed)

    # ---------------------------------------------------------------- valeurs

    def metrics_of(self, game: Game, env=None) -> MazeMetrics:
        return self._metrics or (env.metrics if env is not None else metrics_for(game.maze))

    def q_from(self, values: tuple[float, ...]) -> float:
        return sum(self.weights[name] * value for name, value in zip(FEATURE_NAMES, values))

    def q(self, game: Game, action: Direction, metrics: MazeMetrics) -> float:
        return self.q_from(extract(game, action, metrics))

    def best_value(self, game: Game, actions: list[Direction], metrics: MazeMetrics) -> float:
        if not actions:
            return 0.0
        return max(self.q(game, action, metrics) for action in actions)

    # ---------------------------------------------------------------- decision

    def act(self, game: Game, actions: list[Direction], env=None) -> Direction:
        """Choix glouton. L'exploration est du ressort de l'entrainement."""
        return self.greedy(game, actions, self.metrics_of(game, env))

    def greedy(self, game: Game, actions: list[Direction], metrics: MazeMetrics) -> Direction:
        scored = [(self.q(game, action, metrics), action) for action in actions]
        best = max(score for score, _ in scored)
        candidates = [action for score, action in scored if score == best]
        # Les ex aequo sont frequents au demarrage (tous les poids sont nuls) :
        # les departager au hasard evite un biais vers la premiere direction.
        return candidates[0] if len(candidates) == 1 else self._rng.choice(candidates)

    def explore(
        self,
        game: Game,
        actions: list[Direction],
        metrics: MazeMetrics,
        epsilon: float,
    ) -> Direction:
        """Choix epsilon-glouton, utilise pendant l'entrainement uniquement."""
        if self._rng.random() < epsilon:
            return self._rng.choice(actions)
        return self.greedy(game, actions, metrics)

    # ---------------------------------------------------------------- apprentissage

    def update(
        self,
        values: tuple[float, ...],
        reward: float,
        next_value: float,
        *,
        alpha: float,
        gamma: float,
        clip: float = 100.0,
    ) -> float:
        """Une mise a jour de difference temporelle. Renvoie l'erreur appliquee.

        L'erreur est bornee : une mort vaut -500 alors que les features valent
        au plus 1, donc un seul episode malheureux suffirait sinon a faire
        exploser les poids avant que la moyenne ne les rattrape.
        """
        error = reward + gamma * next_value - self.q_from(values)
        error = max(-clip, min(clip, error))
        for name, value in zip(FEATURE_NAMES, values):
            self.weights[name] += alpha * error * value
        return error

    # ---------------------------------------------------------------- persistance

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"weights": self.weights}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path, **kwargs) -> ApproximateQAgent:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("weights", data), **kwargs)
