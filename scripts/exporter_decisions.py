"""Enregistre le RAISONNEMENT de l'agent sur une partie, pas seulement ses coups.

Un score ne montre pas une politique. Ce script rejoue une partie avec l'agent
entraine et note, a chaque intersection : ce qu'il voyait, ce que chaque
direction valait a ses yeux, la contribution de chaque descripteur a cette
valeur, et ce qu'il a choisi.

Le resultat est un `docs/decisions.html` autonome — donnees comprises — qui
rend le raisonnement lisible case par case.

    python scripts/exporter_decisions.py
    python scripts/exporter_decisions.py --graine 1000007 --agent heuristique
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pacman.core.entities import GhostMode  # noqa: E402
from pacman.core.geometry import Direction  # noqa: E402
from pacman.rl.agents import ApproximateQAgent, HeuristicAgent  # noqa: E402
from pacman.rl.environment import EnvConfig, PacmanEnv  # noqa: E402
from pacman.rl.evaluation import EVALUATION_SEEDS  # noqa: E402
from pacman.rl.search import SearchAgent  # noqa: E402

GABARIT = RACINE / "docs" / "decisions_gabarit.html"
SORTIE = RACINE / "docs" / "decisions.html"
POIDS = RACINE / "results" / "poids_4fantomes.json"

#: Evenements qui meritent d'etre signales pendant le rejeu. Le reste (chaque
#: pastille, chaque vague) ferait du bruit sans rien apprendre.
MARQUANTS = frozenset(
    {
        "power_pellet",
        "ghost_eaten",
        "fruit_eaten",
        "pacman_died",
        "extra_life",
        "level_complete",
        "frightened",
    }
)


def plan(maze) -> dict:
    """Le decor, envoye une seule fois : murs, portes, cases praticables."""
    return {
        "largeur": maze.width,
        "hauteur": maze.height,
        "murs": [
            [x, y]
            for y in range(maze.height)
            for x in range(maze.width)
            if maze.is_wall(_pos(x, y))
        ],
        "portes": [
            [x, y]
            for y in range(maze.height)
            for x in range(maze.width)
            if maze.is_door(_pos(x, y))
        ],
    }


def _pos(x: int, y: int):
    from pacman.core.geometry import Position

    return Position(x, y)


def etat_des_fantomes(game) -> list[dict]:
    return [
        {
            "nom": ghost.name,
            "x": ghost.position.x,
            "y": ghost.position.y,
            "effraye": ghost.mode is GhostMode.FRIGHTENED,
            "actif": ghost.is_active,
        }
        for ghost in game.ghosts
    ]


def evaluation_des_actions(agent, game, actions: list[Direction], env) -> list[dict]:
    """Ce que vaut chaque direction, et d'ou vient cette valeur.

    Pour l'agent lineaire on peut tout ouvrir : la valeur est une somme de
    produits `poids x descripteur`, donc chaque terme se montre. C'est tout
    l'interet d'avoir refuse le reseau de neurones.

    Un descripteur qui vaut la MEME chose pour toutes les directions n'a beau
    peser tres lourd, il ne departage rien — le biais en est le cas pur, et
    `avancement` (part de pastilles mangees) aussi, puisqu'il decrit l'etat et
    non le coup. Les marquer evite de faire lire un raisonnement dans un terme
    qui ne choisit rien.
    """
    if not isinstance(agent, ApproximateQAgent):
        return [{"direction": action.name.lower(), "valeur": None} for action in actions]

    par_action = {action: agent.values(game, action, env.metrics) for action in actions}
    noms = agent.features.names
    discriminants = {
        nom
        for position, nom in enumerate(noms)
        if len({valeurs[position] for valeurs in par_action.values()}) > 1
    }

    lignes = []
    for action, valeurs in par_action.items():
        contributions = [
            {
                "nom": nom,
                "descripteur": round(valeur, 3),
                "apport": round(agent.weights[nom] * valeur, 1),
                "discrimine": nom in discriminants,
            }
            for nom, valeur in zip(noms, valeurs)
            if valeur != 0.0
        ]
        contributions.sort(key=lambda item: (not item["discrimine"], -abs(item["apport"])))
        lignes.append(
            {
                "direction": action.name.lower(),
                "valeur": round(agent.q_from(valeurs), 1),
                # Ce qui a reellement pese dans le choix : la somme des seuls
                # termes qui varient d'une direction a l'autre.
                "valeur_discriminante": round(
                    sum(item["apport"] for item in contributions if item["discrimine"]), 1
                ),
                "contributions": contributions,
            }
        )
    return lignes


def construire_agent(nom: str):
    if nom == "heuristique":
        return HeuristicAgent(seed=1)
    if nom == "recherche":
        return SearchAgent(depth=3)
    if not POIDS.exists():
        raise SystemExit(f"{POIDS} absent : lancer d'abord scripts/campagne_rl.py")
    return ApproximateQAgent.load(POIDS, seed=1)


def rejouer(agent, graine: int, fantomes: int) -> dict:
    #: Une image par tick, pour rejouer le MOUVEMENT et pas seulement les
    #: choix. L'environnement ne rend la main qu'aux intersections : sans cet
    #: observateur, tout ce qui se passe dans les couloirs serait invisible.
    images: list[dict] = []

    def filmer(game, evenements) -> None:
        images.append(
            {
                "p": [game.pacman.position.x, game.pacman.position.y],
                "d": game.pacman.direction.name.lower(),
                "f": [
                    [g.position.x, g.position.y, 1 if g.mode is GhostMode.FRIGHTENED else 0]
                    for g in game.ghosts
                    if g.is_active
                ],
                "s": game.score,
                "m": [e.type for e in evenements if e.type in MARQUANTS],
                "n": [
                    [e.payload["x"], e.payload["y"]]
                    for e in evenements
                    if e.type in ("pellet", "power_pellet")
                ],
            }
        )

    env = PacmanEnv(EnvConfig(ghosts=fantomes, lives=1), on_tick=filmer)
    game = env.reset(graine)

    # Les pastilles ne sont envoyees qu'une fois : le film porte deja celles
    # qui sont mangees a chaque tick, donc les recopier a chaque decision
    # quadruplerait le poids de la page pour la meme information.
    pastilles_initiales = sorted(game.pellets | game.power_pellets, key=lambda p: (p.y, p.x))
    super_initiales = sorted(game.power_pellets, key=lambda p: (p.y, p.x))
    decisions = []

    while not env.finished and len(decisions) < 400:
        actions = env.legal_actions()
        if not actions:
            break
        choix = agent.act(game, actions, env)

        decisions.append(
            {
                "numero": len(decisions) + 1,
                "tick": env.ticks,
                # Index de l'image ou cette decision est prise : c'est ce qui
                # raccroche le film au raisonnement.
                "image": len(images),
                "score": game.score,
                "x": game.pacman.position.x,
                "y": game.pacman.position.y,
                "venant_de": game.pacman.direction.name.lower(),
                "fantomes": etat_des_fantomes(game),
                "actions": evaluation_des_actions(agent, game, actions, env),
                "choix": choix.name.lower(),
            }
        )

        resultat = env.step(choix)

    return {
        "agent": getattr(agent, "name", type(agent).__name__),
        "graine": graine,
        "fantomes": fantomes,
        "plan": plan(game.maze),
        "pastilles_initiales": [[p.x, p.y] for p in pastilles_initiales],
        "super_pastilles": [[p.x, p.y] for p in super_initiales],
        "images": images,
        "decisions": decisions,
        "final": {
            "score": game.score,
            "ticks": env.ticks,
            "gagne": bool(resultat.info.get("won")) if decisions else False,
            "mort": env.deaths > 0,
            "pastilles_restantes": game.remaining_pellets,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graine", type=int, default=EVALUATION_SEEDS)
    parser.add_argument("--fantomes", type=int, default=4)
    parser.add_argument(
        "--agent",
        default="appris",
        choices=("appris", "heuristique", "recherche"),
        help="seul « appris » peut montrer le detail de son calcul",
    )
    args = parser.parse_args(argv)

    if args.graine < EVALUATION_SEEDS:
        print(
            f"graine {args.graine} : montrer une partie d'ENTRAINEMENT donnerait "
            f"une fausse idee de la politique. Prendre >= {EVALUATION_SEEDS}."
        )
        return 1

    partie = rejouer(construire_agent(args.agent), args.graine, args.fantomes)
    donnees = json.dumps(partie, ensure_ascii=False, separators=(",", ":"))

    gabarit = GABARIT.read_text(encoding="utf-8")
    SORTIE.write_text(gabarit.replace("/*DONNEES*/null", donnees), encoding="utf-8")

    final = partie["final"]
    print(
        f"{len(partie['decisions'])} decisions, score {final['score']}, "
        f"{'gagne' if final['gagne'] else 'mort' if final['mort'] else 'inacheve'}"
        f" -> {SORTIE.relative_to(RACINE)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
