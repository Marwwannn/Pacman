"""Fruits et meilleurs scores."""

import json

import pytest
from fastapi.testclient import TestClient

from pacman.api.scores import ScoreBoard, ScoreSubmission
from pacman.api.server import app
from pacman.api.sessions import SessionStore
from pacman.core import rules
from pacman.core.game import Game
from pacman.core.geometry import Direction


class TestFruits:
    def test_le_labyrinthe_declare_une_case_a_fruit(self, classic_maze):
        assert classic_maze.fruit_start is not None
        assert not classic_maze.is_wall(classic_maze.fruit_start)

    def test_case_par_defaut_si_le_marqueur_est_absent(self, small_maze):
        # Sans 'F', le fruit apparait au depart de Pac-Man plutot que nulle part.
        assert small_maze.fruit_start == small_maze.pacman_start

    def test_apparait_au_palier_de_pastilles(self, game):
        assert game.fruit is None
        game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        game._maybe_spawn_fruit()
        assert game.fruit == game.maze.fruit_start
        assert any(e.type == "fruit_spawn" for e in game.events)

    def test_un_seul_fruit_par_palier(self, game):
        game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        game._maybe_spawn_fruit()
        game.fruit = None
        game._maybe_spawn_fruit()  # meme palier : rien de plus
        assert game.fruit is None

    def test_deux_fruits_au_maximum(self, game):
        for palier in rules.FRUIT_DOT_TRIGGERS:
            game._dots_eaten = palier
            game._maybe_spawn_fruit()
            game.fruit = None
        game._dots_eaten = 999
        game._maybe_spawn_fruit()
        assert game.fruit is None

    def test_disparait_apres_un_temps(self, game):
        game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        game._maybe_spawn_fruit()
        game.run(rules.FRUIT_DURATION + 2)
        assert game.fruit is None

    def test_manger_le_fruit_rapporte(self, game):
        game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        game._maybe_spawn_fruit()
        # On place Pac-Man juste a cote, face au fruit.
        cible = game.fruit
        game.pacman.position = game.pacman.previous_position = cible.moved(Direction.DOWN)
        game.set_direction(Direction.UP)
        avant = game.score
        for _ in range(10):
            game.tick()
            if game.fruit is None:
                break
        assert game.score > avant
        assert game.fruit is None

    def test_valeur_croissante_selon_le_niveau(self):
        assert rules.fruit_for(1) == ("cerise", 100)
        assert rules.fruit_for(2)[1] > rules.fruit_for(1)[1]
        # Au-dela du tableau, on garde le dernier fruit.
        assert rules.fruit_for(99) == rules.FRUITS[-1]

    def test_le_fruit_ne_survit_pas_a_une_vie_perdue(self, game):
        game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        game._maybe_spawn_fruit()
        assert game.fruit is not None
        game._place_entities()
        assert game.fruit is None

    def test_les_fruits_reviennent_au_niveau_suivant(self, classic_maze):
        game = Game(classic_maze)
        game._fruits_spawned = 2
        game.pellets.clear()
        game.power_pellets.clear()
        for _ in range(500):
            game.tick()
            if game.level == 2:
                break
        assert game._fruits_spawned == 0


class TestScoreBoard:
    def test_classement_trie(self):
        board = ScoreBoard()
        for score in (100, 900, 500):
            board.submit(ScoreSubmission(name="X", score=score))
        assert [e.score for e in board.top()] == [900, 500, 100]

    def test_taille_limitee(self):
        board = ScoreBoard(size=3)
        for score in range(1, 10):
            board.submit(ScoreSubmission(name="X", score=score * 100))
        assert len(board) == 3
        assert board.top()[0].score == 900

    def test_score_trop_faible_non_classe(self):
        board = ScoreBoard(size=2)
        board.submit(ScoreSubmission(name="A", score=500))
        board.submit(ScoreSubmission(name="B", score=400))
        _, rang = board.submit(ScoreSubmission(name="C", score=10))
        assert rang is None
        assert len(board) == 2

    def test_score_nul_non_classe(self):
        board = ScoreBoard()
        assert board.qualifies(0) is False

    def test_nom_nettoye_et_borne(self):
        # Le nom finit affiche chez les autres joueurs : pas de balise ni de roman.
        entree, _ = ScoreBoard().submit(ScoreSubmission(name="<script>alert(1)</script>", score=10))
        assert "<" not in entree.name and ">" not in entree.name
        assert len(entree.name) <= 12

    def test_nom_vide_remplace(self):
        entree, _ = ScoreBoard().submit(ScoreSubmission(name="!!!", score=10))
        assert entree.name == "ANONYME"

    def test_persistance(self, tmp_path):
        chemin = tmp_path / "scores.json"
        board = ScoreBoard(chemin)
        board.submit(ScoreSubmission(name="MARWAN", score=4200, level=3))
        assert json.loads(chemin.read_text(encoding="utf-8"))[0]["score"] == 4200

        recharge = ScoreBoard(chemin)
        assert recharge.top()[0].name == "MARWAN"

    def test_fichier_corrompu_ne_bloque_pas_le_demarrage(self, tmp_path):
        chemin = tmp_path / "scores.json"
        chemin.write_text("{ ceci n'est pas du json", encoding="utf-8")
        assert ScoreBoard(chemin).top() == []


class TestScoresApi:
    @pytest.fixture
    def client(self, tmp_path):
        app.state.sessions = SessionStore()
        app.state.scores = ScoreBoard(tmp_path / "scores.json")
        with TestClient(app) as client:
            yield client

    def test_classement_vide_au_depart(self, client):
        assert client.get("/api/scores").json() == []

    def test_soumission_et_lecture(self, client):
        reponse = client.post("/api/scores", json={"name": "MARWAN", "score": 3000, "level": 2})
        assert reponse.status_code == 201
        assert reponse.json() == {
            "entry": {"name": "MARWAN", "score": 3000, "level": 2},
            "rank": 1,
            "ranked": True,
        }
        assert client.get("/api/scores").json()[0]["name"] == "MARWAN"

    def test_score_negatif_refuse(self, client):
        assert client.post("/api/scores", json={"score": -5}).status_code == 422

    def test_fruit_expose_dans_letat(self, client):
        game_id = client.post("/api/games").json()["state"]["id"]
        session = client.app.state.sessions.get(game_id)
        session.game._dots_eaten = rules.FRUIT_DOT_TRIGGERS[0]
        session.game._maybe_spawn_fruit()
        fruit = client.get(f"/api/games/{game_id}").json()["fruit"]
        assert fruit["name"] == "cerise"
        assert fruit["points"] == 100
