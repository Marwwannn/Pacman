"""Ligne de commande de l'apprentissage : `pacman-rl`.

Trois sous-commandes, qui suivent l'ordre dans lequel on travaille :
`baselines` pour poser les bornes, `train` pour apprendre, `compare` pour
situer l'agent entre les deux.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .agents import ApproximateQAgent, HeuristicAgent, RandomAgent
from .environment import EnvConfig
from .evaluation import EvalReport, evaluate
from .rewards import RewardConfig
from .training import Hyper, train


def _env_config(args: argparse.Namespace) -> EnvConfig:
    return EnvConfig(
        maze=args.maze,
        level=args.level,
        lives=args.lives,
        ghosts=args.ghosts,
        randomize_start=not args.fixed_start,
    )


def _add_env_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--maze", default="classic", help="nom du labyrinthe")
    parser.add_argument("--level", type=int, default=1, help="niveau de jeu")
    parser.add_argument("--lives", type=int, default=1, help="vies par episode")
    parser.add_argument("--ghosts", type=int, default=4, help="nombre de fantomes (curriculum)")
    parser.add_argument(
        "--fixed-start",
        action="store_true",
        help="depart toujours identique (deconseille : l'agent memorise la partie)",
    )
    parser.add_argument("--json", action="store_true", help="sortie machine")


def _report(reports: list[EvalReport], as_json: bool) -> None:
    if as_json:
        print(json.dumps([item.as_dict() for item in reports], indent=2, ensure_ascii=False))
        return
    for item in reports:
        print(item.line())


def cmd_baselines(args: argparse.Namespace) -> int:
    """Plancher et plafond raisonnable, sur les memes graines que tout le reste."""
    config = _env_config(args)
    reports = [
        evaluate(RandomAgent(seed=1), games=args.games, config=config),
        evaluate(HeuristicAgent(seed=1), games=args.games, config=config),
    ]
    _report(reports, args.json)
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    config = _env_config(args)
    defaults = Hyper()
    hyper = Hyper(
        alpha=args.alpha,
        # Le plancher ne doit jamais depasser la valeur de depart, sinon le
        # taux d'apprentissage monterait au lieu de descendre.
        alpha_final=min(args.alpha, defaults.alpha_final),
        gamma=args.gamma,
        epsilon=args.epsilon,
        epsilon_final=min(args.epsilon, defaults.epsilon_final),
    )

    # Curriculum : on reprend les poids appris a un fantome pour continuer a
    # quatre, plutot que de repartir de zero sur un probleme plus dur.
    resumed = ApproximateQAgent.load(args.resume, seed=args.seed) if args.resume else None

    started = time.perf_counter()
    agent, report = train(
        args.episodes,
        config=config,
        rewards=RewardConfig(),
        hyper=hyper,
        agent=resumed,
        seed=args.seed,
        log_every=args.log_every,
        on_window=None if args.json else _print_window,
    )
    elapsed = time.perf_counter() - started

    agent.save(args.out)
    evaluation = evaluate(agent, games=args.games, config=config)

    if args.json:
        print(
            json.dumps(
                {
                    "entrainement": report.summary(),
                    "fenetres": report.windows,
                    "poids": report.weights,
                    "secondes": round(elapsed, 1),
                    "evaluation": evaluation.as_dict(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"\n{args.episodes} episodes en {elapsed:.1f} s -> poids ecrits dans {args.out}")
    print("\nPoids appris :")
    for name, value in sorted(agent.weights.items(), key=lambda item: -abs(item[1])):
        print(f"  {name:<24} {value:+10.3f}")
    print()
    print(evaluation.line())
    return 0


def _print_window(entry: dict) -> None:
    print(
        f"episode {entry['episode']:>6}  epsilon {entry['epsilon']:.2f}  "
        f"alpha {entry['alpha']:.4f}  score median {entry['score_median']:>7.0f}"
    )


def cmd_compare(args: argparse.Namespace) -> int:
    """Les trois agents sur les memes graines : c'est le tableau du rendu."""
    config = _env_config(args)
    agents = [RandomAgent(seed=1), HeuristicAgent(seed=1)]
    if args.weights:
        agents.append(ApproximateQAgent.load(args.weights, seed=1))

    reports = [evaluate(agent, games=args.games, config=config) for agent in agents]
    _report(reports, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pacman-rl",
        description="Apprentissage par renforcement d'un agent joueur de Pac-Man",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    baselines = subparsers.add_parser("baselines", help="mesurer le plancher et le plafond")
    _add_env_arguments(baselines)
    baselines.add_argument("--games", type=int, default=100)
    baselines.set_defaults(func=cmd_baselines)

    trainer = subparsers.add_parser("train", help="entrainer l'agent Q approxime")
    _add_env_arguments(trainer)
    trainer.add_argument("--episodes", type=int, default=2_000)
    trainer.add_argument("--games", type=int, default=100, help="parties d'evaluation finale")
    trainer.add_argument("--alpha", type=float, default=Hyper().alpha)
    trainer.add_argument("--gamma", type=float, default=Hyper().gamma)
    trainer.add_argument("--epsilon", type=float, default=Hyper().epsilon)
    trainer.add_argument("--seed", type=int, default=0)
    trainer.add_argument("--log-every", type=int, default=100)
    trainer.add_argument("--resume", help="poids de depart (curriculum)")
    trainer.add_argument("--out", default="weights.json")
    trainer.set_defaults(func=cmd_train)

    compare = subparsers.add_parser("compare", help="comparer les agents sur les memes graines")
    _add_env_arguments(compare)
    compare.add_argument("--games", type=int, default=100)
    compare.add_argument("--weights", help="poids d'un agent entraine")
    compare.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - point d'entree
    sys.exit(main())
