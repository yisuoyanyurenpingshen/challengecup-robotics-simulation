"""ROS-independent velocity-command safety watchdog."""

from dataclasses import dataclass
from math import isfinite
from typing import Optional


class VelocityGuardError(ValueError):
    """The watchdog received an invalid configuration or clock value."""


@dataclass(frozen=True)
class VelocityCommand:
    """A ROS-independent representation of all six ``Twist`` components."""

    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0

    def is_finite(self) -> bool:
        """Return whether every component is safe to forward."""

        try:
            return all(
                isfinite(value)
                for value in (
                    self.linear_x,
                    self.linear_y,
                    self.linear_z,
                    self.angular_x,
                    self.angular_y,
                    self.angular_z,
                )
            )
        except TypeError:
            return False


ZERO_VELOCITY = VelocityCommand()


class CmdVelGuard:
    """Keep the latest valid command and replace stale/invalid input with zero."""

    def __init__(self, command_timeout_s: float = 0.5) -> None:
        try:
            timeout = float(command_timeout_s)
        except (TypeError, ValueError) as exc:
            raise VelocityGuardError("command_timeout_s 必须是有限数值") from exc
        if isinstance(command_timeout_s, bool) or not isfinite(timeout) or timeout <= 0.0:
            raise VelocityGuardError("command_timeout_s 必须是大于 0 的有限数值")

        self._command_timeout_s = timeout
        self._last_command = ZERO_VELOCITY
        self._last_received_at_s = None  # type: Optional[float]

    @property
    def command_timeout_s(self) -> float:
        """Configured interval after which a command becomes unsafe."""

        return self._command_timeout_s

    def accept(self, command: VelocityCommand, received_at_s: float) -> bool:
        """Store a finite command, or invalidate the current command otherwise."""

        if not isinstance(command, VelocityCommand):
            raise TypeError("command 必须是 VelocityCommand")
        received_at = self._validate_time(received_at_s, "received_at_s")
        if not command.is_finite():
            self.reset()
            return False

        self._last_command = command
        self._last_received_at_s = received_at
        return True

    def safe_command(self, now_s: float) -> VelocityCommand:
        """Return the latest fresh command, or an all-zero fail-safe command."""

        now = self._validate_time(now_s, "now_s")
        if self._last_received_at_s is None:
            return ZERO_VELOCITY

        age_s = now - self._last_received_at_s
        if age_s < 0.0 or age_s >= self._command_timeout_s:
            # A backward clock jump is treated like a timeout. Clearing state keeps
            # an old command from becoming valid again if the clock later catches up.
            self.reset()
            return ZERO_VELOCITY
        return self._last_command

    def reset(self) -> None:
        """Immediately return the guard to its safe, no-command state."""

        self._last_command = ZERO_VELOCITY
        self._last_received_at_s = None

    @staticmethod
    def _validate_time(value: float, name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise VelocityGuardError("{} 必须是有限数值".format(name)) from exc
        if isinstance(value, bool) or not isfinite(parsed):
            raise VelocityGuardError("{} 必须是有限数值".format(name))
        return parsed
