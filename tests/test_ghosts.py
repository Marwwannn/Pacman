"""Les cibles des quatre fantomes.

Chaque cible est calculee a la main dans le test : c'est la seule facon de
verifier une personnalite, puisque le reste du comportement est mutualise.
"""

import pytest

from pacman.ai import Blinky, Clyde, Inky, Pinky, ahead_of, create_ghosts, scatter_targets
from pacman.core.entities import GhostMode
from pacman.core.geometry import Direction, Position

from .test_entities import Contexte


@pytest.fixture
def ctx(classic_maze):
    return Contexte(classic_maze, Position(13, 23), Direction.LEFT, Position(10, 20))


class TestCibles:
    def test_blinky_vise_pacman(self, ctx):
        blinky = Blinky("blinky", Position(13, 11), Position(25, 0))
        assert blinky.chase_target(ctx) == Position(13, 23)

    def test_pinky_vise_quatre_cases_devant(self, ctx):
        pinky = Pinky("pinky", Position(14, 13), Position(2, 0))
        # Pac-Man va vers la gauche : quatre cases plus a gauche.
        assert pinky.chase_target(ctx) == Position(9, 23)

    def test_inky_symetrise_blinky(self, ctx):
        # Pivot = deux cases devant Pac-Man = (11, 23) ; Blinky est en (10, 20).
        # Cible = 2 * pivot - blinky = (12, 26).
        inky = Inky("inky", Position(12, 13), Position(27, 30))
        assert inky.chase_target(ctx) == Position(12, 26)

    def test_clyde_poursuit_de_loin(self, ctx):
        clyde = Clyde("clyde", Position(1, 1), Position(0, 30))
        clyde.position = Position(1, 1)  # tres loin de Pac-Man
        assert clyde.chase_target(ctx) == Position(13, 23)

    def test_clyde_se_defile_de_pres(self, ctx):
        clyde = Clyde("clyde", Position(13, 25), Position(0, 30))
        clyde.position = Position(13, 25)  # a deux cases de Pac-Man
        assert clyde.chase_target(ctx) == clyde.scatter_target


class TestBugDorigine:
    def test_debordement_vers_le_haut(self):
        # Bug de 1980 : viser vers le haut decale aussi vers la gauche.
        assert ahead_of(Position(13, 23), Direction.UP, 4) == Position(9, 19)

    def test_desactivable(self):
        assert ahead_of(Position(13, 23), Direction.UP, 4, overflow_bug=False) == Position(13, 19)

    def test_les_autres_directions_sont_intactes(self):
        for direction in (Direction.LEFT, Direction.RIGHT, Direction.DOWN):
            avec = ahead_of(Position(13, 23), direction, 4)
            sans = ahead_of(Position(13, 23), direction, 4, overflow_bug=False)
            assert avec == sans

    def test_pinky_suit_loption(self, classic_maze):
        ctx = Contexte(classic_maze, Position(13, 23), Direction.UP)
        avec = Pinky("pinky", Position(14, 13), Position(2, 0), overflow_bug=True)
        sans = Pinky("pinky", Position(14, 13), Position(2, 0), overflow_bug=False)
        assert avec.chase_target(ctx) == Position(9, 19)
        assert sans.chase_target(ctx) == Position(13, 19)


class TestFabrique:
    def test_cree_les_quatre_fantomes_dans_lordre(self, classic_maze):
        fantomes = create_ghosts(classic_maze)
        assert [f.name for f in fantomes] == ["blinky", "pinky", "inky", "clyde"]

    def test_transmet_loption_aux_fantomes_concernes(self, classic_maze):
        fantomes = {f.name: f for f in create_ghosts(classic_maze, overflow_bug=False)}
        assert fantomes["pinky"].overflow_bug is False
        assert fantomes["inky"].overflow_bug is False

    def test_coins_de_repli_distincts(self, classic_maze):
        coins = scatter_targets(classic_maze)
        assert len(set(coins.values())) == 4

    def test_coins_hors_du_labyrinthe_praticable(self, classic_maze):
        # Une cible inatteignable force le fantome a tourner dans son coin
        # au lieu de s'immobiliser dessus.
        for coin in scatter_targets(classic_maze).values():
            assert classic_maze.is_wall(coin)

    def test_ignore_les_fantomes_absents_du_labyrinthe(self, small_maze):
        fantomes = create_ghosts(small_maze)
        assert [f.name for f in fantomes] == ["blinky", "pinky"]


def test_les_personnalites_divergent(classic_maze):
    """Sur une meme situation, les quatre ne visent pas la meme case."""
    ctx = Contexte(classic_maze, Position(13, 23), Direction.LEFT, Position(10, 20))
    cibles = set()
    for fantome in create_ghosts(classic_maze):
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        cibles.add(fantome.chase_target(ctx))
    assert len(cibles) >= 3
