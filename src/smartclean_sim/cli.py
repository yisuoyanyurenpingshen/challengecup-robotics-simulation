"""SmartClean-Sim 命令行入口。"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from smartclean_sim.config import ConfigError, load_config
from smartclean_sim.html_visualization import write_animation_html
from smartclean_sim.rendering import render_ascii
from smartclean_sim.simulation import Simulator
from smartclean_sim.tasking import TaskParseError, task_from_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 SmartClean-Sim 二维清扫闭环")
    parser.add_argument("--config", default="configs/demo.json", help="JSON 配置路径")
    parser.add_argument("--task", help="覆盖配置中的自然语言任务")
    parser.add_argument("--output", help="将结构化结果写入 JSON 文件")
    parser.add_argument(
        "--animate",
        metavar="HTML_PATH",
        help="导出可离线打开的自包含 HTML 动画",
    )
    parser.add_argument("--show-map", action="store_true", help="在终端显示最终路线图")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        task_payload = dict(config["task"])
        if args.task:
            task_payload = {"instruction": args.task}
        task = task_from_dict(task_payload)
        simulator = Simulator.from_config(config, task)
        result = simulator.run()
    except (ConfigError, TaskParseError, ValueError) as exc:
        print("配置或任务错误：{}".format(exc), file=sys.stderr)
        return 2

    result_payload = result.to_dict()
    summary = {
        "status": result.status,
        "cleaned": "{}/{}".format(
            result.metrics.cleaned_targets, result.metrics.total_targets
        ),
        "completion_rate": round(result.metrics.completion_rate, 4),
        "coverage_rate": round(result.metrics.coverage_rate, 4),
        "path_length_cells": result.metrics.path_length_cells,
        "replans": result.metrics.replans,
        "collisions": result.metrics.collisions,
        "returned_to_dock": result.metrics.returned_to_dock,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.show_map:
        print("\n图例：# 障碍，W 积水，* 轨迹，D 充电点，R 机器人")
        print(render_ascii(simulator.world, result.trajectory, result.final_position))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as stream:
            json.dump(result_payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print("结果已写入：{}".format(output_path))

    if args.animate:
        animation_path = write_animation_html(
            config["scenario"],
            result,
            args.animate,
            title="SmartClean-Sim · {}".format(
                config["scenario"].get("name", "清扫演示")
            ),
        )
        print("动画已写入：{}".format(animation_path))

    return 0 if result.metrics.completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
