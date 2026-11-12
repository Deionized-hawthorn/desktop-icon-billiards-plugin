"""A message-only window receives the global exit hotkey through Tk."""
from __future__ import annotations

import ctypes
import queue

import win32api
import win32con
import win32gui

from . import config


class Hotkeys:
    def __init__(self):
        self.pending = queue.SimpleQueue()
        self.registered = set()
        self.instance = win32api.GetModuleHandle(None)
        self.class_name = f'DesktopIconBilliardsHotkeys-{id(self)}'
        window_class = win32gui.WNDCLASS()
        window_class.hInstance = self.instance
        window_class.lpszClassName = self.class_name
        window_class.lpfnWndProc = self._message
        win32gui.RegisterClass(window_class)
        # HWND_MESSAGE: invisible, but dispatched by Tk's native message loop.
        self.hwnd = win32gui.CreateWindow(self.class_name, '', 0, 0, 0, 0, 0, -3, 0, self.instance, None)
        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        for identifier, key in ((config.HOTKEY_ID, config.HOTKEY_VK),):
            if user32.RegisterHotKey(self.hwnd, identifier, config.HOTKEY_MODIFIERS | 0x4000, key):
                self.registered.add(identifier)

    def _message(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_HOTKEY and wparam in self.registered:
            self.pending.put(wparam)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def close(self):
        for identifier in self.registered:
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, identifier)
        self.registered.clear()
        win32gui.DestroyWindow(self.hwnd)
        win32gui.UnregisterClass(self.class_name, self.instance)
