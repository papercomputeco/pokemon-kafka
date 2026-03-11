"""Tests for A* pathfinding on the collision grid."""

from pathfinding import astar_path


class TestAStarPath:
    def _open_grid(self):
        """9x10 grid, all walkable."""
        return [[1] * 10 for _ in range(9)]

    def test_already_at_target(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (4, 4))
        assert result == {"status": "success", "directions": []}

    def test_simple_right(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (4, 6))
        assert result["status"] == "success"
        assert result["directions"] == ["right", "right"]

    def test_simple_left(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (4, 2))
        assert result["status"] == "success"
        assert result["directions"] == ["left", "left"]

    def test_simple_down(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (6, 4))
        assert result["status"] == "success"
        assert result["directions"] == ["down", "down"]

    def test_simple_up(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (2, 4))
        assert result["status"] == "success"
        assert result["directions"] == ["up", "up"]

    def test_path_around_wall(self):
        grid = self._open_grid()
        grid[4][5] = 0
        result = astar_path(grid, (4, 4), (4, 6))
        assert result["status"] == "success"
        assert len(result["directions"]) > 2

    def test_target_unreachable(self):
        grid = self._open_grid()
        for r in range(3, 6):
            for c in range(3, 6):
                grid[r][c] = 0
        grid[4][4] = 1
        result = astar_path(grid, (4, 4), (0, 0))
        assert result["status"] == "failure"
        assert result["directions"] == []

    def test_target_is_wall(self):
        grid = self._open_grid()
        grid[0][0] = 0
        result = astar_path(grid, (4, 4), (0, 0))
        assert result["status"] == "partial"

    def test_diagonal_path(self):
        grid = self._open_grid()
        result = astar_path(grid, (0, 0), (2, 2))
        assert result["status"] == "success"
        assert len(result["directions"]) == 4

    def test_out_of_bounds_target(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (20, 20))
        assert result["status"] == "failure"

    def test_out_of_bounds_start(self):
        grid = self._open_grid()
        result = astar_path(grid, (20, 20), (4, 4))
        assert result["status"] == "failure"

    def test_avoid_sprites(self):
        grid = self._open_grid()
        result = astar_path(grid, (4, 4), (4, 6), sprites=[(4, 5)])
        assert result["status"] == "success"
        assert len(result["directions"]) > 2
