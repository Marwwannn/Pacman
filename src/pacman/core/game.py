"""Boucle de jeu : etat d'une partie et avancement tick par tick.

`Game` est purement synchrone et deterministe : un meme etat plus une meme
suite d'entrees donne toujours le meme resultat. Aucune horloge, aucun aleatoire,
aucune dependance reseau : c'est ce qui rend le moteur testable et rejouable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum

from ..ai.ghosts import create_ghosts
from . import rules
from .entities import Ghost, GhostMode, Pacman
from .geometry import Direction, Position
from .maze import Maze


class GameState(Enum):
    """Etat global de la partie."""

    READY = "ready"  # compte a rebours avant le depart
    PLAYING = "playing"
    DYING = "dying"  # Pac-Man vient d'etre attrape
    LEVEL_COMPLETE = "level_complete"
    GAME_OVER = "game_over"
    PAUSED = "paused"


@dataclass(slots=True)
class Event:
    """Fait notable survenu pendant un tick, a destination du client."""

    type: str
    payload: dict = field(default_factory=dict)


class Game:
    """Une partie de Pac-Man.

    Implemente `GhostContext` : c'est la vue restreinte que les fantomes ont
    de la partie.
    """

    def __init__(
        self,
        maze: Maze | None = None,
        *,
        level: int = 1,
        lives: int = rules.STARTING_LIVES,
        overflow_bug: bool = True,
    ) -> None:
        self.maze = maze or Maze.load()
        self.level = level
        self.lives = lives
        self.score = 0
        self.overflow_bug = overflow_bug

        self.pacman = Pacman(self.maze.pacman_start)
        self.ghosts: list[Ghost] = create_ghosts(self.maze, overflow_bug=overflow_bug)
        self._by_name = {ghost.name: ghost for ghost in self.ghosts}

        self.pellets: set[Position] = set(self.maze.pellets)
        self.power_pellets: set[Position] = set(self.maze.power_pellets)

        self.state = GameState.READY
        self.tick_count = 0
        self.events: list[Event] = []

        self._state_timer = rules.READY_DURATION
        self._frightened_timer = 0
        self._ghost_chain = 0
        self._wave_index = 0
        self._wave_timer = 0
        self._dots_eaten = 0
        self._extra_life_at = rules.EXTRA_LIFE_SCORE
        self._paused_from = GameState.PLAYING

        #: Fruit present sur le plateau, s'il y en a un.
        self.fruit: Position | None = None
        self.fruit_name: str = ""
        self._fruit_timer = 0
        self._fruits_spawned = 0

        self._apply_level_rules()
        self._place_entities()

    # ================================================================ GhostContext

    @property
    def pacman_position(self) -> Position:
        return self.pacman.position

    @property
    def pacman_direction(self) -> Direction:
        return self.pacman.direction

    @property
    def blinky_position(self) -> Position:
        blinky = self._by_name.get("blinky")
        return blinky.position if blinky else self.pacman.position

    # ================================================================ etat derive

    @property
    def rules(self) -> rules.LevelRules:
        return self._rules

    @property
    def remaining_pellets(self) -> int:
        return len(self.pellets) + len(self.power_pellets)

    @property
    def frightened(self) -> bool:
        return self._frightened_timer > 0

    @property
    def is_over(self) -> bool:
        return self.state is GameState.GAME_OVER

    def ghost(self, name: str) -> Ghost | None:
        return self._by_name.get(name)

    def limit_ghosts(self, count: int) -> None:
        """Ne garde que les `count` premiers fantomes, dans l'ordre de sortie.

        Sert au curriculum d'apprentissage : commencer a un fantome permet de
        distinguer « l'agent n'apprend pas » de « le probleme est trop dur ».
        Blinky est toujours conserve en premier, c'est lui que les autres
        prennent comme reference.
        """
        if count >= len(self.ghosts):
            return
        self.ghosts = self.ghosts[: max(0, count)]
        self._by_name = {ghost.name: ghost for ghost in self.ghosts}

    def clone(self) -> Game:
        """Copie independante de la partie, qu'on peut faire avancer sans risque.

        C'est ce qui permet a un agent de **simuler** la suite au lieu de
        l'apprendre : le moteur etant deterministe, ce que la copie vit est
        exactement ce que la partie vivrait.

        Le labyrinthe n'est pas copie : il ne change jamais en cours de partie,
        et le dupliquer a chaque noeud de recherche couterait plus cher que la
        recherche elle-meme.
        """
        twin = copy.copy(self)
        twin.pacman = copy.deepcopy(self.pacman)
        twin.ghosts = [copy.deepcopy(ghost) for ghost in self.ghosts]
        twin._by_name = {ghost.name: ghost for ghost in twin.ghosts}
        twin.pellets = set(self.pellets)
        twin.power_pellets = set(self.power_pellets)
        twin.events = list(self.events)
        return twin

    # ================================================================ entrees

    def set_direction(self, direction: Direction) -> None:
        """Entree du joueur. Prise en compte au prochain tick."""
        self.pacman.request(direction)

    def pause(self) -> None:
        if self.state in (GameState.READY, GameState.PLAYING):
            self._paused_from = self.state
            self.state = GameState.PAUSED

    def resume(self) -> None:
        if self.state is GameState.PAUSED:
            self.state = self._paused_from

    # ================================================================ boucle

    def tick(self) -> list[Event]:
        """Avance la partie d'un pas. Renvoie les evenements de ce tick."""
        self.events = []
        if self.state in (GameState.GAME_OVER, GameState.PAUSED):
            return self.events

        self.tick_count += 1

        if self.state is not GameState.PLAYING:
            self._tick_transition()
            return self.events

        self._tick_modes()
        self._tick_fruit()
        self._tick_pacman()

        # Une collision peut survenir avant comme apres le pas des fantomes :
        # sans ce double controle, Pac-Man traverserait un fantome venant d'en face.
        if self._resolve_collisions():
            return self.events

        self._tick_ghosts()
        self._resolve_collisions()
        self._check_level_complete()
        return self.events

    def run(self, ticks: int) -> list[Event]:
        """Enchaine `ticks` pas. Pratique pour les tests et la simulation."""
        collected: list[Event] = []
        for _ in range(ticks):
            collected.extend(self.tick())
        return collected

    # ---------------------------------------------------------------- transitions

    def _tick_transition(self) -> None:
        """Gere les etats d'attente : compte a rebours, mort, fin de niveau."""
        self._state_timer -= 1
        if self._state_timer > 0:
            return

        if self.state is GameState.READY:
            self.state = GameState.PLAYING
            self._emit("round_start", level=self.level)
        elif self.state is GameState.DYING:
            self._after_death()
        elif self.state is GameState.LEVEL_COMPLETE:
            self._next_level()

    def _after_death(self) -> None:
        if self.lives <= 0:
            self.state = GameState.GAME_OVER
            self._emit("game_over", score=self.score, level=self.level)
            return
        self._place_entities()
        self.state = GameState.READY
        self._state_timer = rules.READY_DURATION

    def _next_level(self) -> None:
        self.level += 1
        self.pellets = set(self.maze.pellets)
        self.power_pellets = set(self.maze.power_pellets)
        self._dots_eaten = 0
        self._fruits_spawned = 0
        self._apply_level_rules()
        self._place_entities()
        self.state = GameState.READY
        self._state_timer = rules.READY_DURATION
        self._emit("level_start", level=self.level)

    # ---------------------------------------------------------------- modes

    def _tick_modes(self) -> None:
        """Fait avancer l'alternance scatter/chase et le compte a rebours d'effroi."""
        if self._frightened_timer > 0:
            self._frightened_timer -= 1
            if self._frightened_timer == 0:
                self._end_frightened()
            # Pendant l'effroi, l'alternance scatter/chase est gelee.
            return

        waves = self._rules.mode_waves
        if self._wave_index >= len(waves):
            return  # derniere vague : chase pour toujours

        self._wave_timer -= 1
        if self._wave_timer > 0:
            return

        self._wave_index += 1
        target = self._current_wave_mode()
        for ghost in self.ghosts:
            if ghost.is_active:
                ghost.set_mode(target)
        if self._wave_index < len(waves):
            self._wave_timer = waves[self._wave_index]
        self._emit("wave", mode=target.value, index=self._wave_index)

    def _current_wave_mode(self) -> GhostMode:
        """Les vagues d'indice pair sont des phases scatter, les impaires des chases."""
        if self._wave_index >= len(self._rules.mode_waves):
            return GhostMode.CHASE
        return GhostMode.SCATTER if self._wave_index % 2 == 0 else GhostMode.CHASE

    def _start_frightened(self) -> None:
        duration = self._rules.frightened_duration
        self._ghost_chain = 0
        for ghost in self.ghosts:
            if ghost.is_active:
                # Meme sans duree (niveaux eleves), les fantomes font demi-tour.
                ghost.set_mode(GhostMode.FRIGHTENED)
                if duration <= 0:
                    ghost.set_mode(self._current_wave_mode(), reverse=False)
        if duration > 0:
            self._frightened_timer = duration
            self.pacman.energized = True
            self._emit("frightened", duration=duration)

    def _end_frightened(self) -> None:
        self.pacman.energized = False
        self._ghost_chain = 0
        target = self._current_wave_mode()
        for ghost in self.ghosts:
            if ghost.mode is GhostMode.FRIGHTENED:
                ghost.set_mode(target, reverse=False)
        self._emit("frightened_end")

    # ---------------------------------------------------------------- entites

    def _tick_fruit(self) -> None:
        """Fait expirer le fruit present. Il ne reste affiche qu'un temps limite."""
        if self.fruit is None:
            return
        self._fruit_timer -= 1
        if self._fruit_timer <= 0:
            self.fruit = None
            self._emit("fruit_gone")

    def _maybe_spawn_fruit(self) -> None:
        """Fait apparaitre un fruit aux paliers de pastilles du jeu d'origine."""
        if self._fruits_spawned >= len(rules.FRUIT_DOT_TRIGGERS):
            return
        if self._dots_eaten < rules.FRUIT_DOT_TRIGGERS[self._fruits_spawned]:
            return

        self._fruits_spawned += 1
        self.fruit = self.maze.fruit_start or self.maze.pacman_start
        self.fruit_name, points = rules.fruit_for(self.level)
        self._fruit_timer = rules.FRUIT_DURATION
        self._emit(
            "fruit_spawn",
            x=self.fruit.x,
            y=self.fruit.y,
            name=self.fruit_name,
            points=points,
        )

    def _tick_pacman(self) -> None:
        if not self.pacman.update(self):
            return
        pos = self.pacman.position

        if self.fruit is not None and pos == self.fruit:
            _, points = rules.fruit_for(self.level)
            self.fruit = None
            self._add_score(points)
            self._emit("fruit_eaten", name=self.fruit_name, points=points)

        if pos in self.pellets:
            self.pellets.discard(pos)
            self._add_score(rules.POINTS_PELLET)
            self._dots_eaten += 1
            self._emit("pellet", x=pos.x, y=pos.y)
            self._release_ghosts()
            self._maybe_spawn_fruit()
        elif pos in self.power_pellets:
            self.power_pellets.discard(pos)
            self._add_score(rules.POINTS_POWER_PELLET)
            self._dots_eaten += 1
            self._emit("power_pellet", x=pos.x, y=pos.y)
            self._release_ghosts()
            self._maybe_spawn_fruit()
            self._start_frightened()

    def _tick_ghosts(self) -> None:
        for ghost in self.ghosts:
            if ghost.mode is GhostMode.EATEN and ghost.position == ghost.home_target:
                # Les yeux sont rentres : le fantome se reconstitue et ressort.
                ghost.set_mode(GhostMode.LEAVING, reverse=False)
                continue

            if ghost.mode is GhostMode.LEAVING and ghost.position == ghost.house_exit:
                ghost.set_mode(self._current_wave_mode(), reverse=False)

            ghost.update(self)

    def _release_ghosts(self) -> None:
        """Libere les fantomes dont le quota de pastilles est atteint."""
        for ghost in self.ghosts:
            if ghost.mode is not GhostMode.HOUSE:
                continue
            limit = self._rules.dot_limits.get(ghost.name, 0)
            if self._dots_eaten >= limit:
                ghost.set_mode(GhostMode.LEAVING, reverse=False)
                self._emit("ghost_released", ghost=ghost.name)

    # ---------------------------------------------------------------- collisions

    def _resolve_collisions(self) -> bool:
        """Traite les rencontres Pac-Man / fantome. Renvoie True si Pac-Man est mort."""
        for ghost in self.ghosts:
            if not self._touching(ghost):
                continue

            if ghost.mode is GhostMode.FRIGHTENED:
                self._eat_ghost(ghost)
            elif ghost.is_active:
                self._kill_pacman(ghost)
                return True
        return False

    def _touching(self, ghost: Ghost) -> bool:
        """Meme case, ou echange de cases : deux entites ne se traversent pas."""
        if ghost.position == self.pacman.position:
            return True
        # Croisement frontal : chacun a pris la case que l'autre quittait.
        return (
            ghost.position == self.pacman.previous_position
            and ghost.previous_position == self.pacman.position
        )

    def _eat_ghost(self, ghost: Ghost) -> None:
        points = rules.POINTS_GHOST_CHAIN[min(self._ghost_chain, len(rules.POINTS_GHOST_CHAIN) - 1)]
        self._ghost_chain += 1
        self._add_score(points)
        ghost.set_mode(GhostMode.EATEN, reverse=False)
        self._emit("ghost_eaten", ghost=ghost.name, points=points)

    def _kill_pacman(self, ghost: Ghost) -> None:
        self.lives -= 1
        self.state = GameState.DYING
        self._state_timer = rules.DEATH_DURATION
        self._frightened_timer = 0
        self.pacman.energized = False
        self._emit("pacman_died", ghost=ghost.name, lives=self.lives)

    def _check_level_complete(self) -> None:
        if self.remaining_pellets > 0:
            return
        self.state = GameState.LEVEL_COMPLETE
        self._state_timer = rules.LEVEL_END_DURATION
        self._emit("level_complete", level=self.level, score=self.score)

    # ---------------------------------------------------------------- utilitaires

    def _add_score(self, points: int) -> None:
        self.score += points
        if self.score >= self._extra_life_at:
            self.lives += 1
            self._extra_life_at += rules.EXTRA_LIFE_SCORE
            self._emit("extra_life", lives=self.lives)

    def _apply_level_rules(self) -> None:
        self._rules = rules.rules_for(self.level)
        self.pacman.base_speed = self._rules.pacman_speed
        for ghost in self.ghosts:
            ghost.base_speed = self._rules.ghost_speed
            ghost.frightened_speed = self._rules.frightened_speed

    def _place_entities(self) -> None:
        """Replace tout le monde au depart et relance l'alternance de modes."""
        self.pacman.reset()
        exit_tile = self._house_exit()
        home_tile = self._house_center(exit_tile)
        for ghost in self.ghosts:
            ghost.reset()
            ghost.house_exit = exit_tile
            ghost.home_target = home_tile

        self._frightened_timer = 0
        self._ghost_chain = 0
        self._wave_index = 0
        self._wave_timer = self._rules.mode_waves[0] if self._rules.mode_waves else 0
        # Un fruit non ramasse ne survit pas a la perte d'une vie.
        self.fruit = None
        self._fruit_timer = 0

        # Blinky commence toujours dehors : c'est lui qui met la pression d'entree.
        blinky = self._by_name.get("blinky")
        if blinky is not None and not self.maze.in_house(blinky.start):
            blinky.set_mode(GhostMode.SCATTER, reverse=False)

        self._release_ghosts()

    def _house_exit(self) -> Position:
        """Case libre juste au-dessus de la porte de la maison."""
        if not self.maze.doors:
            return self.maze.pacman_start
        door = min(self.maze.doors, key=lambda p: (p.y, p.x))
        return Position(door.x, door.y - 1)

    def _house_center(self, exit_tile: Position) -> Position:
        """Case de la maison ou les fantomes manges se reconstituent."""
        if not self.maze.house:
            return exit_tile
        # La plus proche de la porte : les yeux n'ont pas a traverser toute la maison.
        door = min(self.maze.doors, key=lambda p: (p.y, p.x))
        return min(self.maze.house, key=lambda p: (p.manhattan(door), p.y, p.x))

    def _emit(self, type_: str, **payload) -> None:
        self.events.append(Event(type_, payload))
