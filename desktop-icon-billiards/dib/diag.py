"""Best-effort diagnostics for support requests (``diag.log`` in the runtime directory).

Players report problems such as multi-monitor misplacement or clicks that do
nothing. This log records the facts needed to reproduce them (monitor layout,
DPI awareness of the Explorer windows, icon counts, what blocks the mouse). It
never raises: diagnostics must not break the game.
"""
from __future__ import annotations

import threading
import time

from .paths import runtime_directory

MAX_BYTES = 64 * 1024
_lock = threading.Lock()


def _path():
    return runtime_directory() / 'diag.log'


def start_session(version, lines=()):
    """Begin a fresh log (the previous one is kept as ``diag.old.log``)."""
    try:
        with _lock:
            path = _path()
            if path.exists():
                path.replace(path.with_name('diag.old.log'))
            header = [f'Desktop Icon Billiards {version}', time.strftime('%Y-%m-%d %H:%M:%S')]
            path.write_text('\n'.join([*header, *lines]) + '\n', encoding='utf-8')
    except Exception:
        pass


def log(*lines):
    """Append lines, stopping quietly once the file reaches its size cap."""
    try:
        with _lock:
            path = _path()
            if path.exists() and path.stat().st_size > MAX_BYTES:
                return
            with path.open('a', encoding='utf-8') as handle:
                handle.write('\n'.join(str(line) for line in lines) + '\n')
    except Exception:
        pass
