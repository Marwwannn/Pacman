"""L'IA au volant d'une partie servie en temps reel.

La promesse a tenir est simple a enoncer : l'agent que l'on regarde jouer dans
le navigateur est EXACTEMENT celui qui a ete mesure. Le test central compare
donc, case par case, une partie pilotee par le serveur et la meme partie jouee
par l'environnement d'entrainement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pacman.api.pilot import PILOTES, POIDS_RETENUS, Pilot, build_pilot
from pacman.api.server import app
from pacman.api.sessions import SessionStore
from pacman.core.game import Game, GameState
from pacman.core.geometry import Direction
from pacman.rl.agents import HeuristicAgent
from pacman.rl.environment import EnvConfig, PacmanEnv
from pacman.rl.metrics import metrics_for

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    app.state.sessions = SessionStore()
    with TestClient(app) as client:
        yield client


class TestConstruction:
    @pytest.mark.parametrize("nom", sorted(PILOTES))
    def test_chaque_pilote_du_comparatif_se_construit(self, classic_maze, nom):
        pilote = build_pilot(nom, classic_maze)
        assert isinstance(pilote, Pilot)
        assert pilote.name == nom

    def test_sans_nom_pas_de_pilote(self, classic_maze):
        assert build_pilot(None, classic_maze) is None

    def test_un_nom_inconnu_est_refuse_avec_la_liste(self, classic_maze):
        with pytest.raises(ValueError, match="aleatoire, heuristique, appris, recherche"):
            build_pilot("skynet", classic_maze)

    def test_le_modele_embarque_est_celui_du_rendu(self):
        """Les poids servis par `pacman-server` sont ceux du comparatif publie.

        Sans cette garde, on pourrait reentrainer, regenerer `results/` et
        laisser le serveur faire jouer un agent perime sans que rien ne le dise.
        """
        embarque = json.loads(
            (RACINE / "src" / "pacman" / "rl" / "weights" / POIDS_RETENUS).read_text("utf-8")
        )
        publie = json.loads((RACINE / "results" / "poids_4fantomes.json").read_text("utf-8"))
        assert embarque == publie


class TestAuVolant:
    def test_pacman_avance_et_mange_sans_aucune_entree(self, classic_maze):
        game = Game(classic_maze)
        pastilles = game.remaining_pellets
        pilote = build_pilot("heuristique", classic_maze)
        for _ in range(600):
            pilote.steer(game)
            game.tick()
        assert game.score > 0
        assert game.remaining_pellets < pastilles

    def test_le_pilote_ne_donne_que_des_directions_praticables(self, classic_maze):
        """Un agent qui demanderait un mur laisserait Pac-Man immobile."""
        game = Game(classic_maze)
        pilote = build_pilot("aleatoire", classic_maze)
        demandees = []
        original = game.set_direction

        def espion(direction):
            demandees.append((game.pacman.position, direction))
            original(direction)

        game.set_direction = espion
        for _ in range(900):
            pilote.steer(game)
            game.tick()

        assert demandees, "aucune direction donnee en 900 ticks"
        for position, direction in demandees:
            voisins = [d for d, _ in classic_maze.neighbors(position)]
            assert direction in voisins, f"{direction.name} demande depuis {position}, hors {voisins}"

    def test_le_pilote_joue_exactement_comme_l_environnement(self, classic_maze):
        """La garantie qui compte : on regarde bien l'agent qui a ete mesure.

        Meme agent, meme labyrinthe, aucune randomisation : la trajectoire de
        Pac-Man doit etre identique tick par tick entre la partie pilotee et
        l'environnement de `rl/` : jusqu'a la mort, puisque l'environnement n'a
        qu'une vie.
        """
        trace_env: list[tuple[int, object]] = []
        env = PacmanEnv(
            EnvConfig(ghosts=4, lives=1, randomize_start=False, randomize_ghosts=False),
            on_tick=lambda game, events: trace_env.append((game.tick_count, game.pacman.position)),
        )
        env.run_episode(HeuristicAgent(seed=1), seed=0)

        game = Game(classic_maze, lives=1)
        pilote = Pilot("heuristique", HeuristicAgent(seed=1), metrics_for(classic_maze))
        trace: list[tuple[int, object]] = []
        while game.state is not GameState.GAME_OVER and len(trace) < len(trace_env):
            pilote.steer(game)
            game.tick()
            trace.append((game.tick_count, game.pacman.position))

        commun = min(len(trace), len(trace_env)) - 1
        assert commun > 500, "partie trop courte pour prouver quoi que ce soit"
        assert trace[:commun] == trace_env[:commun]


class TestApi:
    def test_creer_une_partie_pilotee(self, client):
        reponse = client.post("/api/games", json={"pilot": "appris"})
        assert reponse.status_code == 201
        assert reponse.json()["pilot"] == "appris"

    def test_sans_pilote_le_champ_est_nul(self, client):
        assert client.post("/api/games").json()["pilot"] is None

    def test_un_pilote_inconnu_est_refuse(self, client):
        reponse = client.post("/api/games", json={"pilot": "skynet"})
        assert reponse.status_code == 422
        assert "skynet" in reponse.json()["detail"]

    def test_la_partie_pilotee_avance_sans_entree(self, client):
        game_id = client.post("/api/games", json={"pilot": "heuristique"}).json()["state"]["id"]
        etat = client.post(f"/api/games/{game_id}/tick", json={"ticks": 600}).json()
        assert etat["score"] > 0

    def test_les_entrees_du_joueur_sont_ignorees(self, client):
        """L'IA tient le volant : une direction tapee par un spectateur ne fait rien."""
        game_id = client.post("/api/games", json={"pilot": "heuristique"}).json()["state"]["id"]
        reponse = client.post(f"/api/games/{game_id}/input", json={"direction": "up"})
        assert reponse.status_code == 200
        session = app.state.sessions.get(game_id)
        assert session.game.pacman.desired_direction is Direction.NONE

    def test_la_pause_reste_au_spectateur(self, client):
        game_id = client.post("/api/games", json={"pilot": "heuristique"}).json()["state"]["id"]
        client.post(f"/api/games/{game_id}/tick", json={"ticks": 200})
        assert client.post(f"/api/games/{game_id}/pause").json()["state"] == "paused"
        assert client.post(f"/api/games/{game_id}/resume").json()["state"] != "paused"

    def test_sur_le_canal_temps_reel_l_ia_joue_sans_personne(self, client):
        """Le chemin que le navigateur emprunte vraiment : la boucle de diffusion.

        Personne n'envoie la moindre commande sur le canal ; Pac-Man doit
        pourtant changer de case et marquer des points.
        """
        game_id = client.post("/api/games", json={"pilot": "heuristique"}).json()["state"]["id"]
        # Le compte a rebours de depart est passe par l'API : le canal ne sert
        # ici qu'a observer le jeu en mouvement, pas a attendre qu'il commence.
        client.post(f"/api/games/{game_id}/tick", json={"ticks": 130})
        positions = set()
        score = 0
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            assert ws.receive_json()["type"] == "init"
            for _ in range(120):
                image = ws.receive_json()
                if image["type"] != "state":
                    continue
                positions.add((image["pacman"]["x"], image["pacman"]["y"]))
                score = image["score"]
        assert len(positions) > 5, "Pac-Man n'a pas bouge : l'IA ne tient pas le volant"
        assert score > 0
