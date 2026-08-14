"""Description d'un couple (etat, action) par une poignee de nombres.

L'etat brut du jeu est hors de portee d'une table : rien que la configuration
des pastilles vaut 2^244 possibilites. On decrit donc l'etat par quelques
quantites qui generalisent d'une partie a l'autre, et on apprend une valeur
lineaire sur ces quantites.

Toutes les features sont bornees dans [0, 1]. Ce n'est pas cosmetique : avec
des amplitudes heterogenes, un meme taux d'apprentissage ferait diverger un
poids pendant qu'un autre bouge a peine.

Les distances sont des distances reelles dans le labyrinthe, jamais a vol
d'oiseau : deux cases separees par un mur epais sont proches en ligne droite
et tres loin dans les faits.

**Deux jeux de descripteurs** cohabitent, et se comparent (voir `FEATURE_SETS`) :

- `base` — douze quantites agregees : le chasseur le PLUS proche, la pastille
  la PLUS proche. Compact, mais l'agent ne distingue pas deux fantomes a huit
  cases d'un seul.
- `positions` — ajoute la position de CHAQUE fantome et la repartition de la
  nourriture. Exprimees dans le repere de Pac-Man (distance + « cette action
  m'en rapproche-t-elle »), jamais en coordonnees absolues : un poids sur `x`
  signifierait « prefere la droite du plan », ce qui ne generalise a rien.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Callable

from ..core.entities import GhostMode
from ..core.game import Game
from ..core.geometry import Direction
from .metrics import MazeMetrics

#: Ordre des features. Sert aussi de nom des poids appris, ce qui rend un
#: modele entraine lisible : on voit ce que l'agent a retenu.
FEATURE_NAMES: tuple[str, ...] = (
    "biais",
    "mange_pastille",
    "mange_super_pastille",
    "mange_fruit",
    "proximite_pastille",
    "proximite_chasseur",
    "chasseurs_proches",
    "proximite_proie",
    "proximite_super_pastille",
    "issues",
    "demi_tour",
    "avancement",
)

#: Rayon en deca duquel un fantome est considere comme une menace immediate.
DANGER_RADIUS = 3


def extract(game: Game, action: Direction, metrics: MazeMetrics) -> tuple[float, ...]:
    """Vecteur de features du couple (etat courant, `action`)."""
    maze = game.maze
    tile = maze.step(game.pacman.position, action)

    hunters = []
    prey = []
    for ghost in game.ghosts:
        if not ghost.is_active:
            continue
        if ghost.mode is GhostMode.FRIGHTENED:
            prey.append(ghost.position)
        else:
            hunters.append(ghost.position)

    hunter_distances = [metrics.distance(tile, pos) for pos in hunters]
    nearest_hunter = min(hunter_distances, default=inf)
    close_hunters = sum(1 for value in hunter_distances if value <= DANGER_RADIUS)
    nearest_prey = min((metrics.distance(tile, pos) for pos in prey), default=inf)

    total_pellets = len(maze.pellets) + len(maze.power_pellets)
    eaten = total_pellets - game.remaining_pellets

    return (
        1.0,
        1.0 if tile in game.pellets else 0.0,
        1.0 if tile in game.power_pellets else 0.0,
        1.0 if game.fruit is not None and tile == game.fruit else 0.0,
        metrics.proximity(metrics.nearest(tile, game.pellets)),
        metrics.proximity(nearest_hunter),
        min(1.0, close_hunters / max(1, len(game.ghosts))),
        metrics.proximity(nearest_prey),
        metrics.proximity(metrics.nearest(tile, game.power_pellets)),
        min(1.0, len(metrics.options(tile, action)) / 3.0),
        1.0 if action is game.pacman.direction.opposite else 0.0,
        eaten / total_pellets if total_pellets else 1.0,
    )


def named(values: tuple[float, ...]) -> dict[str, float]:
    """Associe les features a leur nom. Pour l'inspection et les tests."""
    return dict(zip(FEATURE_NAMES, values, strict=True))


# ===================================================================== positions

#: Nombre de fantomes decrits un par un. Les emplacements sans fantome valent
#: zero, ce qui permet au meme vecteur de servir a un fantome comme a quatre —
#: c'est ce qui rend le curriculum possible sans changer de modele.
GHOST_SLOTS = 4

#: Rayon du comptage local de nourriture, en cases.
FOOD_RADIUS = 4

#: Au-dela de ce nombre de pastilles dans le rayon, la case est « dense ».
FOOD_DENSE = 8

POSITION_FEATURE_NAMES: tuple[str, ...] = (
    FEATURE_NAMES
    + tuple(
        f"fantome{index}_{aspect}"
        for index in range(GHOST_SLOTS)
        for aspect in ("proximite", "approche", "effraye")
    )
    + ("nourriture_devant", "nourriture_amas")
)


def extract_with_positions(
    game: Game,
    action: Direction,
    metrics: MazeMetrics,
) -> tuple[float, ...]:
    """Les douze features de base, plus la position des fantomes et de la nourriture.

    Chaque fantome est decrit par trois nombres : a quelle distance il est, si
    l'action m'en rapproche, et s'il est comestible. Les fantomes sont ranges
    du plus proche au plus lointain — sans cet ordre, echanger deux fantomes
    identiques changerait le vecteur, et l'agent devrait apprendre quatre fois
    la meme chose.
    """
    maze = game.maze
    ici = game.pacman.position
    tile = maze.step(ici, action)

    depuis_case = metrics.distances.get(tile, {})
    depuis_ici = metrics.distances.get(ici, {})

    actifs = [ghost for ghost in game.ghosts if ghost.is_active]
    actifs.sort(key=lambda ghost: depuis_case.get(ghost.position, inf))

    fantomes: list[float] = []
    for index in range(GHOST_SLOTS):
        if index >= len(actifs):
            fantomes += [0.0, 0.0, 0.0]  # emplacement vide : ne pese rien
            continue
        ghost = actifs[index]
        vers_case = depuis_case.get(ghost.position, inf)
        vers_ici = depuis_ici.get(ghost.position, inf)
        fantomes += [
            metrics.proximity(vers_case),
            1.0 if vers_case < vers_ici else 0.0,
            1.0 if ghost.mode is GhostMode.FRIGHTENED else 0.0,
        ]

    # Une seule passe sur les pastilles pour les deux mesures : la direction de
    # la masse de nourriture, et sa densite autour de la case visee.
    devant = 0
    amas = 0
    pastilles = game.pellets
    for pastille in pastilles:
        vers_case = depuis_case.get(pastille, inf)
        if vers_case < depuis_ici.get(pastille, inf):
            devant += 1
        if vers_case <= FOOD_RADIUS:
            amas += 1

    total = len(pastilles)
    return extract(game, action, metrics) + tuple(fantomes) + (
        devant / total if total else 0.0,
        min(1.0, amas / FOOD_DENSE),
    )


# ================================================================== jeux nommes


@dataclass(frozen=True, slots=True)
class FeatureSet:
    """Un jeu de descripteurs : son nom, ses noms de poids, son extracteur.

    Le nom voyage avec les poids sauvegardes : recharger douze poids dans un
    modele qui en attend vingt-six doit echouer bruyamment, jamais donner un
    agent silencieusement amnesique.
    """

    name: str
    names: tuple[str, ...]
    extractor: Callable[[Game, Direction, MazeMetrics], tuple[float, ...]]

    def extract(self, game: Game, action: Direction, metrics: MazeMetrics) -> tuple[float, ...]:
        return self.extractor(game, action, metrics)

    def named(self, values: tuple[float, ...]) -> dict[str, float]:
        return dict(zip(self.names, values, strict=True))


BASE = FeatureSet("base", FEATURE_NAMES, extract)
POSITIONS = FeatureSet("positions", POSITION_FEATURE_NAMES, extract_with_positions)

FEATURE_SETS: dict[str, FeatureSet] = {jeu.name: jeu for jeu in (BASE, POSITIONS)}


def feature_set(name: str | None) -> FeatureSet:
    """Jeu de descripteurs designe par son nom. `base` par defaut."""
    if not name:
        return BASE
    try:
        return FEATURE_SETS[name]
    except KeyError:
        connus = ", ".join(sorted(FEATURE_SETS))
        raise ValueError(f"jeu de descripteurs inconnu : {name!r} (connus : {connus})") from None
