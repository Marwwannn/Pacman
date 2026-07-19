"""Fixtures partagees.

Les tests du moteur utilisent un petit labyrinthe dedie plutot que le niveau
classique : une grille de quelques cases rend les scenarios lisibles et les
positions attendues verifiables a la main.
"""

from __future__ import annotations

import pytest

from pacman.core.game import Game
from pacman.core.maze import Maze

#: Labyrinthe de test : un anneau, une maison a deux fantomes, un tunnel.
SMALL_MAZE = """\
#########
#.......#
#.##-##.#
T.#B Y#.T
#.##_##.#
#...P...#
#########
"""


@pytest.fixture
def small_maze() -> Maze:
    # Le second '_' n'existe pas dans le format : on ferme la maison par un mur.
    return Maze.from_text(SMALL_MAZE.replace("_", "#"))


@pytest.fixture
def classic_maze() -> Maze:
    return Maze.load("classic")


@pytest.fixture
def game(classic_maze: Maze) -> Game:
    """Partie sur le niveau classique, deja sortie du compte a rebours."""
    game = Game(classic_maze)
    game.run(130)
    return game
