"""Tests du paquet `rl` : environnement, features, agents, protocole d'evaluation.

Une bonne partie de ces tests garde des proprietes qu'aucune assertion de score
ne remplacerait : un agent qui apprend peut aller mieux ou moins bien d'une
version a l'autre, mais l'environnement, lui, doit rester exact.
"""

from __future__ import annotations

import json
from math import inf

import pytest

from pacman.core.entities import GhostMode
from pacman.core.game import Game
from pacman.core.geometry import Direction
from pacman.core.maze import Maze
from pacman.rl.agents import ApproximateQAgent, HeuristicAgent, RandomAgent
from pacman.rl.environment import EnvConfig, PacmanEnv
from pacman.rl.evaluation import EVALUATION_SEEDS, evaluate
from pacman.rl.features import FEATURE_NAMES, extract, named
from pacman.rl.metrics import metrics_for
from pacman.rl.rewards import RewardConfig
from pacman.rl.training import Hyper, train


@pytest.fixture
def metrics(classic_maze: Maze):
    return metrics_for(classic_maze)


@pytest.fixture
def env() -> PacmanEnv:
    return PacmanEnv(EnvConfig(ghosts=1))


class TestMesuresDuLabyrinthe:
    """Les chiffres qui justifient de ne decider qu'aux intersections."""

    def test_le_labyrinthe_classique_a_bien_300_cases_et_34_choix(self, metrics):
        # Ces deux nombres portent toute la conception du paquet : 89 % des
        # cases ne sont que des couloirs. S'ils changent, le harnais doit etre
        # rediscute, pas simplement adapte.
        assert len(metrics.walkable) == 300
        assert len(metrics.decision_tiles) == 34

    def test_la_maison_des_fantomes_n_est_pas_praticable(self, metrics, classic_maze):
        assert not (metrics.walkable & classic_maze.house)

    def test_les_distances_sont_symetriques_et_reelles(self, metrics):
        a, b = sorted(metrics.decision_tiles, key=lambda p: (p.y, p.x))[:2]
        assert metrics.distance(a, b) == metrics.distance(b, a)
        # Un mur separe forcement deux cases plus eloignees qu'a vol d'oiseau.
        assert metrics.distance(a, b) >= a.manhattan(b)

    def test_une_case_inatteignable_est_infiniment_loin(self, metrics, classic_maze):
        inside = next(iter(classic_maze.house))
        assert metrics.distance(classic_maze.pacman_start, inside) == inf
        assert metrics.proximity(inf) == 0.0

    def test_la_proximite_decroit_avec_la_distance(self, metrics):
        assert metrics.proximity(0) == 1.0
        assert metrics.proximity(1) > metrics.proximity(5) > 0.0

    def test_les_mesures_sont_mises_en_cache(self, classic_maze):
        assert metrics_for(classic_maze) is metrics_for(Maze.load("classic"))


class TestPointsDeDecision:
    """Un pas d'environnement = une intersection, jamais un tick."""

    def test_un_couloir_n_est_pas_un_point_de_decision(self, metrics):
        couloirs = [
            tile
            for tile in metrics.walkable
            if metrics.exits(tile) == 2 and tile not in metrics.decision_tiles
        ]
        assert couloirs
        for tile in couloirs[:20]:
            direction = metrics.maze.neighbors(tile)[0][0]
            assert not metrics.is_decision(tile, direction.opposite)

    def test_une_impasse_ne_laisse_que_le_demi_tour(self, metrics):
        impasses = [tile for tile in metrics.walkable if metrics.exits(tile) == 1]
        for tile in impasses:
            entree = metrics.maze.neighbors(tile)[0][0]
            # Arrive au fond, la seule direction restante est celle d'ou l'on
            # vient : l'environnement la joue lui-meme, sans demander l'avis
            # de l'agent.
            assert metrics.options(tile, entree.opposite) == []
            assert not metrics.is_decision(tile, entree.opposite)

    def test_chaque_pas_s_arrete_sur_un_vrai_choix(self, env):
        env.reset(EVALUATION_SEEDS)
        agent = RandomAgent(seed=3)
        for _ in range(15):
            if env.finished:
                break
            assert len(env.legal_actions()) >= 1
            assert env.metrics.is_decision(env.position, env.game.pacman.direction)
            env.step(agent.act(env.game, env.legal_actions(), env))

    def test_un_pas_avance_de_plusieurs_ticks(self, env):
        env.reset(EVALUATION_SEEDS)
        before = env.ticks
        env.step(env.legal_actions()[0])
        # Pac-Man avance de 0,8 case par unite de vitesse : une case demande
        # plusieurs ticks, et un pas de decision traverse tout un couloir.
        assert env.ticks - before >= 6

    def test_une_action_illegale_est_refusee(self, env):
        env.reset(EVALUATION_SEEDS)
        interdites = set(Direction.moves()) - set(env.legal_actions())
        if interdites:
            with pytest.raises(ValueError):
                env.step(next(iter(interdites)))

    def test_on_ne_joue_pas_apres_la_fin(self, env):
        env.reset(EVALUATION_SEEDS)
        agent = RandomAgent(seed=5)
        while not env.finished:
            env.step(agent.act(env.game, env.legal_actions(), env))
        with pytest.raises(RuntimeError):
            env.step(env.legal_actions()[0])


class TestDeterminismeEtVariete:
    """Le piege n°1 : un moteur deterministe fait memoriser au lieu d'apprendre."""

    def test_une_meme_graine_rejoue_la_meme_partie(self):
        env = PacmanEnv(EnvConfig(ghosts=4))
        premier = env.run_episode(RandomAgent(seed=1), EVALUATION_SEEDS)
        second = PacmanEnv(EnvConfig(ghosts=4)).run_episode(RandomAgent(seed=1), EVALUATION_SEEDS)
        assert premier == second

    def test_deux_graines_donnent_deux_parties_differentes(self, env):
        departs = {env.reset(EVALUATION_SEEDS + index).pacman.position for index in range(20)}
        # Sans randomisation du depart, l'agent apprendrait une sequence de
        # coups valable pour une seule partie.
        assert len(departs) > 1

    def test_le_depart_fixe_reste_disponible_mais_immobile(self, classic_maze):
        env = PacmanEnv(EnvConfig(randomize_start=False))
        departs = {env.reset(EVALUATION_SEEDS + index).pacman.position for index in range(5)}
        assert departs == {classic_maze.pacman_start}

    def test_les_fantomes_sont_resemes_par_la_graine(self):
        env = PacmanEnv(EnvConfig(ghosts=4))
        etats = []
        for seed in (EVALUATION_SEEDS, EVALUATION_SEEDS + 1):
            game = env.reset(seed)
            etats.append([ghost._rng_state for ghost in game.ghosts])
        assert etats[0] != etats[1]

    def test_la_case_de_depart_ne_porte_jamais_de_pastille(self, env):
        for index in range(30):
            game = env.reset(EVALUATION_SEEDS + index)
            assert game.pacman.position not in game.pellets
            assert game.pacman.position not in game.power_pellets

    def test_resemer_un_fantome_reste_reproductible(self, classic_maze):
        game = Game(classic_maze)
        ghost = game.ghosts[0]
        ghost.seed_rng(42)
        premier = [ghost._next_random(4) for _ in range(5)]
        ghost.seed_rng(42)
        assert [ghost._next_random(4) for _ in range(5)] == premier

    def test_le_curriculum_ne_garde_que_les_premiers_fantomes(self, classic_maze):
        game = Game(classic_maze)
        game.limit_ghosts(1)
        assert [ghost.name for ghost in game.ghosts] == ["blinky"]
        assert game.ghost("pinky") is None
        # Blinky doit rester : c'est la reference de position des autres.
        assert game.blinky_position == game.ghosts[0].position

    def test_limiter_a_plus_que_le_nombre_de_fantomes_ne_change_rien(self, classic_maze):
        game = Game(classic_maze)
        game.limit_ghosts(99)
        assert len(game.ghosts) == 4


class TestRecompenses:
    """Le piege n°2 : le bareme pese plus que alpha et gamma reunis."""

    def test_la_mort_domine_tout_le_reste(self):
        config = RewardConfig()
        assert config.death <= -10 * config.power_pellet
        assert config.death < -max(200, config.pellet * 40)

    def test_chaque_pas_de_decision_coute(self, env):
        env.reset(EVALUATION_SEEDS)
        # Sans ce cout, tourner en rond devant une super-pastille serait gratuit.
        assert env.rewards.step < 0

    def test_le_bareme_lit_les_evenements_du_moteur(self):
        from pacman.core.game import Event

        config = RewardConfig()
        events = [
            Event("pellet"),
            Event("power_pellet"),
            Event("ghost_eaten", {"points": 400}),
            Event("pacman_died", {"ghost": "blinky"}),
        ]
        assert config.from_events(events) == 10 + 50 + 400 - 500

    def test_le_score_brut_du_jeu_n_est_pas_la_recompense(self, env):
        # La prime de vie a 10 000 points creerait une marche impredictible.
        resultat = env.run_episode(RandomAgent(seed=2), EVALUATION_SEEDS)
        assert resultat["return"] != resultat["score"]

    def test_une_mort_est_comptee_une_seule_fois(self):
        env = PacmanEnv(EnvConfig(ghosts=4, lives=3))
        resultat = env.run_episode(RandomAgent(seed=4), EVALUATION_SEEDS + 3)
        assert resultat["deaths"] <= 3
        assert resultat["died"] == (resultat["deaths"] > 0)


class TestFeatures:
    """Douze nombres, tous bornes, tous calcules sur des distances reelles."""

    def test_toutes_les_features_restent_entre_zero_et_un(self, env):
        env.reset(EVALUATION_SEEDS)
        for _ in range(10):
            if env.finished:
                break
            for action in env.legal_actions():
                values = extract(env.game, action, env.metrics)
                assert len(values) == len(FEATURE_NAMES)
                assert all(0.0 <= value <= 1.0 for value in values)
            env.step(env.legal_actions()[0])

    def test_manger_une_pastille_est_vu(self, env):
        game = env.reset(EVALUATION_SEEDS)
        voisine = game.maze.step(game.pacman.position, env.legal_actions()[0])
        game.pellets.add(voisine)
        values = named(extract(game, env.legal_actions()[0], env.metrics))
        assert values["mange_pastille"] == 1.0
        assert values["proximite_pastille"] == 1.0

    def test_un_fantome_effraye_devient_une_proie(self, env):
        game = env.reset(EVALUATION_SEEDS)
        game.run(200)  # laisser les fantomes sortir de la maison
        ghost = game.ghosts[0]
        action = env.legal_actions()[0]

        ghost.set_mode(GhostMode.CHASE, reverse=False)
        chasse = named(extract(game, action, env.metrics))
        ghost.set_mode(GhostMode.FRIGHTENED, reverse=False)
        effraye = named(extract(game, action, env.metrics))

        assert chasse["proximite_chasseur"] > 0.0
        assert effraye["proximite_chasseur"] == 0.0
        assert effraye["proximite_proie"] > 0.0

    def test_le_demi_tour_est_signale(self, env):
        game = env.reset(EVALUATION_SEEDS)
        env.step(env.legal_actions()[0])
        retour = game.pacman.direction.opposite
        if retour in env.legal_actions():
            assert named(extract(game, retour, env.metrics))["demi_tour"] == 1.0

    def test_une_impasse_n_a_aucune_issue(self, env):
        game = env.reset(EVALUATION_SEEDS)
        impasses = [
            tile for tile in env.metrics.walkable if env.metrics.exits(tile) == 1
        ]
        if impasses:
            tile = impasses[0]
            direction = game.maze.neighbors(tile)[0][0]
            assert env.metrics.options(tile, direction.opposite) == []

    def test_les_distances_sont_celles_du_labyrinthe_pas_du_vol_d_oiseau(self, metrics):
        # Deux cases separees par un mur epais sont proches en ligne droite et
        # tres loin dans les faits : c'est precisement ce que les fantomes du
        # jeu ignorent, et ce que l'agent, lui, doit savoir.
        from pacman.core.pathfinding import torus_distance

        cases = sorted(metrics.walkable, key=lambda p: (p.y, p.x))[:40]
        paires = [(a, b) for a in cases for b in cases if metrics.distance(a, b) != inf]

        # Au moins une paire ou contourner coute vraiment plus cher.
        assert any(metrics.distance(a, b) > a.manhattan(b) for a, b in paires)
        # Et jamais de raccourci a travers un mur : la distance reelle ne peut
        # pas etre inferieure a la distance a vol d'oiseau, tunnels compris.
        assert all(
            metrics.distance(a, b) >= torus_distance(metrics.maze, a, b) for a, b in paires
        )


class TestAgents:
    def test_l_agent_aleatoire_ne_choisit_que_des_actions_legales(self, env):
        env.reset(EVALUATION_SEEDS)
        agent = RandomAgent(seed=1)
        for _ in range(10):
            if env.finished:
                break
            actions = env.legal_actions()
            assert agent.act(env.game, actions, env) in actions

    def test_l_heuristique_fuit_un_fantome_colle(self, env):
        game = env.reset(EVALUATION_SEEDS)
        game.run(300)
        agent = HeuristicAgent(metrics=env.metrics, seed=1)
        actions = env.legal_actions()
        if len(actions) >= 2:
            choix = agent.act(game, actions, env)
            danger = min(
                (
                    env.metrics.distance(game.maze.step(game.pacman.position, choix), ghost.position)
                    for ghost in game.ghosts
                    if ghost.is_active and ghost.mode is not GhostMode.FRIGHTENED
                ),
                default=inf,
            )
            pire = min(
                min(
                    (
                        env.metrics.distance(
                            game.maze.step(game.pacman.position, action), ghost.position
                        )
                        for ghost in game.ghosts
                        if ghost.is_active and ghost.mode is not GhostMode.FRIGHTENED
                    ),
                    default=inf,
                )
                for action in actions
            )
            assert danger >= pire

    def test_l_heuristique_bat_largement_le_hasard(self):
        config = EnvConfig(ghosts=1)
        hasard = evaluate(RandomAgent(seed=1), games=12, config=config)
        regles = evaluate(HeuristicAgent(seed=1), games=12, config=config)
        # Sans cet ecart, les deux bornes ne borneraient rien.
        assert regles.score_median > 2 * hasard.score_median

    def test_l_agent_q_part_de_poids_nuls_et_reste_legal(self, env):
        agent = ApproximateQAgent(metrics=env.metrics, seed=1)
        assert set(agent.weights) == set(FEATURE_NAMES)
        assert all(value == 0.0 for value in agent.weights.values())
        env.reset(EVALUATION_SEEDS)
        assert agent.act(env.game, env.legal_actions(), env) in env.legal_actions()

    def test_la_mise_a_jour_va_dans_le_sens_de_la_recompense(self, env):
        agent = ApproximateQAgent(metrics=env.metrics, seed=1)
        game = env.reset(EVALUATION_SEEDS)
        action = env.legal_actions()[0]
        values = extract(game, action, env.metrics)
        avant = agent.q_from(values)
        agent.update(values, 100.0, 0.0, alpha=0.05, gamma=0.9)
        assert agent.q_from(values) > avant

    def test_l_erreur_de_difference_temporelle_est_ecretee(self, env):
        agent = ApproximateQAgent(metrics=env.metrics, seed=1)
        game = env.reset(EVALUATION_SEEDS)
        values = extract(game, env.legal_actions()[0], env.metrics)
        # Une mort vaut -500 quand les features valent au plus 1 : sans
        # ecretage, un seul episode malheureux fait exploser les poids.
        erreur = agent.update(values, -100_000.0, 0.0, alpha=0.01, gamma=0.9, clip=100.0)
        assert erreur == -100.0

    def test_les_poids_se_relisent_a_l_identique(self, env, tmp_path):
        agent = ApproximateQAgent({"biais": 1.5, "demi_tour": -2.0}, metrics=env.metrics)
        chemin = tmp_path / "poids.json"
        agent.save(chemin)
        relu = ApproximateQAgent.load(chemin)
        assert relu.weights == agent.weights
        assert json.loads(chemin.read_text(encoding="utf-8"))["weights"]["biais"] == 1.5

    def test_un_poids_inconnu_est_ignore(self, env):
        agent = ApproximateQAgent({"inexistant": 3.0, "biais": 1.0})
        assert "inexistant" not in agent.weights
        assert agent.weights["biais"] == 1.0


class TestProtocoleEvaluation:
    """Les trois regles qui empechent un chiffre flatteur mais faux."""

    def test_les_graines_d_entrainement_sont_refusees_a_l_evaluation(self):
        with pytest.raises(ValueError, match="graines"):
            evaluate(RandomAgent(), games=2, offset=0)

    def test_l_evaluation_rend_mediane_et_dispersion(self):
        rapport = evaluate(RandomAgent(seed=1), games=8, config=EnvConfig(ghosts=1))
        assert rapport.games == 8
        assert rapport.score_min <= rapport.score_median <= rapport.score_max
        assert rapport.score_stdev >= 0
        assert 0.0 <= rapport.win_rate <= 1.0
        # Le meilleur run ne doit jamais etre confondu avec le resultat.
        assert rapport.as_dict()["score_median"] == rapport.score_median

    def test_deux_evaluations_du_meme_agent_donnent_le_meme_chiffre(self):
        config = EnvConfig(ghosts=1)
        premier = evaluate(RandomAgent(seed=1), games=6, config=config)
        second = evaluate(RandomAgent(seed=1), games=6, config=config)
        assert premier.as_dict() == second.as_dict()


class TestEntrainement:
    def test_un_entrainement_court_modifie_les_poids_et_reste_fini(self):
        agent, rapport = train(
            30,
            config=EnvConfig(ghosts=1),
            hyper=Hyper(alpha=0.02, epsilon=0.5),
            log_every=10,
        )
        assert rapport.episodes == 30
        assert len(rapport.windows) == 3
        assert any(value != 0.0 for value in agent.weights.values())
        assert all(abs(value) < 1e6 for value in agent.weights.values())

    def test_l_entrainement_n_utilise_jamais_les_graines_d_evaluation(self):
        from pacman.rl.evaluation import seeds_for
        from pacman.rl.training import TRAINING_SEEDS

        entrainement = set(seeds_for(5_000, offset=TRAINING_SEEDS))
        evaluation = set(seeds_for(1_000, offset=EVALUATION_SEEDS))
        assert not (entrainement & evaluation)

    def test_un_agent_entraine_depasse_le_hasard(self):
        # Volontairement court : on verifie que l'apprentissage progresse, pas
        # qu'il atteint un score donne (celui-la se mesure, il ne s'asserte pas).
        config = EnvConfig(ghosts=1)
        agent, _ = train(150, config=config, seed=3)
        appris = evaluate(agent, games=12, config=config)
        hasard = evaluate(RandomAgent(seed=1), games=12, config=config)
        assert appris.score_median > hasard.score_median


class TestLigneDeCommande:
    """La CLI est le chemin par lequel le projet sera relance : elle se teste."""

    def test_baselines_sort_les_deux_bornes(self, capsys):
        from pacman.rl.cli import main

        assert main(["baselines", "--ghosts", "1", "--games", "2", "--json"]) == 0
        rapports = json.loads(capsys.readouterr().out)
        assert [item["agent"] for item in rapports] == ["aleatoire", "heuristique"]

    def test_un_entrainement_ecrit_ses_poids(self, tmp_path, capsys):
        from pacman.rl.cli import main

        chemin = tmp_path / "poids.json"
        code = main(
            [
                "train",
                "--episodes", "8",
                "--games", "2",
                "--ghosts", "1",
                "--log-every", "0",
                "--json",
                "--out", str(chemin),
            ]
        )
        capsys.readouterr()
        assert code == 0
        assert set(json.loads(chemin.read_text(encoding="utf-8"))["weights"]) == set(FEATURE_NAMES)

    def test_reprendre_des_poids_demarre_tiede(self, tmp_path):
        from pacman.rl.cli import build_parser

        parser = build_parser()
        # Sans --resume l'exploration part de 1,0 ; avec, elle doit partir plus
        # bas, sinon les centaines de premiers episodes jettent l'acquis.
        assert parser.parse_args(["train"]).epsilon is None
        assert parser.parse_args(["train", "--resume", str(tmp_path)]).resume == str(tmp_path)

    def test_comparer_sans_poids_ne_compare_que_les_bornes(self, capsys):
        from pacman.rl.cli import main

        assert main(["compare", "--ghosts", "1", "--games", "2", "--json"]) == 0
        assert len(json.loads(capsys.readouterr().out)) == 2
