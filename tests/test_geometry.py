from pacman.core.geometry import Direction, Position


class TestPosition:
    def test_moved_applique_le_vecteur(self):
        assert Position(3, 4).moved(Direction.UP) == Position(3, 3)
        assert Position(3, 4).moved(Direction.RIGHT) == Position(4, 4)
        assert Position(3, 4).moved(Direction.NONE) == Position(3, 4)

    def test_positions_egales_sont_interchangeables(self):
        # Position sert de cle de dictionnaire et d'element d'ensemble partout
        # dans le moteur : l'egalite structurelle est une garantie, pas un detail.
        assert Position(1, 2) == Position(1, 2)
        assert len({Position(1, 2), Position(1, 2)}) == 1

    def test_manhattan(self):
        assert Position(0, 0).manhattan(Position(3, 4)) == 7

    def test_squared_distance_evite_la_racine(self):
        assert Position(0, 0).squared_distance(Position(3, 4)) == 25

    def test_squared_distance_ordonne_comme_la_vraie_distance(self):
        origin = Position(0, 0)
        near, far = Position(1, 2), Position(3, 3)
        assert origin.squared_distance(near) < origin.squared_distance(far)


class TestDirection:
    def test_opposite(self):
        assert Direction.UP.opposite is Direction.DOWN
        assert Direction.LEFT.opposite is Direction.RIGHT
        assert Direction.NONE.opposite is Direction.NONE

    def test_ordre_de_priorite_du_jeu_dorigine(self):
        # Cet ordre departage les fantomes a distance egale. Le changer modifie
        # leur trajectoire : il est verrouille par ce test.
        assert Direction.moves() == (
            Direction.UP,
            Direction.LEFT,
            Direction.DOWN,
            Direction.RIGHT,
        )

    def test_none_nest_pas_un_deplacement(self):
        assert Direction.NONE not in Direction.moves()
