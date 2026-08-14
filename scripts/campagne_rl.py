"""Campagne de mesure reproductible : baselines, curriculum, comparatif.

C'est la commande qui produit les chiffres du rendu. Elle enchaine exactement
ce que le README decrit a la main, et ecrit tout dans `results/` : les poids
appris (rejouables) et les mesures (citables).

    python scripts/campagne_rl.py

Duree : quelques minutes. Rien n'est aleatoire d'un run a l'autre — les
graines d'entrainement comme d'evaluation sont fixees.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pacman.rl.agents import ApproximateQAgent, HeuristicAgent, RandomAgent  # noqa: E402
from pacman.rl.environment import EnvConfig  # noqa: E402
from pacman.rl.evaluation import evaluate  # noqa: E402
from pacman.rl.search import SearchAgent  # noqa: E402
from pacman.rl.training import Hyper, train  # noqa: E402

RESULTATS = RACINE / "results"
PARTIES = 100
EPISODES = 3_000
#: Profondeurs balayees pour la recherche en ligne. Elle n'apprend rien : son
#: seul reglage est « jusqu'ou je regarde », et son cout suit.
PROFONDEURS = (1, 2, 3)
#: Profondeur du comparatif final. Choisie sur la mediane et l'ecart-type, pas
#: sur le taux de victoire seul.
PROFONDEUR_RETENUE = 2


def mesurer(agent, config: EnvConfig) -> dict:
    rapport = evaluate(agent, games=PARTIES, config=config)
    print(f"  {rapport.line()}", flush=True)
    return rapport.as_dict()


def entrainer(ghosts: int, reprise: str | None, sortie: Path) -> dict:
    config = EnvConfig(ghosts=ghosts)
    defauts = Hyper()
    # Reprendre des poids appris puis explorer a 100 % rejetterait l'acquis :
    # un curriculum demarre tiede (meme regle que le CLI).
    epsilon = 0.3 if reprise else defauts.epsilon
    hyper = Hyper(epsilon=epsilon, epsilon_final=min(epsilon, defauts.epsilon_final))
    depart = ApproximateQAgent.load(reprise, seed=0) if reprise else None

    debut = time.perf_counter()
    agent, rapport = train(
        EPISODES,
        config=config,
        hyper=hyper,
        agent=depart,
        seed=0,
        log_every=500,
        on_window=lambda e: print(
            f"    episode {e['episode']:>5}  epsilon {e['epsilon']:.2f}"
            f"  score median {e['score_median']:>6.0f}",
            flush=True,
        ),
    )
    secondes = time.perf_counter() - debut
    agent.save(str(sortie))
    print(f"  {EPISODES} episodes en {secondes:.0f} s -> {sortie.name}", flush=True)

    return {
        "entrainement": rapport.summary(),
        "fenetres": rapport.windows,
        "poids": rapport.weights,
        "secondes": round(secondes, 1),
        "evaluation": mesurer(agent, config),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sans-entrainement",
        action="store_true",
        help="reutilise les poids de results/ et ne refait que les mesures",
    )
    args = parser.parse_args(argv)

    RESULTATS.mkdir(exist_ok=True)
    destination = RESULTATS / "campagne.json"
    poids_1f = RESULTATS / "poids_1fantome.json"
    poids_4f = RESULTATS / "poids_4fantomes.json"

    if args.sans_entrainement:
        # Remesurer sans reapprendre : c'est ce qui rend l'ajout d'un agent
        # bon marche, et c'est aussi le controle que les poids ecrits sur
        # disque rendent bien le chiffre publie.
        campagne = json.loads(destination.read_text(encoding="utf-8"))
    else:
        campagne = {"episodes": EPISODES, "parties_evaluation": PARTIES, "etapes": {}}

        for ghosts in (1, 4):
            print(f"\n== Baselines a {ghosts} fantome(s) ==", flush=True)
            config = EnvConfig(ghosts=ghosts)
            campagne["etapes"][f"baselines_{ghosts}f"] = [
                mesurer(RandomAgent(seed=1), config),
                mesurer(HeuristicAgent(seed=1), config),
            ]

        print("\n== Apprentissage a 1 fantome ==", flush=True)
        campagne["etapes"]["train_1f"] = entrainer(1, None, poids_1f)

        print("\n== Curriculum : reprise a 4 fantomes ==", flush=True)
        campagne["etapes"]["train_4f_curriculum"] = entrainer(4, str(poids_1f), poids_4f)

        print("\n== Temoin : 4 fantomes sans curriculum ==", flush=True)
        poids_direct = RESULTATS / "poids_4fantomes_sans_curriculum.json"
        campagne["etapes"]["train_4f_direct"] = entrainer(4, None, poids_direct)

    config = EnvConfig(ghosts=4)

    print("\n== Profondeur de recherche (4 fantomes) ==", flush=True)
    campagne["etapes"]["profondeurs_recherche"] = [
        mesurer(SearchAgent(depth=profondeur), config) | {"profondeur": profondeur}
        for profondeur in PROFONDEURS
    ]

    print("\n== Comparatif final a 4 fantomes ==", flush=True)
    campagne["etapes"]["comparatif_4f"] = [
        mesurer(RandomAgent(seed=1), config),
        mesurer(HeuristicAgent(seed=1), config),
        mesurer(ApproximateQAgent.load(str(poids_4f), seed=1), config),
        mesurer(SearchAgent(depth=PROFONDEUR_RETENUE), config),
    ]

    destination.write_text(json.dumps(campagne, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nMesures ecrites dans {destination}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
