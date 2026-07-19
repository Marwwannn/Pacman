import pytest

from pacman.core.entities import Ghost, GhostMode, Pacman
from pacman.core.geometry import Direction, Position
from pacman.core.maze import Maze


class Contexte:
    """GhostContext minimal, pour tester les entites sans instancier Game."""

    def __init__(self, maze: Maze, pacman: Position, direction=Direction.LEFT, blinky=None):
        self.maze = maze
        self._pacman = pacman
        self._direction = direction
        self._blinky = blinky or pacman

    pacman_position = property(lambda self: self._pacman)
    pacman_direction = property(lambda self: self._direction)
    blinky_position = property(lambda self: self._blinky)


class FantomeTest(Ghost):
    """Fantome jetable : sa cible est fixee par le test."""

    def __init__(self, *args, cible: Position | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cible = cible or Position(0, 0)

    def chase_target(self, context):
        return self.cible


@pytest.fixture
def ctx(classic_maze):
    return Contexte(classic_maze, Position(13, 23))


class TestPacman:
    def test_avance_dans_la_direction_demandee(self, ctx):
        pacman = Pacman(Position(13, 23), speed=1.0)
        pacman.request(Direction.LEFT)
        pacman.update(ctx)
        assert pacman.position == Position(12, 23)

    def test_sarrete_devant_un_mur(self, ctx):
        pacman = Pacman(Position(6, 23), speed=1.0)
        pacman.request(Direction.LEFT)
        for _ in range(3):
            pacman.update(ctx)
        assert pacman.position == Position(6, 23)
        assert pacman.direction is Direction.NONE

    def test_intention_conservee_jusqua_ce_quelle_soit_jouable(self, ctx):
        # Le joueur demande un virage trop tot ; il doit se produire des que
        # possible, sinon le controle parait rate.
        pacman = Pacman(Position(9, 20), speed=1.0)
        pacman.request(Direction.LEFT)
        pacman.update(ctx)
        pacman.request(Direction.UP)  # impossible ici
        pacman.update(ctx)
        assert pacman.direction is Direction.LEFT
        for _ in range(5):
            pacman.update(ctx)
        assert pacman.direction is Direction.UP

    def test_vitesse_fractionnaire_espace_les_pas(self, ctx):
        pacman = Pacman(Position(13, 23), speed=0.5)
        pacman.request(Direction.LEFT)
        assert pacman.update(ctx) is False  # accumulateur a 0.5
        assert pacman.update(ctx) is True

    def test_super_pastille_accelere(self, ctx):
        pacman = Pacman(Position(13, 23), speed=0.8)
        lent = pacman.speed
        pacman.energized = True
        assert pacman.speed > lent

    def test_reset_efface_lintention(self, ctx):
        pacman = Pacman(Position(13, 23))
        pacman.request(Direction.LEFT)
        pacman.energized = True
        pacman.reset()
        assert pacman.desired_direction is Direction.NONE
        assert pacman.energized is False


class TestGhost:
    def test_ghost_est_abstrait(self, classic_maze):
        with pytest.raises(TypeError):
            Ghost("x", Position(1, 1), Position(0, 0))  # type: ignore[abstract]

    def test_immobile_dans_la_maison(self, ctx, classic_maze):
        fantome = FantomeTest("pinky", classic_maze.ghost_starts["pinky"], Position(2, 0))
        depart = fantome.position
        for _ in range(10):
            fantome.update(ctx)
        assert fantome.position == depart

    def test_vise_la_cible_la_plus_proche(self, ctx, classic_maze):
        fantome = FantomeTest(
            "blinky", Position(6, 5), Position(0, 0), speed=1.0, cible=Position(6, 1)
        )
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        fantome.update(ctx)
        assert fantome.position == Position(6, 4)

    def test_demi_tour_interdit(self, ctx, classic_maze):
        fantome = FantomeTest(
            "blinky", Position(6, 4), Position(0, 0), speed=1.0, cible=Position(6, 8)
        )
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        fantome.direction = Direction.UP
        fantome.update(ctx)
        # La cible est en bas, mais faire demi-tour est interdit.
        assert fantome.position != Position(6, 5)

    def test_changement_de_mode_provoque_un_demi_tour(self, ctx, classic_maze):
        fantome = FantomeTest("blinky", Position(6, 4), Position(0, 0), speed=1.0)
        fantome.set_mode(GhostMode.SCATTER, reverse=False)
        fantome.direction = Direction.UP
        fantome.set_mode(GhostMode.CHASE)
        assert fantome.pending_reverse is True
        fantome.update(ctx)
        assert fantome.direction is Direction.DOWN

    def test_ralenti_dans_le_tunnel(self, ctx, classic_maze):
        fantome = FantomeTest("blinky", Position(1, 14), Position(0, 0), speed=0.75)
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        assert fantome.effective_speed(classic_maze) == pytest.approx(Ghost.TUNNEL_SPEED)

    def test_effraye_est_plus_lent_mange_plus_rapide(self, ctx, classic_maze):
        fantome = FantomeTest("blinky", Position(13, 11), Position(0, 0))
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        normale = fantome.speed
        fantome.set_mode(GhostMode.FRIGHTENED)
        effraye = fantome.speed
        fantome.set_mode(GhostMode.EATEN, reverse=False)
        assert effraye < normale < fantome.speed

    def test_effraye_ne_suit_plus_la_cible(self, ctx, classic_maze):
        # Deux fantomes effrayes partant du meme endroit doivent diverger,
        # sinon ils restent colles et le mode perd tout interet.
        a = FantomeTest("blinky", Position(6, 5), Position(0, 0), speed=1.0)
        b = FantomeTest("clyde", Position(6, 5), Position(0, 0), speed=1.0)
        for fantome in (a, b):
            fantome.set_mode(GhostMode.SCATTER, reverse=False)
            fantome.set_mode(GhostMode.FRIGHTENED, reverse=False)
        chemins = []
        for fantome in (a, b):
            trace = []
            for _ in range(30):
                fantome.update(ctx)
                trace.append(fantome.position)
            chemins.append(trace)
        assert chemins[0] != chemins[1]

    def test_seuls_les_yeux_franchissent_la_porte(self, ctx, classic_maze):
        porte = min(classic_maze.doors, key=lambda p: (p.y, p.x))
        fantome = FantomeTest("blinky", Position(13, 11), Position(0, 0))
        fantome.set_mode(GhostMode.CHASE, reverse=False)
        assert not fantome.can_enter(classic_maze, porte)
        fantome.set_mode(GhostMode.EATEN, reverse=False)
        assert fantome.can_enter(classic_maze, porte)

    def test_aleatoire_reproductible(self, ctx, classic_maze):
        def trace():
            fantome = FantomeTest("blinky", Position(6, 5), Position(0, 0), speed=1.0)
            fantome.set_mode(GhostMode.SCATTER, reverse=False)
            fantome.set_mode(GhostMode.FRIGHTENED, reverse=False)
            return [fantome.update(ctx) or fantome.position for _ in range(20)]

        assert trace() == trace()
