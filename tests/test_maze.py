import pytest

from pacman.core.geometry import Direction, Position
from pacman.core.maze import Maze, MazeError, Tile


class TestChargement:
    def test_dimensions_et_departs(self, small_maze: Maze):
        assert (small_maze.width, small_maze.height) == (9, 7)
        assert small_maze.pacman_start == Position(4, 5)
        assert small_maze.ghost_starts == {"blinky": Position(3, 3), "pinky": Position(5, 3)}

    def test_les_departs_ne_sont_pas_des_murs(self, small_maze: Maze):
        # Les lettres de depart marquent une case libre : sans cela, une entite
        # naitrait dans un mur et ne pourrait plus bouger.
        assert small_maze.tile_at(small_maze.pacman_start) is Tile.EMPTY

    def test_pastilles_recensees(self, small_maze: Maze):
        assert Position(1, 1) in small_maze.pellets
        assert small_maze.pellets.isdisjoint(small_maze.power_pellets)

    def test_niveau_classique_a_244_pastilles(self, classic_maze: Maze):
        assert len(classic_maze.pellets) == 240
        assert len(classic_maze.power_pellets) == 4

    def test_lignes_de_largeurs_differentes_refusees(self):
        with pytest.raises(MazeError, match="largeurs"):
            Maze.from_text("####\n###\n")

    def test_caractere_inconnu_refuse(self):
        with pytest.raises(MazeError, match="caractere inconnu"):
            Maze.from_text("###\n#X#\n###")

    def test_labyrinthe_sans_pacman_refuse(self):
        with pytest.raises(MazeError, match="Pac-Man"):
            Maze.from_text("####\n#..#\n####")

    def test_labyrinthe_inconnu(self):
        with pytest.raises(MazeError):
            Maze.load("nexiste-pas")


class TestGrille:
    def test_hors_grille_vaut_mur(self, small_maze: Maze):
        assert small_maze.is_wall(Position(-5, -5))
        assert not small_maze.contains(Position(100, 0))

    def test_porte_infranchissable_par_defaut(self, small_maze: Maze):
        door = next(iter(small_maze.doors))
        assert not small_maze.is_walkable(door)
        assert small_maze.is_walkable(door, through_door=True)

    def test_maison_detectee_derriere_la_porte(self, small_maze: Maze):
        assert small_maze.in_house(Position(3, 3))
        assert small_maze.in_house(Position(5, 3))
        # La detection ne doit pas fuir hors de la maison.
        assert not small_maze.in_house(small_maze.pacman_start)

    def test_maison_close_dans_le_niveau_classique(self, classic_maze: Maze):
        assert 0 < len(classic_maze.house) < 30


class TestDeplacement:
    def test_tunnel_replie_sur_le_bord_oppose(self, small_maze: Maze):
        gauche = Position(0, 3)
        assert small_maze.is_tunnel(gauche)
        assert small_maze.step(gauche, Direction.LEFT) == Position(8, 3)

    def test_step_normal_ne_replie_pas(self, small_maze: Maze):
        assert small_maze.step(Position(4, 5), Direction.LEFT) == Position(3, 5)

    def test_neighbors_exclut_les_murs(self, small_maze: Maze):
        voisins = dict(small_maze.neighbors(Position(1, 1)))
        assert Direction.UP not in voisins
        assert voisins[Direction.RIGHT] == Position(2, 1)

    def test_neighbors_suit_lordre_de_priorite(self, classic_maze: Maze):
        directions = [d for d, _ in classic_maze.neighbors(Position(6, 5))]
        assert directions == sorted(directions, key=Direction.moves().index)

    def test_intersection(self, classic_maze: Maze):
        assert classic_maze.is_intersection(Position(6, 5))
        assert not classic_maze.is_intersection(Position(1, 2))


def test_toutes_les_pastilles_sont_atteignables(classic_maze: Maze):
    # Une pastille enfermee rendrait le niveau infinissable : la regression
    # serait invisible a l'oeil sur le fichier texte.
    from collections import deque

    vus = {classic_maze.pacman_start}
    file = deque(vus)
    while file:
        for _, voisin in classic_maze.neighbors(file.popleft()):
            if voisin not in vus:
                vus.add(voisin)
                file.append(voisin)

    assert (classic_maze.pellets | classic_maze.power_pellets) <= vus
