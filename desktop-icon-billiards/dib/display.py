"""Explicit DPI contexts and physical monitor layout for desktop artwork."""
from __future__ import annotations

import ctypes
from contextlib import contextmanager

import win32api


@contextmanager
def dpi_context(value):
    """Run the block under a specific thread DPI awareness context."""
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(value))
    try:
        yield
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))


def monitors():
    """Return a sorted tuple of device, monitor rect, work rect, DPI and primary flag."""
    result = []
    with dpi_context(-4):
        for handle, _, _ in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(handle)
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            hresult = ctypes.windll.shcore.GetDpiForMonitor(
                int(handle), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            )
            if hresult:
                raise OSError('Cannot read monitor DPI')
            result.append(
                (
                    info['Device'],
                    info['Monitor'],
                    info['Work'],
                    dpi_x.value,
                    bool(info['Flags'] & 1),
                )
            )
    return tuple(sorted(result))
