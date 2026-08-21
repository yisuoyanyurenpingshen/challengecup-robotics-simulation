import unittest

from smartclean_sim.grid import GridWorld
from smartclean_sim.models import GridPosition
from smartclean_sim.planning import AStarPlanner, NoPathError


class AStarPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = AStarPlanner()

    def test_path_reaches_goal_without_crossing_wall(self):
        wall = {GridPosition(2, 0), GridPosition(2, 1), GridPosition(2, 2)}
        world = GridWorld(
            width=5,
            height=4,
            start=GridPosition(0, 1),
            dock=GridPosition(0, 1),
            static_obstacles=wall,
        )

        path = self.planner.plan(world, world.start, GridPosition(4, 1))

        self.assertEqual(path[0], world.start)
        self.assertEqual(path[-1], GridPosition(4, 1))
        self.assertTrue(wall.isdisjoint(path))
        self.assertEqual(len(path), 9)
        for current, following in zip(path, path[1:]):
            self.assertEqual(
                abs(current.x - following.x) + abs(current.y - following.y),
                1,
            )

    def test_path_avoids_requested_water_hazard(self):
        water = GridPosition(2, 1)
        world = GridWorld(
            width=5,
            height=3,
            start=GridPosition(0, 1),
            dock=GridPosition(0, 1),
            hazards={"water": {water}},
        )
        goal = GridPosition(4, 1)

        direct_path = self.planner.plan(world, world.start, goal)
        safe_path = self.planner.plan(
            world, world.start, goal, avoid_types=("water",)
        )

        self.assertIn(water, direct_path)
        self.assertNotIn(water, safe_path)
        self.assertEqual(len(direct_path), 5)
        self.assertEqual(len(safe_path), 7)

    def test_no_path_raises_clear_error(self):
        world = GridWorld(
            width=3,
            height=3,
            start=GridPosition(0, 1),
            dock=GridPosition(0, 1),
            static_obstacles={
                GridPosition(1, 0),
                GridPosition(1, 1),
                GridPosition(1, 2),
            },
        )

        with self.assertRaises(NoPathError):
            self.planner.plan(world, world.start, GridPosition(2, 1))

    def test_extra_blocked_cells_are_honored(self):
        world = GridWorld(
            width=3,
            height=2,
            start=GridPosition(0, 0),
            dock=GridPosition(0, 0),
        )

        path = self.planner.plan(
            world,
            world.start,
            GridPosition(2, 0),
            extra_blocked={GridPosition(1, 0)},
        )

        self.assertNotIn(GridPosition(1, 0), path)
        self.assertEqual(len(path), 5)


if __name__ == "__main__":
    unittest.main()
