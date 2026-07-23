"""Tests de l'API REST."""

import pytest
from fastapi.testclient import TestClient

from pacman.api.server import app
from pacman.api.sessions import SessionStore


@pytest.fixture
def client():
    # Un magasin neuf par test : les parties ne doivent pas fuir d'un test a l'autre.
    app.state.sessions = SessionStore()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def game_id(client) -> str:
    return client.post("/api/games").json()["state"]["id"]


class TestService:
    def test_health(self, client):
        reponse = client.get("/health")
        assert reponse.status_code == 200
        assert reponse.json()["status"] == "ok"

    def test_plan_du_labyrinthe(self, client):
        plan = client.get("/api/mazes/classic").json()
        assert (plan["width"], plan["height"]) == (28, 31)
        assert len(plan["rows"]) == 31
        assert len(plan["pellets"]) == 240
        assert len(plan["power_pellets"]) == 4

    def test_labyrinthe_inconnu(self, client):
        assert client.get("/api/mazes/nexiste-pas").status_code == 404


class TestFront:
    """Le client de jeu est servi par le meme serveur que l'API."""

    def test_la_racine_sert_le_client(self, client):
        reponse = client.get("/")
        assert reponse.status_code == 200
        assert reponse.headers["content-type"].startswith("text/html")
        assert "<canvas" in reponse.text

    def test_le_front_ne_masque_pas_lapi(self, client):
        # Le montage statique est sur "/" : il doit passer apres les routes API.
        assert client.get("/health").status_code == 200
        assert client.get("/api/mazes/classic").status_code == 200
        assert client.get("/docs").status_code == 200


class TestCreation:
    def test_creation_renvoie_plan_et_etat(self, client):
        reponse = client.post("/api/games")
        assert reponse.status_code == 201
        corps = reponse.json()
        assert corps["maze"]["name"] == "classic"
        etat = corps["state"]
        assert etat["state"] == "ready"
        assert etat["score"] == 0
        assert etat["lives"] == 3
        assert etat["remaining_pellets"] == 244
        # Les pastilles ne sont envoyees qu'ici, pour que le client parte complet.
        assert len(etat["pellets"]) == 240

    def test_les_quatre_fantomes_sont_decrits(self, client):
        etat = client.post("/api/games").json()["state"]
        assert [g["name"] for g in etat["ghosts"]] == ["blinky", "pinky", "inky", "clyde"]
        assert all(g["color"].startswith("#") for g in etat["ghosts"])

    def test_parametres_personnalises(self, client):
        etat = client.post(
            "/api/games", json={"level": 5, "lives": 1, "overflow_bug": False}
        ).json()["state"]
        assert etat["level"] == 5
        assert etat["lives"] == 1

    def test_parametres_invalides_refuses(self, client):
        assert client.post("/api/games", json={"level": 0}).status_code == 422
        assert client.post("/api/games", json={"lives": 999}).status_code == 422

    def test_labyrinthe_inconnu_refuse(self, client):
        assert client.post("/api/games", json={"maze": "nexiste-pas"}).status_code == 404

    def test_chaque_partie_a_son_identifiant(self, client):
        a = client.post("/api/games").json()["state"]["id"]
        b = client.post("/api/games").json()["state"]["id"]
        assert a != b


class TestPartie:
    def test_lecture_de_letat(self, client, game_id):
        etat = client.get(f"/api/games/{game_id}").json()
        assert etat["id"] == game_id
        # Les pastilles sont omises par defaut : trop lourdes a chaque image.
        assert etat["pellets"] is None

    def test_resynchronisation_avec_les_pastilles(self, client, game_id):
        etat = client.get(f"/api/games/{game_id}", params={"include_pellets": True}).json()
        assert len(etat["pellets"]) == 240

    def test_partie_inconnue(self, client):
        assert client.get("/api/games/inconnu").status_code == 404

    def test_tick_avance_la_partie(self, client, game_id):
        etat = client.post(f"/api/games/{game_id}/tick", json={"ticks": 10}).json()
        assert etat["tick"] == 10

    def test_tick_sort_du_compte_a_rebours(self, client, game_id):
        etat = client.post(f"/api/games/{game_id}/tick", json={"ticks": 130}).json()
        assert etat["state"] == "playing"
        assert any(e["type"] == "round_start" for e in etat["events"])

    def test_input_puis_deplacement(self, client, game_id):
        client.post(f"/api/games/{game_id}/tick", json={"ticks": 130})
        avant = client.get(f"/api/games/{game_id}").json()["pacman"]
        client.post(f"/api/games/{game_id}/input", json={"direction": "left"})
        apres = client.post(f"/api/games/{game_id}/tick", json={"ticks": 10}).json()["pacman"]
        assert apres["x"] < avant["x"]

    def test_input_insensible_a_la_casse(self, client, game_id):
        assert (
            client.post(f"/api/games/{game_id}/input", json={"direction": "UP"}).status_code == 200
        )

    def test_direction_invalide(self, client, game_id):
        reponse = client.post(f"/api/games/{game_id}/input", json={"direction": "diagonale"})
        assert reponse.status_code == 422
        assert "direction inconnue" in reponse.text

    def test_pastilles_mangees_remontent_en_evenements(self, client, game_id):
        client.post(f"/api/games/{game_id}/tick", json={"ticks": 130})
        client.post(f"/api/games/{game_id}/input", json={"direction": "left"})
        etat = client.post(f"/api/games/{game_id}/tick", json={"ticks": 60}).json()
        assert any(e["type"] == "pellet" for e in etat["events"])
        assert etat["score"] > 0

    def test_pause_et_reprise(self, client, game_id):
        client.post(f"/api/games/{game_id}/tick", json={"ticks": 130})
        client.post(f"/api/games/{game_id}/input", json={"direction": "left"})
        client.post(f"/api/games/{game_id}/pause")
        fige = client.post(f"/api/games/{game_id}/tick", json={"ticks": 30}).json()
        assert fige["state"] == "paused"

        client.post(f"/api/games/{game_id}/resume")
        repris = client.post(f"/api/games/{game_id}/tick", json={"ticks": 30}).json()
        assert repris["pacman"]["x"] != fige["pacman"]["x"]

    def test_suppression(self, client, game_id):
        assert client.delete(f"/api/games/{game_id}").status_code == 204
        assert client.get(f"/api/games/{game_id}").status_code == 404

    def test_suppression_dune_partie_inconnue(self, client):
        assert client.delete("/api/games/inconnu").status_code == 404


class TestSessionStore:
    def test_purge_les_parties_abandonnees(self):
        store = SessionStore(timeout=10.0)
        store.create(now=0.0)
        assert len(store) == 1
        assert store.purge(now=5.0) == []
        assert store.purge(now=100.0)
        assert len(store) == 0

    def test_ne_purge_pas_une_partie_suivie_en_temps_reel(self):
        store = SessionStore(timeout=10.0)
        session = store.create(now=0.0)
        session.subscribers.add(object())
        assert store.purge(now=100.0) == []

    def test_limite_le_nombre_de_parties(self):
        from pacman.api.sessions import SessionError

        store = SessionStore(max_sessions=2)
        store.create(now=0.0)
        store.create(now=0.0)
        with pytest.raises(SessionError):
            store.create(now=0.0)

    def test_le_plan_nest_charge_quune_fois(self):
        store = SessionStore()
        assert store.maze("classic") is store.maze("classic")
