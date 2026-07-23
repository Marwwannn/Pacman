"""Reglages du jeu : cadence, points, vitesses et progression par niveau.

Tout ce qui s'equilibre est ici, hors du moteur : on peut durcir le jeu sans
toucher a une ligne de logique.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Cadence de simulation. Toutes les durees ci-dessous sont en ticks.
#:
#: Le deplacement etant discret (une case au plus par tick, cf. `core.entities`),
#: la cadence fixe aussi la vitesse du jeu : a `speed = 0.8`, Pac-Man parcourt
#: `0.8 * TICKS_PER_SECOND` cases par seconde. La borne de 12 place le niveau 1
#: a 9,6 cases/s, proche des ~9 cases/s de la borne d'arcade de 1980. Toutes les
#: durees restent exprimees en secondes via `seconds()` : changer la cadence
#: change la vitesse, jamais l'equilibrage temporel.
TICKS_PER_SECOND = 12


def seconds(value: float) -> int:
    return round(value * TICKS_PER_SECOND)


# --------------------------------------------------------------------- points

POINTS_PELLET = 10
POINTS_POWER_PELLET = 50
#: Points par fantome mange pendant une meme super-pastille : 200, 400, 800, 1600.
POINTS_GHOST_CHAIN = (200, 400, 800, 1600)
#: Une vie supplementaire au franchissement de ce score.
EXTRA_LIFE_SCORE = 10_000

STARTING_LIVES = 3

# --------------------------------------------------------------------- delais

#: Compte a rebours avant le depart d'une vie.
READY_DURATION = seconds(2)
#: Pause apres la mort de Pac-Man, avant de replacer tout le monde.
DEATH_DURATION = seconds(1.5)
#: Pause a la fin d'un niveau.
LEVEL_END_DURATION = seconds(2)
#: Duree d'affichage d'un fruit.
FRUIT_DURATION = seconds(9.5)


# --------------------------------------------------------------------- fruits

#: Nombre de pastilles mangees declenchant l'apparition d'un fruit.
FRUIT_DOT_TRIGGERS = (70, 170)

#: Fruit et points par niveau. Au-dela du dernier, le fruit le plus cher reste.
FRUITS = (
    ("cerise", 100),
    ("fraise", 300),
    ("orange", 500),
    ("orange", 500),
    ("pomme", 700),
    ("pomme", 700),
    ("melon", 1000),
    ("melon", 1000),
    ("galboss", 2000),
    ("galboss", 2000),
    ("cloche", 3000),
    ("cloche", 3000),
    ("cle", 5000),
)


def fruit_for(level: int) -> tuple[str, int]:
    """Fruit du niveau `level` : nom et valeur en points."""
    return FRUITS[min(max(1, level), len(FRUITS)) - 1]


@dataclass(frozen=True, slots=True)
class LevelRules:
    """Parametres dependant du niveau."""

    pacman_speed: float
    ghost_speed: float
    frightened_speed: float
    frightened_duration: int
    #: Alternance scatter / chase, en ticks. Le dernier element vaut « pour toujours ».
    mode_waves: tuple[int, ...]
    #: Nombre de pastilles avant la sortie de la maison, par fantome.
    dot_limits: dict[str, int]


def _waves(*durations: float) -> tuple[int, ...]:
    return tuple(seconds(d) for d in durations)


#: Vagues scatter/chase du jeu d'origine : scatter, chase, scatter, chase, ...
WAVES_EARLY = _waves(7, 20, 7, 20, 5, 20, 5)
WAVES_MID = _waves(7, 20, 7, 20, 5, 1033 / 60, 1 / 60)
WAVES_LATE = _waves(5, 20, 5, 20, 5, 1037 / 60, 1 / 60)

DOT_LIMITS_START = {"blinky": 0, "pinky": 0, "inky": 30, "clyde": 60}


def rules_for(level: int) -> LevelRules:
    """Reglages du niveau `level` (1 = premier niveau).

    La difficulte monte comme dans l'original : les fantomes accelerent, la
    duree de vulnerabilite fond, et les fantomes sortent de plus en plus tot.
    """
    level = max(1, level)

    if level == 1:
        waves = WAVES_EARLY
    elif level < 5:
        waves = WAVES_MID
    else:
        waves = WAVES_LATE

    # Vitesses : progression douce, plafonnee pour rester jouable.
    pacman_speed = min(0.9, 0.8 + 0.01 * (level - 1))
    ghost_speed = min(0.95, 0.75 + 0.02 * (level - 1))
    frightened_speed = min(0.6, 0.5 + 0.01 * (level - 1))

    # La vulnerabilite passe de 6 s a 0 : au-dela du niveau 19, les super-pastilles
    # ne font plus qu'inverser le sens des fantomes.
    frightened_duration = seconds(max(0.0, 6.0 - 0.3 * (level - 1)))

    dot_limits = {
        name: max(0, limit - 10 * (level - 1)) for name, limit in DOT_LIMITS_START.items()
    }

    return LevelRules(
        pacman_speed=pacman_speed,
        ghost_speed=ghost_speed,
        frightened_speed=frightened_speed,
        frightened_duration=frightened_duration,
        mode_waves=waves,
        dot_limits=dot_limits,
    )
