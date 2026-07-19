"""Tests du canal WebSocket temps reel."""

import pytest
from fastapi.testclient import TestClient

from pacman.api.server import app
from pacman.api.sessions import SessionStore


@pytest.fixture
def client():
    app.state.sessions = SessionStore()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def game_id(client) -> str:
    return client.post("/api/games").json()["state"]["id"]


def lire_jusqua(ws, predicat, limite: int = 400):
    """Consomme les images jusqu'a satisfaire `predicat`."""
    for _ in range(limite):
        message = ws.receive_json()
        if predicat(message):
            return message
    raise AssertionError("message jamais recu")


class TestConnexion:
    def test_partie_inconnue_refusee(self, client):
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as info:
            with client.websocket_connect("/ws/games/inconnu") as ws:
                ws.receive_json()
        assert info.value.code == 1008

    def test_premier_message_contient_le_plan_complet(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            init = ws.receive_json()
            assert init["type"] == "init"
            assert init["maze"]["width"] == 28
            assert len(init["state"]["pellets"]) == 240
            assert init["state"]["state"] == "ready"

    def test_les_images_suivantes_sont_des_etats(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()  # init
            image = ws.receive_json()
            assert image["type"] == "state"
            assert image["tick"] >= 1
            # Les pastilles ne sont plus renvoyees : le client les retire lui-meme.
            assert "pellets" not in image

    def test_la_partie_avance_toute_seule(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            premier = ws.receive_json()["tick"]
            plus_tard = lire_jusqua(ws, lambda m: m.get("tick", 0) > premier + 20)
            assert plus_tard["tick"] > premier

    def test_le_joueur_est_enregistre_comme_abonne(self, client, game_id):
        store = client.app.state.sessions
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            assert len(store.get(game_id).subscribers) == 1

    def test_la_simulation_sarrete_sans_spectateur(self, client, game_id):
        store = client.app.state.sessions
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            ws.receive_json()
        session = store.get(game_id)
        assert session.subscribers == set()


class TestCommandes:
    def test_input_deplace_pacman(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            depart = lire_jusqua(ws, lambda m: m.get("state") == "playing")
            ws.send_json({"action": "input", "direction": "left"})
            apres = lire_jusqua(
                ws, lambda m: m.get("pacman", {}).get("x", 99) < depart["pacman"]["x"]
            )
            assert apres["pacman"]["x"] < depart["pacman"]["x"]

    def test_direction_invalide_signalee_sans_couper(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            ws.send_json({"action": "input", "direction": "diagonale"})
            erreur = lire_jusqua(ws, lambda m: m["type"] == "error")
            assert "direction inconnue" in erreur["message"]
            # La partie continue malgre l'erreur.
            assert lire_jusqua(ws, lambda m: m["type"] == "state")

    def test_action_inconnue_signalee(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            ws.send_json({"action": "danser"})
            erreur = lire_jusqua(ws, lambda m: m["type"] == "error")
            assert "action inconnue" in erreur["message"]

    def test_ping_pong(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            ws.send_json({"action": "ping"})
            assert lire_jusqua(ws, lambda m: m["type"] == "pong")

    def test_pause_et_reprise(self, client, game_id):
        with client.websocket_connect(f"/ws/games/{game_id}") as ws:
            ws.receive_json()
            ws.send_json({"action": "pause"})
            fige = lire_jusqua(ws, lambda m: m.get("state") == "paused")
            assert fige["state"] == "paused"
            ws.send_json({"action": "resume"})
            repris = lire_jusqua(ws, lambda m: m.get("state") in ("ready", "playing"))
            assert repris["state"] in ("ready", "playing")


class TestPlusieursSpectateurs:
    def test_une_seule_simulation_pour_tous(self, client, game_id):
        # Deux onglets ouverts ne doivent pas faire tourner la partie deux fois
        # plus vite : c'est le piege d'une boucle par client.
        with client.websocket_connect(f"/ws/games/{game_id}") as a:
            a.receive_json()
            with client.websocket_connect(f"/ws/games/{game_id}") as b:
                b.receive_json()
                image_a = lire_jusqua(a, lambda m: m["type"] == "state")
                image_b = lire_jusqua(b, lambda m: m["type"] == "state")
                # Les deux clients voient la meme partie, au meme identifiant.
                assert image_a["id"] == image_b["id"] == game_id
                assert abs(image_a["tick"] - image_b["tick"]) < 30

    def test_le_depart_dun_client_ne_coupe_pas_lautre(self, client, game_id):
        store = client.app.state.sessions
        with client.websocket_connect(f"/ws/games/{game_id}") as a:
            a.receive_json()
            with client.websocket_connect(f"/ws/games/{game_id}") as b:
                b.receive_json()
                assert len(store.get(game_id).subscribers) == 2
            assert len(store.get(game_id).subscribers) == 1
            assert lire_jusqua(a, lambda m: m["type"] == "state")
