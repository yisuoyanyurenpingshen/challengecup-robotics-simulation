#!/usr/bin/env python3
"""Assert that the local Gazebo trash world spawns every ground-truth entity."""

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = PROJECT_ROOT / "configs" / "gazebo_scene.json"


def _ign_model_list() -> str:
    result = subprocess.run(
        ["ign", "model", "--list"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout


def main() -> int:
    scene = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
    expected = {
        item["model_name"]
        for item in scene["trash"]
        if item.get("model_name")
    }
    expected.add("smartclean_robot")

    deadline = time.monotonic() + 45.0
    spawned = set()
    while time.monotonic() < deadline:
        spawned = {
            line.strip().lstrip("-").strip()
            for line in _ign_model_list().splitlines()
            if line.strip().lstrip("-").strip()
        }
        if expected <= spawned:
            break
        time.sleep(1.0)

    missing = sorted(expected - spawned)
    if missing:
        print("垃圾场景验证失败：缺少模型 {}".format(", ".join(missing)))
        return 1
    print(
        "垃圾场景实体验证通过：机器人 + {} 个垃圾模型全部在场".format(
            len(expected) - 1
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
