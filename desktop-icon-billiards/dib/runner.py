"""Animation thread that drives the layered windows outside Tk's event loop."""
from __future__ import annotations

import ctypes
import threading
import time

import win32gui

FRAME_SECONDS = 1 / 60


class BilliardsRunner:
    """Own the overlay windows, tablet input polling and repaint loop."""

    def __init__(self, overlay):
        self.overlay = overlay
        self.prepared = threading.Event()
        self.shown = threading.Event()
        self.stopping = threading.Event()
        self.error = None
        self.show_request = None
        self.thread = threading.Thread(target=self._run, name='DesktopIconBilliards', daemon=True)

    def start(self):
        self.thread.start()

    def request_show(self, snapshot, journal):
        self.show_request = (snapshot, journal)

    def stop(self):
        self.stopping.set()
        self.thread.join(5)
        if self.thread.is_alive():
            raise RuntimeError('动画线程尚未退出，请稍后再次停止。')

    def _run(self):
        try:
            # Tk may change the UI thread DPI context; match native desktop coordinates.
            ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            self.overlay.prepare()
            self.prepared.set()
            last = time.perf_counter()
            while not self.stopping.is_set():
                now = time.perf_counter()
                if self.show_request and not self.shown.is_set():
                    self.overlay.show(*self.show_request)
                    self.shown.set()
                    last = now
                if self.shown.is_set():
                    self.overlay.draw(now, min(0.05, now - last))
                last = now
                win32gui.PumpWaitingMessages()
                self.stopping.wait(max(0.001, FRAME_SECONDS - (time.perf_counter() - now)))
        except Exception as exc:  # surfaced to the Tk thread through .error
            self.error = exc
        finally:
            try:
                self.overlay.close()
            except Exception as exc:
                if self.error is None:
                    self.error = exc
