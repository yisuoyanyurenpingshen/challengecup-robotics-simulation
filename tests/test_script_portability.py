"""Regression tests for run-script portability.

The verify scripts must not depend on developer-only tools (for example ripgrep)
that are absent from a minimal Pixi runtime PATH. These tests run without ROS,
Gazebo, or any repository-local tool on PATH.
"""

import os
import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MINIMAL_PATH = "/usr/bin:/bin"

# Tools that exist only on developer machines and must not be called by
# repository run scripts. Shell builtins and POSIX utilities stay allowed.
DENYLIST = ("rg", "codex", "gh", "hub")

# POSIX/bash utilities that a minimal runtime PATH must provide.
REQUIRED_UTILS = ("bash", "grep", "sed", "awk", "cut", "sort", "uname")


def _script_paths():
    return sorted(SCRIPTS_DIR.glob("*.sh"))


def test_verify_scripts_do_not_use_ripgrep():
    """Line matching in verify scripts must use POSIX grep, not rg."""

    for script in _script_paths():
        text = script.read_text(encoding="utf-8")
        assert "rg" not in text.split(), (
            "{} must not depend on ripgrep; use grep -Fxq for exact "
            "line matching".format(script.name)
        )


def test_scripts_avoid_private_developer_tools():
    """No run script may invoke Codex-only or GitHub-only tools."""

    for script in _script_paths():
        text = script.read_text(encoding="utf-8")
        words = set(re.findall(r"[A-Za-z0-9_./-]+", text))
        for tool in DENYLIST:
            assert tool not in words, (
                "{} references private tool '{}'".format(script.name, tool)
            )


def test_verify_scripts_use_exact_grep_matching():
    """World and topic presence assertions must be exact whole-line checks."""

    drive_verify = (SCRIPTS_DIR / "verify_gazebo_drive.sh").read_text(
        encoding="utf-8"
    )
    gazebo_verify = (SCRIPTS_DIR / "verify_gazebo.sh").read_text(
        encoding="utf-8"
    )
    assert "grep -Fxq" in drive_verify
    assert "grep -Fxq" in gazebo_verify
    for needle in (
        "/world/smartclean_drive/control",
        "/smartclean/odom",
        "/smartclean/tf",
    ):
        assert needle in drive_verify
    assert "/world/smartclean_smoke/control" in gazebo_verify


def test_all_scripts_pass_bash_syntax_check():
    """Every shell entry point must be syntactically valid."""

    for script in _script_paths():
        result = subprocess.run(
            ["bash", "-n", str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "bash -n failed for {}: {}".format(script.name, result.stderr)
        )


def test_exact_line_match_assertion_works_with_minimal_path():
    """The grep -Fxq assertions work under a minimal PATH, without rg."""

    listing = "/world/smartclean_drive/control\n/smartclean/odom\n/smartclean/tf\n"
    env = dict(os.environ)
    env["PATH"] = MINIMAL_PATH
    for needle in (
        "/world/smartclean_drive/control",
        "/smartclean/odom",
        "/smartclean/tf",
    ):
        result = subprocess.run(
            ["grep", "-Fxq", needle],
            input=listing,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, "grep -Fxq failed for {}".format(needle)
    missing = subprocess.run(
        ["grep", "-Fxq", "/no/such/service"],
        input=listing,
        capture_output=True,
        text=True,
        env=env,
    )
    assert missing.returncode != 0


def test_required_posix_utilities_exist_on_minimal_path():
    """The minimal PATH used by portability checks contains POSIX tools."""

    for tool in REQUIRED_UTILS:
        found = False
        for directory in MINIMAL_PATH.split(os.pathsep):
            if (pathlib.Path(directory) / tool).is_file():
                found = True
                break
        assert found, "minimal PATH is missing required tool {}".format(tool)


def test_ros2_usage_hints_single_command_form():
    """The unified entry point must show the correct one-command form."""

    text = (SCRIPTS_DIR / "ros2.sh").read_text(encoding="utf-8")
    assert "bash scripts/ros2.sh drive" in text
    assert "drivebash" in text
