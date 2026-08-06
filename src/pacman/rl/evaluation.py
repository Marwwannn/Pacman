"""Protocole d'evaluation : le meme pour les trois agents, sans exception.

Trois regles, toutes destinees a empecher un chiffre flatteur mais faux :

1. **Graines jamais vues.** Les parties d'evaluation sont tirees d'une plage
   disjointe de celle de l'entrainement. Le moteur etant deterministe, rejouer
   les graines d'entrainement mesurerait la memoire, pas la politique.
2. **Aucune exploration.** epsilon = 0 : on mesure la politique apprise, pas
   ses hesitations.
3. **La mediane, jamais le meilleur run.** Cent parties, mediane et ecart-type.
   Le meilleur score d'un agent aleatoire peut depasser la mediane d'un agent
   entraine — le publier serait mentir par selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

from .environment import EnvConfig, PacmanEnv
from .rewards import RewardConfig

#: Debut de la plage de graines reservee a l'entrainement.
TRAINING_SEEDS = 0
#: Debut de la plage reservee a l'evaluation. L'ecart est volontairement enorme :
#: aucune session d'entrainement realiste ne peut l'atteindre.
EVALUATION_SEEDS = 1_000_000


def seeds_for(count: int, offset: int) -> list[int]:
    return [offset + index for index in range(count)]


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Bilan d'une serie de parties."""

    agent: str
    games: int
    score_median: float
    score_mean: float
    score_stdev: float
    score_min: int
    score_max: int
    return_median: float
    win_rate: float
    death_rate: float
    decisions_mean: float
    pellets_left_median: float

    def as_dict(self) -> dict:
        return {
            "agent": self.agent,
            "parties": self.games,
            "score_median": self.score_median,
            "score_moyen": round(self.score_mean, 1),
            "score_ecart_type": round(self.score_stdev, 1),
            "score_min": self.score_min,
            "score_max": self.score_max,
            "retour_median": round(self.return_median, 1),
            "taux_victoire": round(self.win_rate, 3),
            "taux_mort": round(self.death_rate, 3),
            "decisions_moyennes": round(self.decisions_mean, 1),
            "pastilles_restantes_medianes": self.pellets_left_median,
        }

    def line(self) -> str:
        return (
            f"{self.agent:<14} mediane {self.score_median:>7.0f}  "
            f"ecart-type {self.score_stdev:>7.0f}  "
            f"min {self.score_min:>6}  max {self.score_max:>6}  "
            f"victoires {self.win_rate:>5.0%}  morts {self.death_rate:>5.0%}"
        )


def evaluate(
    agent,
    *,
    games: int = 100,
    config: EnvConfig | None = None,
    rewards: RewardConfig | None = None,
    offset: int = EVALUATION_SEEDS,
) -> EvalReport:
    """Fait jouer `agent` sur `games` parties de graines jamais vues."""
    if offset < EVALUATION_SEEDS:
        raise ValueError(
            "les graines d'evaluation doivent venir de la plage reservee "
            f"(>= {EVALUATION_SEEDS}) : un agent evalue sur ses graines "
            "d'entrainement mesure sa memoire, pas sa politique"
        )

    env = PacmanEnv(config or EnvConfig(), rewards)
    results = [env.run_episode(agent, seed) for seed in seeds_for(games, offset)]

    scores = [int(item["score"]) for item in results]
    returns = [float(item["return"]) for item in results]

    return EvalReport(
        agent=getattr(agent, "name", type(agent).__name__),
        games=games,
        score_median=median(scores),
        score_mean=sum(scores) / len(scores),
        score_stdev=pstdev(scores) if len(scores) > 1 else 0.0,
        score_min=min(scores),
        score_max=max(scores),
        return_median=median(returns),
        win_rate=sum(1 for item in results if item.get("won")) / len(results),
        death_rate=sum(1 for item in results if item.get("died")) / len(results),
        decisions_mean=sum(item["decisions"] for item in results) / len(results),
        pellets_left_median=median(item["remaining_pellets"] for item in results),
    )
