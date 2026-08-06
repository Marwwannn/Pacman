"""Boucle d'entrainement du Q-learning approxime.

Le point delicat n'est pas l'algorithme, tenu en dix lignes, mais les graines :
les parties d'entrainement et celles d'evaluation doivent venir de deux plages
disjointes. Sans cette separation, un agent qui a simplement memorise ses
parties obtient un excellent score et personne ne s'en apercoit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .agents import ApproximateQAgent
from .environment import EnvConfig, PacmanEnv
from .evaluation import TRAINING_SEEDS, seeds_for
from .features import extract
from .rewards import RewardConfig


@dataclass(frozen=True, slots=True)
class Hyper:
    """Parametres d'apprentissage.

    `alpha` est plus bas que le 0,1 habituel des exemples de cours : les
    recompenses vont jusqu'a -500 alors que les features valent au plus 1, donc
    une correction a 0,1 deplacerait un poids de 50 d'un seul coup. A 0,02 avec
    ecretage de l'erreur, les poids convergent au lieu d'osciller.
    """

    alpha: float = 0.02
    alpha_final: float = 0.002
    gamma: float = 0.95
    epsilon: float = 1.0
    epsilon_final: float = 0.05
    #: Fraction des episodes sur laquelle epsilon et alpha decroissent.
    decay_fraction: float = 0.7
    td_clip: float = 100.0


@dataclass(slots=True)
class TrainReport:
    """Trace de l'entrainement, pour tracer une courbe d'apprentissage."""

    episodes: int = 0
    scores: list[int] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)
    windows: list[dict[str, float]] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, float]:
        return {
            "episodes": self.episodes,
            "score_median": median(self.scores) if self.scores else 0.0,
            "score_median_dernier_dixieme": (
                median(self.scores[-max(1, len(self.scores) // 10):]) if self.scores else 0.0
            ),
        }


def _schedule(start: float, end: float, progress: float) -> float:
    """Decroissance lineaire de `start` a `end`, puis plateau."""
    return end + (start - end) * max(0.0, 1.0 - progress)


def train(
    episodes: int = 2_000,
    *,
    config: EnvConfig | None = None,
    rewards: RewardConfig | None = None,
    hyper: Hyper | None = None,
    agent: ApproximateQAgent | None = None,
    seed: int = 0,
    log_every: int = 0,
    on_window=None,
) -> tuple[ApproximateQAgent, TrainReport]:
    """Entraine un agent et renvoie ses poids avec la trace de l'apprentissage."""
    hyper = hyper or Hyper()
    env = PacmanEnv(config or EnvConfig(), rewards)
    agent = agent or ApproximateQAgent(metrics=env.metrics, seed=seed)
    report = TrainReport()

    seeds = seeds_for(episodes, offset=TRAINING_SEEDS + seed * episodes)
    window_scores: list[int] = []

    for index, episode_seed in enumerate(seeds):
        progress = index / max(1, episodes * hyper.decay_fraction)
        epsilon = _schedule(hyper.epsilon, hyper.epsilon_final, progress)
        alpha = _schedule(hyper.alpha, hyper.alpha_final, progress)

        total = _run_training_episode(env, agent, episode_seed, epsilon, alpha, hyper)

        report.episodes += 1
        report.scores.append(env.game.score)
        report.returns.append(total)
        window_scores.append(env.game.score)

        if log_every and (index + 1) % log_every == 0:
            entry = {
                "episode": index + 1,
                "epsilon": round(epsilon, 3),
                "alpha": round(alpha, 4),
                "score_median": median(window_scores),
            }
            report.windows.append(entry)
            window_scores.clear()
            if on_window is not None:
                on_window(entry)

    report.weights = dict(agent.weights)
    return agent, report


def _run_training_episode(
    env: PacmanEnv,
    agent: ApproximateQAgent,
    seed: int,
    epsilon: float,
    alpha: float,
    hyper: Hyper,
) -> float:
    """Un episode complet, avec mise a jour a chaque pas de decision."""
    game = env.reset(seed)
    total = 0.0

    while not env.finished:
        actions = env.legal_actions()
        if not actions:
            break

        action = agent.explore(game, actions, env.metrics, epsilon)
        values = extract(game, action, env.metrics)
        result = env.step(action)
        total += result.reward

        # La valeur de l'etat suivant est nulle s'il n'y a plus d'etat suivant :
        # confondre fin de partie et troncature ferait apprendre a l'agent que
        # mourir vaut la valeur moyenne d'une partie qui continue.
        next_value = (
            0.0
            if result.done
            else agent.best_value(game, env.legal_actions(), env.metrics)
        )
        agent.update(
            values,
            result.reward,
            next_value,
            alpha=alpha,
            gamma=hyper.gamma,
            clip=hyper.td_clip,
        )

    return total
