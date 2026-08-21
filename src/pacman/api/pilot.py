"""Un agent aux commandes d'une partie servie en temps reel.

Le serveur n'apprend aucune regle du jeu ici : le pilote ne fait que CHOISIR
une direction la ou un joueur humain l'aurait tapee, et le moteur fait le
reste. Il reprend a l'identique la discipline de l'environnement
d'entrainement (`rl/environment.py`) — decider aux intersections, suivre le
couloir entre deux. C'est ce qui permet d'affirmer que l'agent que l'on
regarde jouer dans le navigateur est exactement celui qui a ete mesure : un
test le verifie case par case.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources

from ..core.game import Game
from ..core.geometry import Direction, Position
from ..core.maze import Maze
from ..rl.agents import ApproximateQAgent, HeuristicAgent, RandomAgent
from ..rl.metrics import MazeMetrics, metrics_for
from ..rl.search import SearchAgent

#: Poids du modele retenu pour le rendu : l'agent entraine a quatre fantomes,
#: celui du comparatif. Copie de `results/poids_4fantomes.json`, embarquee dans
#: le paquet pour que `pacman-server` la trouve une fois installe n'importe ou.
POIDS_RETENUS = "appris_4fantomes.json"
#: Profondeur de la recherche en direct : celle du comparatif publie.
PROFONDEUR_RECHERCHE = 3


def _agent_appris(metrics: MazeMetrics) -> ApproximateQAgent:
    with resources.as_file(resources.files("pacman.rl") / "weights" / POIDS_RETENUS) as chemin:
        return ApproximateQAgent.load(chemin, metrics=metrics, seed=0)


#: Les quatre agents du comparatif, sous le nom que le client leur donne.
PILOTES: dict[str, Callable[[MazeMetrics], object]] = {
    "aleatoire": lambda metrics: RandomAgent(seed=0),
    "heuristique": lambda metrics: HeuristicAgent(metrics=metrics, seed=0),
    "appris": _agent_appris,
    "recherche": lambda metrics: SearchAgent(PROFONDEUR_RECHERCHE, metrics=metrics, seed=0),
}


class Pilot:
    """Tient le volant d'une partie : une direction a chaque case ou il y a a choisir."""

    def __init__(self, name: str, agent, metrics: MazeMetrics) -> None:
        self.name = name
        self.agent = agent
        self.metrics = metrics
        self._last: Position | None = None

    def steer(self, game: Game) -> None:
        """A appeler avant chaque tick. Ne fait rien tant que Pac-Man n'a pas change de case.

        Meme regle que l'environnement : a une intersection, l'agent choisit
        parmi toutes les directions praticables, demi-tour compris ; dans un
        couloir, la seule issue est prise sans lui demander son avis.
        """
        pacman = game.pacman
        position = pacman.position
        if position == self._last:
            return
        self._last = position
        heading = pacman.direction

        if self.metrics.is_decision(position, heading):
            actions = [direction for direction, _ in game.maze.neighbors(position)]
            if actions:
                game.set_direction(self.agent.act(game, actions, None))
            return

        # Couloir : une seule issue, ou demi-tour au fond d'une impasse. Sans
        # cela Pac-Man s'arreterait au premier virage, faute d'intention.
        options = self.metrics.options(position, heading)
        if len(options) == 1:
            game.set_direction(options[0])
        elif not options and heading is not Direction.NONE:
            game.set_direction(heading.opposite)


def build_pilot(name: str | None, maze: Maze) -> Pilot | None:
    """Le pilote demande, ou None pour une partie jouee par un humain."""
    if name is None:
        return None
    try:
        fabrique = PILOTES[name]
    except KeyError:
        raise ValueError(
            f"pilote inconnu : {name!r} (attendu : {', '.join(PILOTES)})"
        ) from None
    metrics = metrics_for(maze)
    return Pilot(name, fabrique(metrics), metrics)
