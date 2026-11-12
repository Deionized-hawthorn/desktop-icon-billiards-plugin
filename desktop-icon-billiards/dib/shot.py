"""Player-adjustable cloth and cue settings."""
import math
from dataclasses import dataclass
from threading import Lock

DEFAULT_FRICTION = .45
DEFAULT_POWER_PERCENT = 45
KEYBOARD_POWER = 'keyboard'
MOUSE_POWER = 'mouse'
FRICTION_RANGE = (.15, 1.50)
SENSITIVITY_RANGE = (.25, 2.50)
MAX_TIP_OFFSET = .82
MAX_ELEVATION = 75


def limit_tip(x, y):
    """Constrain the contact point to a circle inside the edge of the cue ball."""
    distance = math.hypot(x, y)
    if distance > MAX_TIP_OFFSET:
        scale = MAX_TIP_OFFSET / distance
        return x * scale, y * scale
    return x, y


def _number(value, default, low, high):
    if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
        return default
    return float(max(low, min(high, value)))


def power_percent(value):
    return round(_number(value, DEFAULT_POWER_PERCENT, 0, 100))


class ShotPower:
    """Share the power selection between the toolbar and the animation thread."""

    def __init__(self, mode=None, percent=None):
        self._lock = Lock()
        self._mode = MOUSE_POWER if mode == MOUSE_POWER else KEYBOARD_POWER
        self._percent = power_percent(percent)

    def selection(self):
        with self._lock:
            return self._mode, self._percent

    def set_percent(self, percent):
        with self._lock:
            if self._mode == KEYBOARD_POWER:
                self._percent = power_percent(percent)

    def adjust(self, delta):
        with self._lock:
            if self._mode == KEYBOARD_POWER and delta:
                self._percent = max(0, min(100, self._percent + delta))
            return self._mode, self._percent

    def toggle_mode(self):
        with self._lock:
            self._mode = MOUSE_POWER if self._mode == KEYBOARD_POWER else KEYBOARD_POWER


class ShotKeys:
    """Repeat a held strength key and toggle aim only on the spacebar's down edge."""

    def __init__(self):
        self.direction = 0
        self.lock_down = False
        self.repeat_at = None

    def update(self, now, active, increase, decrease, lock):
        direction = int(increase) - int(decrease)
        toggle = active and lock and not self.lock_down
        delta = 0
        if not active or not direction:
            self.repeat_at = None
        elif direction != self.direction:
            delta = direction
            self.repeat_at = now + .28
        elif self.repeat_at is not None and now >= self.repeat_at:
            delta = direction * 2
            self.repeat_at = now + .065
        self.direction = direction
        self.lock_down = lock
        return delta, toggle


@dataclass(frozen=True)
class ShotSettings:
    friction: float = DEFAULT_FRICTION
    tip_sensitivity: float = 1.
    tip_x: float = 0.  # right, as seen from behind the cue
    tip_y: float = 0.  # up
    elevation: float = 0.

    @property
    def has_spin_or_elevation(self):
        return bool(self.tip_x or self.tip_y or self.elevation)

    @classmethod
    def from_data(cls, data):
        if not isinstance(data, dict):
            return cls()
        x = _number(data.get('tip_x'), 0., -MAX_TIP_OFFSET, MAX_TIP_OFFSET)
        y = _number(data.get('tip_y'), 0., -MAX_TIP_OFFSET, MAX_TIP_OFFSET)
        x, y = limit_tip(x, y)
        return cls(
            friction=_number(data.get('friction'), DEFAULT_FRICTION, *FRICTION_RANGE),
            tip_sensitivity=_number(data.get('tip_sensitivity'), 1., *SENSITIVITY_RANGE),
            tip_x=x,
            tip_y=y,
            elevation=_number(data.get('elevation'), 0., 0., MAX_ELEVATION),
        )
