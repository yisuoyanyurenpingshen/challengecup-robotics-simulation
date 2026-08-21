"""项目配置加载与最小结构校验。"""

import json
from pathlib import Path
from typing import Any, Dict, Union


class ConfigError(ValueError):
    """配置缺失、格式错误或版本不受支持。"""


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except FileNotFoundError as exc:
        raise ConfigError("配置文件不存在：{}".format(config_path)) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("配置不是合法 JSON：{}".format(exc)) from exc

    if not isinstance(payload, dict):
        raise ConfigError("配置顶层必须是 JSON 对象")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != 1:
        raise ConfigError("仅支持 schema_version=1")
    for required in ("scenario", "task", "simulation"):
        if not isinstance(payload.get(required), dict):
            raise ConfigError("缺少对象字段：{}".format(required))
    return payload
