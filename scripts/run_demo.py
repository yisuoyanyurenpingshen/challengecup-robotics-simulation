#!/usr/bin/env python3
"""无需先安装包即可从仓库根目录运行默认演示。"""

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from smartclean_sim.cli import main  # noqa: E402


if __name__ == "__main__":
    default_arguments = ["--config", str(REPOSITORY_ROOT / "configs" / "demo.json")]
    raise SystemExit(main(default_arguments + sys.argv[1:]))

