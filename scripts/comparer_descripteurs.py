"""Les deux jeux de descripteurs, a conditions strictement identiques.

La question posee : donner a l'agent la position de CHAQUE fantome et la
repartition de la nourriture le rend-il meilleur qu'avec les douze quantites
agregees ?

Tout est tenu egal : memes graines d'entrainement, memes graines d'evaluation,
memes hyperparametres, meme curriculum. Seul le jeu de descripteurs change.
Sans cette egalite, l'ecart mesure ne voudrait rien dire.

    python scripts/comparer_descripteurs.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pacman.rl.environment import EnvConfig  # noqa: E402
from pacman.rl.evaluation import evaluate  # noqa: E402
from pacman.rl.features import BASE, POSITIONS  # noqa: E402
from pacman.rl.training import Hyper, train  # noqa: E402

RESULTATS = RACINE / "results"
EPISODES = 3_000
PARTIES = 100


def curriculum(jeu) -> dict:
    """Un fantome puis quatre, exactement comme la campagne principale."""
    debut = time.perf_counter()

    agent, rapport_1f = train(
        EPISODES,
        config=EnvConfig(ghosts=1),
        features=jeu,
        seed=0,
        log_every=1_000,
        on_window=lambda e: print(
            f"    1F  episode {e['episode']:>5}  score median {e['score_median']:>6.0f}",
            flush=True,
        ),
    )
    eval_1f = evaluate(agent, games=PARTIES, config=EnvConfig(ghosts=1))
    print(f"  1 fantome  | {eval_1f.line()}", flush=True)

    tiede = Hyper(epsilon=0.3, epsilon_final=0.05)
    agent, rapport_4f = train(
        EPISODES,
        config=EnvConfig(ghosts=4),
        hyper=tiede,
        agent=agent,
        seed=0,
        log_every=1_000,
        on_window=lambda e: print(
            f"    4F  episode {e['episode']:>5}  score median {e['score_median']:>6.0f}",
            flush=True,
        ),
    )
    eval_4f = evaluate(agent, games=PARTIES, config=EnvConfig(ghosts=4))
    print(f"  4 fantomes | {eval_4f.line()}", flush=True)

    agent.save(RESULTATS / f"poids_4fantomes_{jeu.name}.json")
    return {
        "descripteurs": jeu.name,
        "nombre_de_poids": len(jeu.names),
        "secondes": round(time.perf_counter() - debut, 1),
        "un_fantome": eval_1f.as_dict(),
        "quatre_fantomes": eval_4f.as_dict(),
        "poids": dict(agent.weights),
        "fenetres_1f": rapport_1f.windows,
        "fenetres_4f": rapport_4f.windows,
    }


def main() -> int:
    RESULTATS.mkdir(exist_ok=True)
    mesures = {}
    for jeu in (BASE, POSITIONS):
        print(f"\n== Descripteurs '{jeu.name}' ({len(jeu.names)} poids) ==", flush=True)
        mesures[jeu.name] = curriculum(jeu)

    destination = RESULTATS / "descripteurs.json"
    destination.write_text(
        json.dumps({"episodes": EPISODES, "parties": PARTIES, "jeux": mesures},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n== Verdict (4 fantomes, 100 parties, graines jamais vues) ==")
    for nom, mesure in mesures.items():
        quatre = mesure["quatre_fantomes"]
        print(
            f"  {nom:<10} {mesure['nombre_de_poids']:>3} poids  "
            f"mediane {quatre['score_median']:>7.0f}  "
            f"ecart-type {quatre['score_ecart_type']:>7.0f}  "
            f"victoires {quatre['taux_victoire']:>5.0%}  "
            f"({mesure['secondes']:.0f} s d'entrainement)"
        )
    print(f"\nMesures ecrites dans {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
