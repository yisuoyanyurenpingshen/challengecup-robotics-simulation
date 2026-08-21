from math import inf, nan

import pytest

from smartclean_ros.cmd_vel_guard_core import CmdVelGuard
from smartclean_ros.cmd_vel_guard_core import VelocityCommand, VelocityGuardError


def test_guard_outputs_zero_before_receiving_a_command() -> None:
    guard = CmdVelGuard()

    assert guard.safe_command(0.0) == VelocityCommand()
    assert guard.safe_command(100.0) == VelocityCommand()


def test_guard_forwards_all_components_until_timeout() -> None:
    guard = CmdVelGuard(command_timeout_s=0.5)
    command = VelocityCommand(
        linear_x=1.0,
        linear_y=-2.0,
        linear_z=3.0,
        angular_x=-4.0,
        angular_y=5.0,
        angular_z=-6.0,
    )

    assert guard.accept(command, received_at_s=10.0) is True
    assert guard.safe_command(10.0) == command
    assert guard.safe_command(10.499) == command
    assert guard.safe_command(10.5) == VelocityCommand()


@pytest.mark.parametrize(
    "command",
    [
        VelocityCommand(linear_x=nan),
        VelocityCommand(linear_y=inf),
        VelocityCommand(linear_z=-inf),
        VelocityCommand(angular_x=nan),
        VelocityCommand(angular_y=inf),
        VelocityCommand(angular_z=-inf),
    ],
)
def test_non_finite_component_is_rejected_and_invalidates_previous_command(
    command: VelocityCommand,
) -> None:
    guard = CmdVelGuard()
    valid = VelocityCommand(linear_x=0.25, angular_z=-0.5)
    assert guard.accept(valid, received_at_s=1.0) is True

    assert guard.accept(command, received_at_s=1.1) is False
    assert guard.safe_command(1.1) == VelocityCommand()


def test_guard_recovers_after_invalid_command() -> None:
    guard = CmdVelGuard()
    valid = VelocityCommand(linear_x=0.2)

    assert guard.accept(VelocityCommand(angular_z=nan), 0.0) is False
    assert guard.accept(valid, 0.1) is True
    assert guard.safe_command(0.2) == valid


def test_backward_clock_jump_invalidates_the_stored_command() -> None:
    guard = CmdVelGuard()
    command = VelocityCommand(linear_x=0.5)
    guard.accept(command, received_at_s=5.0)

    assert guard.safe_command(4.9) == VelocityCommand()
    assert guard.safe_command(5.1) == VelocityCommand()


@pytest.mark.parametrize("timeout", [0.0, -0.1, nan, inf, True, "invalid"])
def test_invalid_timeout_is_rejected(timeout) -> None:
    with pytest.raises(VelocityGuardError, match="command_timeout_s"):
        CmdVelGuard(command_timeout_s=timeout)


@pytest.mark.parametrize("timestamp", [nan, inf, -inf, True, "invalid"])
def test_invalid_clock_value_is_rejected(timestamp) -> None:
    guard = CmdVelGuard()

    with pytest.raises(VelocityGuardError):
        guard.safe_command(timestamp)
