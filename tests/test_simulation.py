from smartclean_sim.grid import GridWorld
from smartclean_sim.models import CleaningTask
from smartclean_sim.simulation import DynamicObstacle, Simulator


def scenario_payload():
    return {
        "width": 6,
        "height": 5,
        "start": [0, 0],
        "dock": [0, 0],
        "static_obstacles": [[2, 1], [2, 2], [2, 3]],
        "hazards": {"water": [[4, 1]]},
        "trash": [
            {
                "id": "leaf",
                "kind": "fallen_leaves",
                "position": [1, 4],
                "area": "gate",
            },
            {
                "id": "bottle",
                "kind": "plastic_bottle",
                "position": [5, 4],
                "area": "gate",
            },
        ],
    }


def test_simulator_cleans_targets_and_returns_to_dock() -> None:
    world = GridWorld.from_dict(scenario_payload())
    task = CleaningTask(
        target_area="gate",
        priority_classes=("fallen_leaves", "plastic_bottle"),
        avoid_types=("water", "pedestrian"),
        return_to_dock=True,
    )
    result = Simulator(world, task, max_steps=100).run()

    assert result.status == "COMPLETED"
    assert result.metrics.cleaned_targets == 2
    assert result.metrics.completion_rate == 1.0
    assert result.metrics.returned_to_dock is True
    assert result.metrics.collisions == 0


def test_dynamic_obstacle_is_never_entered() -> None:
    world = GridWorld.from_dict(scenario_payload())
    task = CleaningTask(
        target_area="gate",
        avoid_types=("water", "pedestrian"),
        return_to_dock=False,
    )
    pedestrian = DynamicObstacle.from_dict(
        {
            "id": "walker",
            "kind": "pedestrian",
            "path": [[0, 1], [1, 1], [0, 1], [1, 1]],
            "loop": True,
        }
    )
    result = Simulator(world, task, (pedestrian,), max_steps=100).run()

    assert result.status == "COMPLETED"
    assert result.metrics.collisions == 0


def test_moving_obstacle_triggers_safe_replan() -> None:
    world = GridWorld.from_dict(
        {
            "width": 5,
            "height": 2,
            "start": [0, 0],
            "dock": [0, 0],
            "trash": [
                {
                    "id": "leaf",
                    "kind": "fallen_leaves",
                    "position": [4, 0],
                    "area": "gate",
                }
            ],
        }
    )
    task = CleaningTask(target_area="gate", return_to_dock=False)
    pedestrian = DynamicObstacle.from_dict(
        {
            "id": "walker",
            "kind": "pedestrian",
            "path": [[4, 1], [3, 1], [2, 0], [2, 1]],
            "loop": True,
        }
    )

    result = Simulator(world, task, (pedestrian,), max_steps=30).run()

    assert result.status == "COMPLETED"
    assert result.metrics.replans >= 1
    assert result.metrics.collisions == 0
    assert "AVOIDING -> REPLANNING" in result.events
