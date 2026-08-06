"""Apprentissage par renforcement : un agent qui joue Pac-Man.

A ne pas confondre avec `ai/`, qui contient l'intelligence des quatre fantomes
— celle-la est ecrite a la main et ne s'entraine pas. Ici c'est le joueur qui
apprend.

Le paquet ne touche pas au moteur : il l'enveloppe. `core/` reste deterministe,
sans horloge et clonable, ce sont ces trois proprietes qui en font un
environnement d'apprentissage utilisable.

    from pacman.rl import EnvConfig, HeuristicAgent, evaluate

    print(evaluate(HeuristicAgent(), games=20, config=EnvConfig(ghosts=1)).line())
"""

from .agents import Agent, ApproximateQAgent, HeuristicAgent, RandomAgent
from .environment import EnvConfig, PacmanEnv, StepResult
from .evaluation import EVALUATION_SEEDS, EvalReport, evaluate
from .features import FEATURE_NAMES, extract, named
from .metrics import MazeMetrics, metrics_for
from .rewards import RewardConfig
from .training import Hyper, TrainReport, train

__all__ = [
    "EVALUATION_SEEDS",
    "FEATURE_NAMES",
    "Agent",
    "ApproximateQAgent",
    "EnvConfig",
    "EvalReport",
    "HeuristicAgent",
    "Hyper",
    "MazeMetrics",
    "PacmanEnv",
    "RandomAgent",
    "RewardConfig",
    "StepResult",
    "TrainReport",
    "evaluate",
    "extract",
    "metrics_for",
    "named",
    "train",
]
