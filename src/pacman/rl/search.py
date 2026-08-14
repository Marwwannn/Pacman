"""Un joueur qui ne sait rien et qui gagne quand meme : la recherche en ligne.

Les trois autres agents decident a partir de ce qu'ils voient. Celui-ci decide
a partir de ce qui **arriverait** : a chaque intersection il clone la partie,
joue chaque coup possible, laisse le moteur derouler la suite, et garde le coup
dont l'issue est la meilleure.

Deux proprietes du moteur rendent cela possible, et exact :

- il est **deterministe**, donc ce que la copie vit est exactement ce que la
  partie vivrait — pas de noeud de hasard, pas d'esperance a estimer, ce qui
  distingue cette recherche d'un expectimax ou d'un MCTS classiques ;
- il est **rapide** (177 000 ticks/s), donc quelques dizaines de simulations
  par decision restent gratuites a l'echelle d'une partie.

L'interet dans un comparatif est ailleurs que dans le score : cet agent
n'apprend rien et ne generalise rien. Il paie a chaque coup ce que l'agent
entraine a paye une fois pour toutes. L'ecart entre les deux est la vraie
question — savoir, ou recalculer.
"""

from __future__ import annotations

import random
from math import inf

from ..core.entities import GhostMode
from ..core.game import Game, GameState
from ..core.geometry import Direction
from .metrics import MazeMetrics, metrics_for

#: Profondeur en points de decision, pas en ticks. Trois intersections
#: represente une trentaine de cases : au-dela, la position des fantomes n'est
#: plus predictible utilement et le cout explose en puissance du facteur de
#: branchement.
DEFAULT_DEPTH = 3

#: Plafond de ticks par segment simule, pour qu'un couloir pathologique ou une
#: animation de mort ne fasse jamais tourner la simulation sans fin.
SEGMENT_TICKS = 120


class SearchAgent:
    """Choisit son coup en simulant la suite, sans le moindre entrainement."""

    #: Ce que vaut mourir, dans la meme echelle que les points du jeu. Domine
    #: tout gain atteignable sur l'horizon de recherche : aucune pastille ne
    #: vaut le risque.
    DEATH = -500.0
    #: Attirance vers la nourriture la plus proche, pour departager deux issues
    #: qui rapportent autant. Sans elle, l'agent tourne en rond faute de
    #: difference mesurable entre deux coups.
    FOOD_PULL = 12.0
    #: Repulsion des chasseurs, appliquee a la proximite (donc explosive de
    #: pres, negligeable de loin).
    HUNTER_PUSH = 220.0

    def __init__(
        self,
        depth: int = DEFAULT_DEPTH,
        *,
        metrics: MazeMetrics | None = None,
        seed: int = 0,
    ) -> None:
        self.name = "recherche"
        self.depth = max(1, depth)
        self._metrics = metrics
        self._rng = random.Random(seed)

    def reset_rng(self, seed: int) -> None:
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------ decision

    def act(self, game: Game, actions: list[Direction], env=None) -> Direction:
        metrics = self._metrics or (env.metrics if env is not None else metrics_for(game.maze))
        notes = [(self._explore(game, action, self.depth, metrics), action) for action in actions]
        meilleure = max(note for note, _ in notes)
        candidates = [action for note, action in notes if note == meilleure]
        return candidates[0] if len(candidates) == 1 else self._rng.choice(candidates)

    def _explore(
        self,
        game: Game,
        action: Direction,
        depth: int,
        metrics: MazeMetrics,
    ) -> float:
        """Valeur du coup `action`, la suite etant jouee au mieux jusqu'a `depth`."""
        copie = game.clone()
        avant = copie.score
        copie.set_direction(action)
        vivant = _advance_to_decision(copie, metrics)
        gain = float(copie.score - avant)

        if not vivant:
            # Fin de partie : soit on est mort, soit le niveau est fini. Le
            # second cas est le meilleur resultat possible, pas le pire.
            if copie.state is GameState.LEVEL_COMPLETE:
                return gain + 500.0
            return gain + self.DEATH

        suites = [
            direction for direction, _ in copie.maze.neighbors(copie.pacman.position)
        ]
        if depth <= 1 or not suites:
            return gain + self._evaluate(copie, metrics)

        return gain + max(
            self._explore(copie, suivante, depth - 1, metrics) for suivante in suites
        )

    def _evaluate(self, game: Game, metrics: MazeMetrics) -> float:
        """Valeur d'une position ou l'on cesse de simuler.

        Volontairement courte : sur un moteur exact, c'est la simulation qui
        porte l'information, pas l'heuristique de feuille. Une evaluation
        elaboree masquerait ce que la recherche apporte vraiment.
        """
        case = game.pacman.position

        chasseurs = [
            ghost.position
            for ghost in game.ghosts
            if ghost.is_active and ghost.mode is not GhostMode.FRIGHTENED
        ]
        danger = metrics.proximity(min((metrics.distance(case, p) for p in chasseurs), default=inf))
        appat = metrics.proximity(metrics.nearest(case, game.pellets))

        return self.FOOD_PULL * appat - self.HUNTER_PUSH * danger


def _advance_to_decision(game: Game, metrics: MazeMetrics) -> bool:
    """Avance la partie jusqu'au prochain vrai choix. Faux si elle s'est terminee.

    Meme regle que dans l'environnement d'apprentissage — un pas va d'une
    intersection a la suivante — mais sans recompense ni statistique : ici on
    ne mesure rien, on regarde seulement ou l'on arrive.
    """
    for _ in range(SEGMENT_TICKS):
        avant = game.pacman.position
        game.tick()

        if game.is_over or game.state is GameState.LEVEL_COMPLETE:
            return False
        if game.state is GameState.DYING:
            continue
        if game.pacman.position == avant:
            continue

        case = game.pacman.position
        if metrics.is_decision(case, game.pacman.direction):
            return True

        options = metrics.options(case, game.pacman.direction)
        if len(options) == 1:
            game.set_direction(options[0])
        elif not options:
            game.set_direction(game.pacman.direction.opposite)
    return True
