"""Out-of-process desktop recovery if the UI dies; never handles audio or animation."""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

from .shell import LayoutSession, ShellDesktop, atomic_json


def main(args):
    """Watch the UI process and restore the journaled layout when it disappears."""
    journal = Path(args[0])
    nonce = args[1]
    parent = int(args[2])
    ready = journal.with_name(journal.stem + '.watchdog.json')
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x00100000, False, parent)
    if not handle:
        atomic_json(
            ready,
            {'session_id': nonce, 'ready': False, 'error': 'Cannot monitor UI process'},
        )
        raise SystemExit(2)
    atomic_json(ready, {'session_id': nonce, 'ready': True, 'pid': os.getpid()})
    try:
        while True:
            try:
                snapshot = json.loads(journal.read_text(encoding='utf-8'))
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.3)
                continue
            if snapshot.get('session_id') != nonce or not snapshot.get('active'):
                break
            state = kernel32.WaitForSingleObject(handle, 400)
            if state == 0:
                try:
                    desktop = ShellDesktop()
                    result = LayoutSession(desktop, journal).restore()
                    atomic_json(
                        journal.with_name(journal.stem + '.watchdog-recovered.json'),
                        {'session_id': nonce, **result},
                    )
                except Exception as exc:
                    atomic_json(
                        journal.with_name(journal.stem + '.watchdog-error.json'),
                        {'session_id': nonce, 'error': str(exc)},
                    )
                break
    finally:
        kernel32.CloseHandle(handle)


if __name__ == '__main__':
    main(sys.argv[1:])
