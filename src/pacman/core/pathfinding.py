"""Recherche de chemin sur la grille du labyrinthe.

Les fantomes du jeu d'origine ne calculent aucun chemin : ils choisissent
betement la direction qui reduit la distance a vol d'oiseau, ce qui les fait
buter sur les murs. On garde ce comportement pour la fidelite, mais deux cas
demandent un vrai chemin :

- les yeux d'un fantome mange, qui doivent rentrer a coup sur ;
- les fantomes « chasseurs » du mode difficile, qui eux voient les murs.

Les mouvements sont explores dans l'ordre haut, gauche, bas, droite, si bien
qu'a longueur egale le chemin retenu est toujours le meme : la recherche ne
casse pas le determinisme du moteur.
"""

from __future__ import annotations

from collections import deque
from heapq import heappop, heappush

from .geometry import Direction, Position
from .maze import Maze


def bfs_path(
    maze: Maze,
    start: Position,
    goal: Position,
    *,
    through_door: bool = False,
) -> list[Position]:
    """Plus court chemin de `start` a `goal`, cases intermediaires incluses.

    Renvoie une liste commencant par `start` et finissant par `goal`, ou une
    liste vide si la cible est inatteignable.
    """
    if start == goal:
        return [start]

    came_from: dict[Position, Position] = {start: start}
    queue: deque[Position] = deque([start])

    while queue:
        current = queue.popleft()
        for _, neighbor in maze.neighbors(current, through_door=through_door):
            if neighbor in came_from:
                continue
            came_from[neighbor] = current
            if neighbor == goal:
                return _rebuild(came_from, start, goal)
            queue.append(neighbor)

    return []


def torus_distance(maze: Maze, a: Position, b: Position) -> int:
    """Distance de Manhattan tenant compte du repliement par les tunnels.

    C'est l'heuristique d'A* ici. La Manhattan classique serait fausse : entre
    deux cases separees par un tunnel, elle annonce la traversee de tout le
    labyrinthe alors que deux pas suffisent. Elle surestimerait donc le cout
    reel, et A* rendrait des chemins non optimaux.
    """
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return min(dx, maze.width - dx) + min(dy, maze.height - dy)


def a_star_path(
    maze: Maze,
    start: Position,
    goal: Position,
    *,
    through_door: bool = False,
) -> list[Position]:
    """Meme resultat que `bfs_path`, mais guide vers la cible.

    A poids uniformes et avec une heuristique qui ne surestime jamais le cout
    restant, le chemin trouve est optimal. Interessant sur de grands
    labyrinthes, ou A* explore bien moins de cases que le parcours en largeur.
    """
    if start == goal:
        return [start]

    came_from: dict[Position, Position] = {start: start}
    cost: dict[Position, int] = {start: 0}
    # Le compteur departage les ex aequo dans le tas, ce qui rend l'ordre stable.
    counter = 0
    frontier: list[tuple[int, int, Position]] = [(torus_distance(maze, start, goal), 0, start)]

    while frontier:
        _, _, current = heappop(frontier)
        if current == goal:
            return _rebuild(came_from, start, goal)

        next_cost = cost[current] + 1
        for _, neighbor in maze.neighbors(current, through_door=through_door):
            if neighbor in cost and cost[neighbor] <= next_cost:
                continue
            cost[neighbor] = next_cost
            came_from[neighbor] = current
            counter += 1
            heappush(
                frontier,
                (next_cost + torus_distance(maze, neighbor, goal), counter, neighbor),
            )

    return []


def next_direction(
    maze: Maze,
    start: Position,
    goal: Position,
    *,
    through_door: bool = False,
) -> Direction:
    """Premiere direction a prendre pour rejoindre `goal`, ou NONE si impossible."""
    path = bfs_path(maze, start, goal, through_door=through_door)
    if len(path) < 2:
        return Direction.NONE

    step = path[1]
    for direction in Direction.moves():
        if maze.step(start, direction) == step:
            return direction
    return Direction.NONE


def distance_map(
    maze: Maze,
    source: Position,
    *,
    through_door: bool = False,
) -> dict[Position, int]:
    """Distance reelle de `source` vers toutes les cases atteignables.

    Un seul parcours suffit ensuite a comparer plusieurs cibles, la ou un BFS
    par cible serait redondant.
    """
    distances = {source: 0}
    queue: deque[Position] = deque([source])

    while queue:
        current = queue.popleft()
        for _, neighbor in maze.neighbors(current, through_door=through_door):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)

    return distances


def _rebuild(
    came_from: dict[Position, Position], start: Position, goal: Position
) -> list[Position]:
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    path.reverse()
    return path
