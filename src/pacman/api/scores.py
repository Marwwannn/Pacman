"""Meilleurs scores.

Seule donnee du back-end qui merite de survivre au processus. La persistance
est un simple fichier JSON : un serveur de jeu n'a pas besoin d'une base pour
garder dix lignes, et cela laisse le projet installable sans dependance
supplementaire.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

#: Nombre d'entrees conservees.
TOP_SIZE = 10
#: Les noms viennent du client : on les borne et on les nettoie avant stockage.
NAME_PATTERN = re.compile(r"[^\w \-]", re.UNICODE)
MAX_NAME_LENGTH = 12


class ScoreEntry(BaseModel):
    """Une ligne du tableau."""

    name: str
    score: int = Field(ge=0)
    level: int = Field(ge=1)


class ScoreSubmission(BaseModel):
    """Score propose par un client."""

    name: str = Field(default="AAA", max_length=64)
    score: int = Field(ge=0, le=10_000_000)
    level: int = Field(default=1, ge=1, le=256)

    def clean_name(self) -> str:
        """Nettoie le nom : il finit affiche chez les autres joueurs."""
        name = NAME_PATTERN.sub("", self.name).strip()
        return (name[:MAX_NAME_LENGTH] or "ANONYME").upper()


class ScoreBoard:
    """Classement des meilleurs scores, trie du plus haut au plus bas."""

    def __init__(self, path: Path | None = None, *, size: int = TOP_SIZE) -> None:
        self.path = path
        self.size = size
        self._entries: list[ScoreEntry] = []
        if path is not None:
            self.load()

    def __len__(self) -> int:
        return len(self._entries)

    def top(self) -> list[ScoreEntry]:
        return list(self._entries)

    def qualifies(self, score: int) -> bool:
        """Ce score entrerait-il au classement ?"""
        if score <= 0:
            return False
        return len(self._entries) < self.size or score > self._entries[-1].score

    def submit(self, submission: ScoreSubmission) -> tuple[ScoreEntry, int | None]:
        """Enregistre un score. Renvoie l'entree et son rang, ou None si non classe."""
        entry = ScoreEntry(
            name=submission.clean_name(), score=submission.score, level=submission.level
        )
        if not self.qualifies(entry.score):
            return entry, None

        self._entries.append(entry)
        # A score egal, le premier arrive reste devant : le tri est stable.
        self._entries.sort(key=lambda e: e.score, reverse=True)
        del self._entries[self.size :]
        self.save()

        rang = self._entries.index(entry) + 1 if entry in self._entries else None
        return entry, rang

    # ------------------------------------------------------------------ persistance

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            brut = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = [ScoreEntry(**item) for item in brut][: self.size]
        except (OSError, ValueError, TypeError):
            # Fichier corrompu : on repart d'un classement vide plutot que
            # d'empecher le serveur de demarrer pour dix lignes de scores.
            self._entries = []

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([e.model_dump() for e in self._entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
