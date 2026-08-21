"""让源码布局在未执行 editable install 时也能被 pytest 导入。"""

import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

