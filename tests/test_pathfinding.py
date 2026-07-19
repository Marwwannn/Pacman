import random

from pacman.core import pathfinding as pf
from pacman.core.geometry import Direction, Position
from pacman.core.maze import Maze


def cases_libres(maze: Maze) -> list[Position]:
    return [
        Position(x, y)
        for y in range(maze.height)
        for x in range(maze.width)
        if maze.is_walkable(Position(x, y))
    ]


class TestBfs:
    def test_chemin_trivial(self, classic_maze):
        depart = Position(1, 1)
        assert pf.bfs_path(classic_maze, depart, depart) == [depart]

    def test_chemin_continu_et_sans_mur(self, classic_maze):
        chemin = pf.bfs_path(classic_maze, Position(1, 1), Position(26, 29))
        assert chemin[0] == Position(1, 1) and chemin[-1] == Position(26, 29)
        assert all(not classic_maze.is_wall(case) for case in chemin)
        assert all(
            a.manhattan(b) == 1 or classic_maze.is_tunnel(a)
            for a, b in zip(chemin, chemin[1:])
        )

    def test_cible_inatteignable(self, classic_maze):
        # La maison est close : on ne l'atteint pas sans franchir la porte.
        interieur = next(iter(classic_maze.house))
        assert pf.bfs_path(classic_maze, Position(1, 1), interieur) == []
        assert pf.bfs_path(classic_maze, Position(1, 1), interieur, through_door=True) != []

    def test_emprunte_le_tunnel_quand_cest_plus_court(self, classic_maze):
        # De part et d'autre du tunnel : deux pas suffisent.
        chemin = pf.bfs_path(classic_maze, Position(1, 14), Position(26, 14))
        assert len(chemin) < 10


class TestAStar:
    def test_meme_longueur_que_bfs(self, classic_maze):
        # A* n'est utile que s'il reste optimal. L'heuristique repliee sur les
        # tunnels est precisement la condition de cette optimalite.
        random.seed(0)
        cases = cases_libres(classic_maze)
        for _ in range(150):
            a, b = random.choice(cases), random.choice(cases)
            bfs = pf.bfs_path(classic_maze, a, b)
            astar = pf.a_star_path(classic_maze, a, b)
            assert len(bfs) == len(astar)

    def test_distance_repliee_passe_par_le_tunnel(self, classic_maze):
        gauche, droite = Position(0, 14), Position(27, 14)
        assert pf.torus_distance(classic_maze, gauche, droite) == 1
        assert gauche.manhattan(droite) == 27

    def test_chemin_trivial(self, classic_maze):
        assert pf.a_star_path(classic_maze, Position(1, 1), Position(1, 1)) == [Position(1, 1)]


class TestNextDirection:
    def test_premiere_direction_utile(self, classic_maze):
        direction = pf.next_direction(classic_maze, Position(1, 1), Position(1, 5))
        assert direction is Direction.DOWN

    def test_none_si_inatteignable(self, classic_maze):
        interieur = next(iter(classic_maze.house))
        assert pf.next_direction(classic_maze, Position(1, 1), interieur) is Direction.NONE

    def test_none_si_deja_arrive(self, classic_maze):
        assert pf.next_direction(classic_maze, Position(1, 1), Position(1, 1)) is Direction.NONE


class TestDistanceMap:
    def test_couvre_tout_le_labyrinthe_accessible(self, classic_maze):
        carte = pf.distance_map(classic_maze, classic_maze.pacman_start)
        assert (classic_maze.pellets | classic_maze.power_pellets) <= set(carte)

    def test_coherente_avec_le_bfs(self, classic_maze):
        depart = Position(1, 1)
        carte = pf.distance_map(classic_maze, depart)
        cible = Position(26, 29)
        assert carte[cible] == len(pf.bfs_path(classic_maze, depart, cible)) - 1

    def test_le_depart_est_a_distance_nulle(self, classic_maze):
        carte = pf.distance_map(classic_maze, Position(1, 1))
        assert carte[Position(1, 1)] == 0
