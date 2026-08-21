import json
from pathlib import Path

from smartclean_sim.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_exports_json_and_self_contained_animation(tmp_path: Path) -> None:
    result_path = tmp_path / "nested" / "result.json"
    animation_path = tmp_path / "nested" / "animation.html"

    exit_code = main(
        [
            "--config",
            str(PROJECT_ROOT / "configs" / "demo.json"),
            "--output",
            str(result_path),
            "--animate",
            str(animation_path),
        ]
    )

    assert exit_code == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    animation = animation_path.read_text(encoding="utf-8")
    assert result["status"] == "COMPLETED"
    assert result["rates"]["coverage_rate"] == 1.0
    assert len(result["trace"]["frames"]) > 1
    assert '<canvas id="worldCanvas"' in animation
    assert "https://" not in animation
    assert "fetch(" not in animation
