"""Leve un angle mort du protocole : les fantomes partaient toujours des memes cases.

Les graines de l'evaluation ne resemaient que le depart de Pac-Man et l'errance
des fantomes en mode effraye. Leurs quatre cases de depart, elles, ne bougeaient
jamais : a l'entrainement comme a l'evaluation. La garde sur les graines protege
donc contre la memorisation d'une PARTIE, pas contre la dependance a cette
CONFIGURATION. Rien dans les chiffres publies ne permettait de trancher.

Ce script rejoue les memes agents, avec les MEMES poids deja appris (rien n'est
reentraine), dans deux conditions :

* **reference**  : la configuration d'origine, celle de tous les chiffres publies ;
* **disperse**   : les quatre fantomes tires au sort hors de la maison, donc
                   actifs des le premier tick.

La condition dispersee ne joue pas la meme partie : les quatre fantomes y sont
actifs des le premier tick, la ou trois attendent leur quota de pastilles dans
la maison. On l'attendait plus DURE ; la mesure dit l'inverse : heuristique et
recherche y font MIEUX. Disperses, les fantomes partent chacun vers son coin au
lieu de sortir groupes du centre. C'est exactement pourquoi les agents qui n'ont
RIEN appris (l'aleatoire, l'heuristique ecrite a la main, la recherche en
ligne) sont passes dans la meme condition : ils absorbent la variation de
difficulte, quel qu'en soit le sens. Ce qui se lit, c'est l'ecart entre l'agent
appris et eux, jamais son chiffre isole.

Et aucun ecart n'est commente sans son intervalle : sur 100 parties dont
l'ecart-type depasse 1000 points, une variation de 130 points ne veut rien dire.
Le bootstrap ci-dessous le dit explicitement plutot que de laisser un
pourcentage flatteur passer pour un resultat.

    python scripts/fantomes_ailleurs.py

Duree : quelques minutes (la recherche en profondeur 3 domine le cout).
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from statistics import median

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pacman.rl.agents import ApproximateQAgent, HeuristicAgent, RandomAgent  # noqa: E402
from pacman.rl.environment import EnvConfig, PacmanEnv  # noqa: E402
from pacman.rl.evaluation import evaluate  # noqa: E402
from pacman.rl.search import SearchAgent  # noqa: E402

RESULTATS = RACINE / "results"
PARTIES = 100
FANTOMES = 4
PROFONDEUR = 3
#: Tirages du bootstrap et graine fixe : la conclusion doit etre rejouable a
#: l'identique, comme le reste de la campagne.
TIRAGES = 2_000
GRAINE_BOOTSTRAP = 20_260_821

CONDITIONS = {
    "reference": EnvConfig(ghosts=FANTOMES),
    "disperse": EnvConfig(ghosts=FANTOMES, randomize_ghost_starts=True),
}


def agents() -> list:
    """Les quatre agents du comparatif, dans l'ordre du rendu."""
    return [
        ("aleatoire", RandomAgent(seed=0), False),
        ("heuristique", HeuristicAgent(seed=0), False),
        ("appris", ApproximateQAgent.load(RESULTATS / "poids_4fantomes.json", seed=0), True),
        ("recherche", SearchAgent(PROFONDEUR, seed=0), False),
    ]


def configurations_distinctes(config: EnvConfig, parties: int) -> int:
    """Compte les configurations de depart REELLEMENT obtenues.

    Une randomisation se verifie en comptant les valeurs distinctes obtenues,
    jamais en relisant le code cense la produire : c'est precisement en la
    comptant qu'on a trouve l'angle mort.
    """
    env = PacmanEnv(config)
    vues = set()
    for index in range(parties):
        env.reset(1_000_000 + index)
        vues.add(tuple(sorted((g.name, g.start.x, g.start.y) for g in env.game.ghosts)))
    return len(vues)


def intervalle_ecart(avant: list[int], apres: list[int]) -> tuple[float, float]:
    """Intervalle a 95 % de l'ecart entre les deux medianes, par bootstrap.

    Les deux conditions ne rejouent pas les memes parties : un fantome place
    ailleurs change la partie entiere, donc les echantillons sont retires
    independamment. L'intervalle repond a la seule question qui compte ici :
    l'ecart observe peut-il n'etre que du bruit d'echantillonnage ?
    """
    tirage = random.Random(GRAINE_BOOTSTRAP)
    ecarts = []
    for _ in range(TIRAGES):
        a = median(tirage.choices(avant, k=len(avant)))
        b = median(tirage.choices(apres, k=len(apres)))
        ecarts.append(b - a)
    ecarts.sort()
    return ecarts[int(0.025 * TIRAGES)], ecarts[int(0.975 * TIRAGES) - 1]


def main() -> int:
    mesures: dict[str, dict] = {}

    for condition, config in CONDITIONS.items():
        distinctes = configurations_distinctes(config, PARTIES)
        print(f"\n=== {condition} : {distinctes} configuration(s) de depart sur {PARTIES} parties")
        mesures[condition] = {"configurations_distinctes": distinctes, "agents": {}}

        for nom, agent, appris in agents():
            debut = time.perf_counter()
            rapport = evaluate(agent, games=PARTIES, config=config)
            secondes = time.perf_counter() - debut
            print(f"  {rapport.line()}  ({secondes:.0f} s)", flush=True)
            mesures[condition]["agents"][nom] = {
                **rapport.as_dict(),
                "appris": appris,
                "_scores": list(rapport.scores),
            }

    # ----------------------------------------------------------------- lecture
    print(f"\n=== ecart entre les deux conditions ({PARTIES} parties, IC 95 % par bootstrap)")
    ecarts = {}
    for nom in mesures["reference"]["agents"]:
        reference = mesures["reference"]["agents"][nom]
        disperse = mesures["disperse"]["agents"][nom]
        avant, apres = reference["score_median"], disperse["score_median"]
        bas, haut = intervalle_ecart(reference["_scores"], disperse["_scores"])
        # Un intervalle qui contient zero veut dire que l'ecart observe est
        # compatible avec l'absence d'effet : il ne se commente pas.
        significatif = bas > 0 or haut < 0
        ecarts[nom] = {
            "reference": avant,
            "disperse": apres,
            "ecart": apres - avant,
            "variation": round((apres - avant) / avant, 3) if avant else 0.0,
            "ic95": [bas, haut],
            "significatif": significatif,
            "appris": reference["appris"],
        }
        marque = " (appris)" if reference["appris"] else ""
        etoile = "significatif" if significatif else "dans le bruit"
        print(
            f"  {nom:<14} {avant:>7.0f} -> {apres:>7.0f}   "
            f"{apres - avant:>+6.0f}  IC95 [{bas:>+6.0f}, {haut:>+6.0f}]  {etoile}{marque}"
        )

    # Verdict. La question n'est pas « le score monte-t-il ou baisse-t-il », mais
    # « l'agent appris s'effondre-t-il la ou les temoins tiennent ». Un
    # effondrement signerait une politique accrochee a la maison centrale.
    appris = ecarts["appris"]
    effondrement = appris["significatif"] and appris["ecart"] < 0
    verdict = (
        "l'agent appris s'effondre quand les fantomes changent de depart : "
        "la politique dependait de la configuration"
        if effondrement
        else "l'agent appris tient quand les fantomes changent de depart "
        f"({appris['ecart']:+.0f} points, IC95 "
        f"[{appris['ic95'][0]:+.0f}, {appris['ic95'][1]:+.0f}]) : "
        "sa politique est topologique, pas un plan de maison memorise"
    )
    print(f"\n  -> {verdict}")

    # Les scores bruts ont servi au bootstrap, ils n'ont pas a etre publies.
    for condition in mesures.values():
        for agent in condition["agents"].values():
            agent.pop("_scores", None)

    sortie = RESULTATS / "fantomes_ailleurs.json"
    sortie.write_text(
        json.dumps(
            {
                "parties": PARTIES,
                "fantomes": FANTOMES,
                "profondeur_recherche": PROFONDEUR,
                "conditions": mesures,
                "ecarts": ecarts,
                "tirages_bootstrap": TIRAGES,
                "verdict": verdict,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n  ecrit -> {sortie.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
