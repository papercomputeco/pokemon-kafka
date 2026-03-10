"""A* pathfinding on a 9x10 collision grid."""

import heapq


def astar_path(
    grid: list[list[int]],
    start: tuple[int, int],
    target: tuple[int, int],
    sprites: list[tuple[int, int]] | None = None,
) -> dict:
    """
    Find path from start to target on a collision grid.

    Args:
        grid: 9x10 grid (0 = wall, 1 = walkable)
        start: (row, col) start position
        target: (row, col) target position
        sprites: list of (row, col) positions to avoid

    Returns:
        {"status": "success"|"partial"|"failure", "directions": [...]}
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    sprite_set = set(sprites) if sprites else set()

    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        return {"status": "failure", "directions": []}
    if not (0 <= target[0] < rows and 0 <= target[1] < cols):
        return {"status": "failure", "directions": []}

    if start == target:
        return {"status": "success", "directions": []}

    target_is_wall = grid[target[0]][target[1]] == 0

    def heuristic(pos):
        return abs(pos[0] - target[0]) + abs(pos[1] - target[1])

    counter = 0
    open_set = [(heuristic(start), counter, start[0], start[1])]
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}
    closed: set[tuple[int, int]] = set()

    best_partial = start
    best_partial_dist = heuristic(start)

    moves = [(-1, 0, "up"), (1, 0, "down"), (0, -1, "left"), (0, 1, "right")]

    while open_set:
        _, _, r, c = heapq.heappop(open_set)
        pos = (r, c)

        closed.add(pos)

        if pos == target:
            return {"status": "success", "directions": _reconstruct(came_from, start, target)}

        for dr, dc, _ in moves:
            nr, nc = r + dr, c + dc
            npos = (nr, nc)

            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if npos in closed:
                continue
            if grid[nr][nc] == 0:
                continue
            if npos in sprite_set and npos != target:
                continue

            new_g = g_score[pos] + 1
            if new_g < g_score.get(npos, float("inf")):
                g_score[npos] = new_g
                came_from[npos] = pos
                f = new_g + heuristic(npos)
                counter += 1
                heapq.heappush(open_set, (f, counter, nr, nc))

                dist = heuristic(npos)
                if dist < best_partial_dist and grid[nr][nc] != 0:
                    best_partial_dist = dist
                    best_partial = npos

    if target_is_wall and best_partial != start:
        return {"status": "partial", "directions": _reconstruct(came_from, start, best_partial)}

    return {"status": "failure", "directions": []}


def _reconstruct(came_from, start, end):
    """Reconstruct path as list of direction strings."""
    path = []
    current = end
    while current != start:
        prev = came_from[current]
        dr = current[0] - prev[0]
        dc = current[1] - prev[1]
        if dr == -1:
            path.append("up")
        elif dr == 1:
            path.append("down")
        elif dc == -1:
            path.append("left")
        elif dc == 1:
            path.append("right")
        current = prev
    path.reverse()
    return path
