"""Comportement du moteur : score, vies, modes, collisions, enchainements."""

import pytest

from pacman.core import rules
from pacman.core.entities import GhostMode
from pacman.core.game import Game, GameState
from pacman.core.geometry import Direction, Position


def place(game: Game, position: Position) -> None:
    """Teleporte Pac-Man, en gardant l'etat coherent pour les collisions."""
    game.pacman.position = game.pacman.previous_position = position


def avancer_jusqua(game: Game, predicat, limite: int = 5000):
    """Fait tourner la partie jusqu'a ce que `predicat` soit vrai."""
    evenements = []
    for _ in range(limite):
        evenements.extend(game.tick())
        if predicat(game):
            return evenements
    raise AssertionError("condition jamais atteinte")


def types(evenements) -> list[str]:
    return [e.type for e in evenements]


class TestDemarrage:
    def test_commence_par_un_compte_a_rebours(self, classic_maze):
        game = Game(classic_maze)
        assert game.state is GameState.READY
        assert game.score == 0
        assert game.lives == rules.STARTING_LIVES
        assert game.remaining_pellets == 244

    def test_passe_en_jeu_apres_le_compte_a_rebours(self, classic_maze):
        game = Game(classic_maze)
        game.run(rules.READY_DURATION + 1)
        assert game.state is GameState.PLAYING

    def test_pacman_immobile_pendant_le_compte_a_rebours(self, classic_maze):
        game = Game(classic_maze)
        game.set_direction(Direction.LEFT)
        game.run(rules.READY_DURATION - 1)
        assert game.pacman.position == classic_maze.pacman_start

    def test_blinky_demarre_dehors(self, game):
        assert game.ghost("blinky").mode is not GhostMode.HOUSE

    def test_inky_et_clyde_attendent_dans_la_maison(self, game):
        assert game.ghost("inky").mode is GhostMode.HOUSE
        assert game.ghost("clyde").mode is GhostMode.HOUSE


class TestScore:
    def test_manger_une_pastille(self, game):
        game.set_direction(Direction.LEFT)
        evenements = avancer_jusqua(game, lambda g: g.score > 0)
        assert game.score == rules.POINTS_PELLET
        assert "pellet" in types(evenements)
        assert game.remaining_pellets == 243

    def test_une_pastille_ne_se_mange_quune_fois(self, game):
        game.set_direction(Direction.LEFT)
        avancer_jusqua(game, lambda g: g.score > 0)
        position = game.pacman.position
        assert position not in game.pellets

    def test_super_pastille_vaut_plus(self, game):
        place(game, Position(1, 2))
        game.set_direction(Direction.DOWN)
        avancer_jusqua(game, lambda g: g.frightened)
        assert game.score >= rules.POINTS_POWER_PELLET

    def test_vie_supplementaire_au_seuil(self, game):
        game._add_score(rules.EXTRA_LIFE_SCORE)
        assert game.lives == rules.STARTING_LIVES + 1
        # Le seuil suivant ne doit pas se declencher immediatement.
        game._add_score(10)
        assert game.lives == rules.STARTING_LIVES + 1


class TestModeEffraye:
    @pytest.fixture
    def effraye(self, game):
        place(game, Position(1, 2))
        game.set_direction(Direction.DOWN)
        avancer_jusqua(game, lambda g: g.frightened)
        return game

    def test_les_fantomes_actifs_deviennent_vulnerables(self, effraye):
        actifs = [g for g in effraye.ghosts if g.mode is GhostMode.FRIGHTENED]
        assert actifs

    def test_manger_un_fantome_suit_la_chaine(self, effraye):
        blinky = effraye.ghost("blinky")
        blinky.position = blinky.previous_position = effraye.pacman.position
        effraye._resolve_collisions()
        assert blinky.mode is GhostMode.EATEN
        assert any(e.type == "ghost_eaten" and e.payload["points"] == 200 for e in effraye.events)

    def test_chaine_200_400_800_1600(self, effraye):
        points = []
        for fantome in effraye.ghosts:
            fantome.set_mode(GhostMode.FRIGHTENED, reverse=False)
            fantome.position = fantome.previous_position = effraye.pacman.position
            effraye.events = []  # les evenements ne sont vides qu'au debut d'un tick
            effraye._resolve_collisions()
            points.extend(e.payload["points"] for e in effraye.events if e.type == "ghost_eaten")
        assert points == [200, 400, 800, 1600]

    def test_seffiloche_et_prend_fin(self, effraye):
        avancer_jusqua(effraye, lambda g: not g.frightened, limite=1000)
        assert not effraye.pacman.energized
        assert all(g.mode is not GhostMode.FRIGHTENED for g in effraye.ghosts)

    def test_les_yeux_rentrent_a_la_maison(self, effraye):
        blinky = effraye.ghost("blinky")
        blinky.position = blinky.previous_position = Position(1, 1)
        blinky.set_mode(GhostMode.EATEN, reverse=False)
        avancer_jusqua(effraye, lambda g: blinky.mode is not GhostMode.EATEN, limite=2000)
        assert blinky.mode in (GhostMode.LEAVING, GhostMode.SCATTER, GhostMode.CHASE)

    def test_un_fantome_mange_ne_tue_pas(self, effraye):
        blinky = effraye.ghost("blinky")
        blinky.set_mode(GhostMode.EATEN, reverse=False)
        blinky.position = blinky.previous_position = effraye.pacman.position
        vies = effraye.lives
        effraye._resolve_collisions()
        assert effraye.lives == vies
        assert effraye.state is not GameState.DYING


class TestCollisions:
    def test_un_fantome_actif_tue_pacman(self, game):
        blinky = game.ghost("blinky")
        blinky.position = blinky.previous_position = game.pacman.position
        game.tick()
        assert game.state is GameState.DYING
        assert game.lives == rules.STARTING_LIVES - 1

    def test_croisement_frontal_detecte(self, game):
        # Sans ce controle, Pac-Man et un fantome echangeraient leurs cases
        # sans jamais se toucher.
        blinky = game.ghost("blinky")
        blinky.previous_position = game.pacman.position
        blinky.position = game.pacman.previous_position = Position(13, 22)
        game.pacman.position = blinky.previous_position
        assert game._touching(blinky)

    def test_un_fantome_dans_la_maison_ne_tue_pas(self, game):
        clyde = game.ghost("clyde")
        assert clyde.mode is GhostMode.HOUSE
        clyde.position = clyde.previous_position = game.pacman.position
        assert game._resolve_collisions() is False

    def test_reprise_apres_la_mort(self, game):
        blinky = game.ghost("blinky")
        blinky.position = blinky.previous_position = game.pacman.position
        game.tick()
        avancer_jusqua(game, lambda g: g.state is GameState.READY)
        assert game.pacman.position == game.maze.pacman_start
        assert game.lives == rules.STARTING_LIVES - 1

    def test_game_over_a_court_de_vies(self, classic_maze):
        game = Game(classic_maze, lives=1)
        game.run(rules.READY_DURATION + 1)
        blinky = game.ghost("blinky")
        blinky.position = blinky.previous_position = game.pacman.position
        game.tick()
        avancer_jusqua(game, lambda g: g.state is GameState.GAME_OVER)
        assert game.is_over
        # Une partie terminee ne bouge plus.
        assert game.tick() == []


class TestNiveaux:
    def test_niveau_termine_quand_tout_est_mange(self, game):
        game.pellets.clear()
        game.power_pellets.clear()
        # Une pastille se mange en arrivant dessus : on la pose devant Pac-Man.
        game.pellets.add(game.pacman.position.moved(Direction.LEFT))
        game.set_direction(Direction.LEFT)
        avancer_jusqua(game, lambda g: g.state is GameState.LEVEL_COMPLETE)
        assert game.remaining_pellets == 0

    def test_le_niveau_suivant_recharge_les_pastilles(self, game):
        game.pellets.clear()
        game.power_pellets.clear()
        avancer_jusqua(game, lambda g: g.level == 2, limite=1000)
        assert game.remaining_pellets == 244
        assert game.state is GameState.READY

    def test_la_difficulte_monte(self):
        facile, dur = rules.rules_for(1), rules.rules_for(10)
        assert dur.ghost_speed > facile.ghost_speed
        assert dur.frightened_duration < facile.frightened_duration
        assert dur.dot_limits["clyde"] < facile.dot_limits["clyde"]

    def test_plus_de_mode_effraye_aux_niveaux_extremes(self):
        assert rules.rules_for(30).frightened_duration == 0


class TestVagues:
    def test_alternance_scatter_chase(self, game):
        evenements = avancer_jusqua(
            game, lambda g: any(e.type == "wave" for e in g.events), limite=1000
        )
        vague = next(e for e in evenements if e.type == "wave")
        assert vague.payload["mode"] == GhostMode.CHASE.value

    def test_les_fantomes_sortent_au_compteur_de_pastilles(self, game):
        game._dots_eaten = 100
        game._release_ghosts()
        assert all(g.mode is not GhostMode.HOUSE for g in game.ghosts)


class TestPause:
    def test_la_pause_gele_la_partie(self, game):
        position = game.pacman.position
        game.set_direction(Direction.LEFT)
        game.pause()
        game.run(50)
        assert game.pacman.position == position
        game.resume()
        game.run(5)
        assert game.pacman.position != position

    def test_on_ne_met_pas_en_pause_une_partie_finie(self, classic_maze):
        game = Game(classic_maze)
        game.state = GameState.GAME_OVER
        game.pause()
        assert game.state is GameState.GAME_OVER


class TestDeterminisme:
    def test_deux_parties_identiques_se_deroulent_pareil(self, classic_maze):
        def jouer():
            game = Game(classic_maze)
            for tick in range(600):
                if tick % 37 == 0:
                    game.set_direction(Direction.moves()[tick // 37 % 4])
                game.tick()
            return (
                game.score,
                game.pacman.position,
                [(g.name, g.position, g.mode) for g in game.ghosts],
            )

        assert jouer() == jouer()

    def test_aucune_dependance_a_lhorloge(self, game):
        # Le moteur n'avance que par tick : sans appel, rien ne change.
        etat = (game.tick_count, game.pacman.position, game.score)
        assert (game.tick_count, game.pacman.position, game.score) == etat
