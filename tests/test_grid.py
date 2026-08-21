import unittest

from smartclean_sim.grid import GridWorld
from smartclean_sim.models import GridPosition


class GridWorldTests(unittest.TestCase):
    def setUp(self):
        self.world = GridWorld.from_dict(
            {
                "width": 4,
                "height": 3,
                "start": [0, 0],
                "dock": {"x": 0, "y": 0},
                "static_obstacles": [[1, 0]],
                "hazards": {"water": [[2, 1]]},
                "trash": [
                    {
                        "item_id": "leaf-1",
                        "kind": "fallen_leaves",
                        "position": [3, 2],
                        "area": "gate",
                    },
                    {
                        "id": "bottle-1",
                        "type": "plastic_bottle",
                        "position": {"x": 3, "y": 2},
                        "area": "gate",
                    },
                ],
            }
        )

    def test_bounds_and_semantic_blocking(self):
        self.assertTrue(self.world.in_bounds(GridPosition(3, 2)))
        self.assertFalse(self.world.in_bounds(GridPosition(4, 2)))
        self.assertTrue(self.world.is_blocked(GridPosition(1, 0)))
        self.assertTrue(self.world.is_blocked(GridPosition(-1, 0)))

        water = GridPosition(2, 1)
        self.assertFalse(self.world.is_blocked(water))
        self.assertTrue(self.world.is_blocked(water, avoid_types=("water",)))

    def test_neighbors_stay_in_bounds_and_skip_blocked_cells(self):
        neighbors = self.world.neighbors(
            GridPosition(2, 0), avoid_types=("water",)
        )
        self.assertEqual(neighbors, (GridPosition(3, 0),))

    def test_clean_at_removes_matching_items(self):
        position = GridPosition(3, 2)
        cleaned = self.world.clean_at(
            position,
            target_area="gate",
            kinds=("fallen_leaves",),
        )

        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned.item_id, "leaf-1")
        self.assertEqual(
            [item.item_id for item in self.world.remaining_trash()],
            ["bottle-1"],
        )
        self.assertIsNone(
            self.world.clean_at(position, kinds=("fallen_leaves",))
        )

    def test_traversable_count_respects_avoid_types(self):
        self.assertEqual(self.world.traversable_count(), 11)
        self.assertEqual(self.world.traversable_count(("water",)), 10)


if __name__ == "__main__":
    unittest.main()
