"""Recompenses de l'environnement d'apprentissage.

Le reglage de ces valeurs pese plus lourd sur le resultat final que le taux
d'apprentissage et le facteur d'actualisation reunis. Deux choix sont
structurants et ne doivent pas etre defaits sans mesure :

- la mort doit dominer tout le reste, sinon l'agent apprend a se faire manger
  pour abreger une partie devenue couteuse ;
- chaque pas de decision coute, sinon l'agent tourne indefiniment devant une
  super-pastille sans jamais la manger — le detournement de recompense
  classique sur Pac-Man.

Le score brut du jeu n'est deliberement pas repris : la vie supplementaire a
10 000 points y cree une marche que rien dans l'etat ne permet de predire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.game import Event


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Bareme de l'environnement."""

    pellet: float = 10.0
    power_pellet: float = 50.0
    #: Multiplicateur applique aux points de la chaine (200, 400, 800, 1600).
    ghost: float = 1.0
    #: Multiplicateur applique aux points du fruit.
    fruit: float = 1.0
    death: float = -500.0
    #: Cout d'un pas de decision, compte une fois par appel a `step`.
    step: float = -1.0
    level_complete: float = 500.0

    def from_events(self, events: Iterable[Event]) -> float:
        """Recompense portee par les evenements d'un ou plusieurs ticks."""
        total = 0.0
        for event in events:
            if event.type == "pellet":
                total += self.pellet
            elif event.type == "power_pellet":
                total += self.power_pellet
            elif event.type == "ghost_eaten":
                total += self.ghost * event.payload.get("points", 0)
            elif event.type == "fruit_eaten":
                total += self.fruit * event.payload.get("points", 0)
            elif event.type == "pacman_died":
                total += self.death
            elif event.type == "level_complete":
                total += self.level_complete
        return total
