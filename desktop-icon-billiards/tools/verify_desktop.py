"""Maintainer smoke test: play on the real desktop and verify exact restoration.

This tool hides the real desktop icons for a few seconds while it drives a real
game from source. It never leaves the desktop hidden: the journal is restored in
a ``finally`` block, and the watchdog process covers a hard crash.

Run from the repository root:

    ..\\.venv\\Scripts\\python.exe tools\\verify_desktop.py
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

import win32api  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402
from PIL import ImageGrab  # noqa: E402

import dib.ui as ui  # noqa: E402
from dib.paths import runtime_directory  # noqa: E402
from dib.shell import LayoutSession, ShellDesktop  # noqa: E402
from dib.shot import KEYBOARD_POWER  # noqa: E402

ARTIFACTS = ROOT / 'build' / 'verify'
JOURNAL = runtime_directory() / 'layout.json'
RESULT = ARTIFACTS / 'source-smoke.json'
CLASS_NAME = 'DesktopIconBilliardsOverlay'


class VerificationError(RuntimeError):
    pass


def overlay_children(parent):
    found = []

    def visit(hwnd, _):
        if win32gui.GetClassName(hwnd) == CLASS_NAME:
            found.append(hwnd)
        return True

    win32gui.EnumChildWindows(parent, visit, None)
    return found


def screen_point(parent, x, y):
    return win32gui.ClientToScreen(parent, (round(x), round(y)))


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # Message boxes would block an unattended run; restore failures are reported in JSON.
    ui.messagebox = types.SimpleNamespace(
        showinfo=lambda *args, **kwargs: None,
        showerror=lambda *args, **kwargs: None,
        showwarning=lambda *args, **kwargs: None,
    )
    result = {'success': False, 'stages': [], 'errors': []}
    desktop = ShellDesktop()
    original = desktop.items()
    original_flags = desktop.get_flags()
    result['icon_count'] = len(original)
    app = None
    root = None
    try:
        if JOURNAL.exists() and json.loads(JOURNAL.read_text(encoding='utf-8')).get('active'):
            LayoutSession(desktop, JOURNAL).restore()
            result['stages'].append('recovered-stale-journal')

        from dib.instance import claim_instance_mutex

        handle = claim_instance_mutex()
        if handle is None:
            raise VerificationError('Another Desktop Icon Billiards instance is running')

        root = tk.Tk()
        app = ui.DesktopBilliardsApp(root, handle)

        def pump(seconds=0.02):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                root.update()
                time.sleep(0.008)

        def wait_for(predicate, timeout, message):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
                if predicate():
                    return
            raise VerificationError(f'timeout waiting for {message}')

        wait_for(lambda: app.runner is not None and app.runner.shown.is_set(), 30, 'overlay shown')
        result['stages'].append('overlay-shown')
        overlay = app.runner.overlay
        table = overlay.table

        if win32gui.IsWindowVisible(overlay.listview):
            raise VerificationError('Explorer icon list view is still visible')
        journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
        if not journal.get('active'):
            raise VerificationError('Layout journal is not active')
        result['stages'].append('icons-hidden-journal-active')

        wait_for(lambda: overlay.transition is None, 6, 'rack intro to finish')
        pump(0.4)
        result['stages'].append('rack-intro-finished')
        if not win32gui.IsWindowVisible(overlay.table_windows['rail']):
            raise VerificationError('Table rail window is not visible')
        if not win32gui.IsWindowVisible(overlay.table_windows['white']):
            raise VerificationError('White ball window is not visible')
        if win32gui.IsWindowVisible(overlay.listview):
            raise VerificationError('Explorer icon list view became visible during play')
        result['table_windows'] = sorted(overlay.table_windows)

        def table_bbox():
            left, top, right, bottom = overlay.primary_bounds
            x, y = win32gui.ClientToScreen(overlay.parent, (left, top))
            return (x, y, x + right - left, y + bottom - top)

        ImageGrab.grab(bbox=table_bbox()).save(ARTIFACTS / 'table.png')
        window = (root.winfo_rootx(), root.winfo_rooty(),
                  root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height())
        ImageGrab.grab(bbox=window).save(ARTIFACTS / 'window.png')
        result['stages'].append('screenshots')

        # Raise and lower the manual power before clicking the rack.
        # Click on the right side of the table: the DSH GUI window covers the centre, and a
        # click over a normal window would be ignored by the desktop hit test.
        white = table.white
        initial_white = white.x, white.y
        if app.shot_power.selection()[0] != KEYBOARD_POWER:
            app.toggle_power_mode()
        app.panel.power_scale.set(82)
        wait_for(lambda: table.charge == .82, 3, 'high slider power')
        app.panel.power_scale.set(58)
        wait_for(lambda: table.charge == .58, 3, 'reduced slider power')
        aim = screen_point(overlay.parent, table.bounds[2] - 80, white.y)
        win32api.SetCursorPos(aim)
        pump(0.2)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        pump(0.45)
        power = table.charge
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        pump(0.1)
        if power != .58:
            raise VerificationError('The mouse changed the selected power')
        result['power_observed'] = power
        wait_for(lambda: table.state in ('rolling', 'return_white', 'ball_in_hand', 'finished', 'ready')
                 and not table.break_shot, 4, 'shot to be taken')
        moved_white = abs(table.white.x - initial_white[0]) + abs(table.white.y - initial_white[1])
        wait_for(lambda: table.state in ('ready', 'finished'), 8, 'balls to settle')
        moved_icons = sum(1 for body, (x, y) in zip(table.icons, table.rack)
                          if abs(body.x - x) + abs(body.y - y) > 1)
        if moved_icons == 0 and moved_white < 1:
            raise VerificationError('The shot did not move any ball')
        result['shot'] = {'moved_icons': moved_icons, 'white_shift': round(moved_white, 1)}
        result['stages'].append('manual-shot')
        ImageGrab.grab(bbox=table_bbox()).save(ARTIFACTS / 'table-after-shot.png')

        app.restart()
        wait_for(lambda: table.state == 'ready' and not table.sunk, 5, 'restart to rebuild the rack')
        result['stages'].append('restart')

        result['overlay_windows_before_close'] = len(overlay_children(overlay.parent))
        parent = overlay.parent
        listview = overlay.listview
        app.close()
        app = None
        root = None
        result['stages'].append('closed')

        if not win32gui.IsWindowVisible(listview):
            raise VerificationError('Explorer icon list view was not shown again')
        if overlay_children(parent):
            raise VerificationError('Overlay child windows survived the shutdown')
        if desktop.items() != original:
            raise VerificationError('Desktop icon layout was not restored exactly')
        if desktop.get_flags() != original_flags:
            raise VerificationError('Desktop arrange flags were not restored')
        if JOURNAL.exists() and json.loads(JOURNAL.read_text(encoding='utf-8')).get('active'):
            raise VerificationError('Layout journal is still active after shutdown')
        result['stages'].append('exact-restore')
        result['success'] = True
    except Exception as exc:
        result['errors'].append(f'{type(exc).__name__}: {exc}')
        result['traceback'] = traceback.format_exc()
        if app is not None:
            try:
                app.close()
            except Exception as exc:
                result['errors'].append(f'close failed: {exc}')
        elif root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    finally:
        # Last-resort safety net: never leave the desktop hidden or rearranged.
        try:
            if JOURNAL.exists() and json.loads(JOURNAL.read_text(encoding='utf-8')).get('active'):
                LayoutSession(ShellDesktop(), JOURNAL).restore()
                result['stages'].append('safety-restore')
        except Exception as exc:
            result['errors'].append(f'safety restore failed: {exc}')
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['success']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
