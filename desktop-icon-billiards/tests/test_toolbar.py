"""The compact toolbar and hotkeys must survive a withdrawn Tk window."""
import math
from types import SimpleNamespace

import tkinter as tk
import unittest

import win32con
import win32gui

from dib import config
from dib.hotkeys import Hotkeys
from dib.overlay import TablePointer
from dib.panel import MainPanel
from dib.shot import KEYBOARD_POWER, MOUSE_POWER, ShotKeys, ShotPower, ShotSettings
from dib.shot_panel import ShotSettingsDialog
from dib.table import BilliardsMotion


class TablePointerTests(unittest.TestCase):
    def test_holding_the_table_click_does_not_change_selected_power(self):
        game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)])
        game.charge = .27
        pointer = TablePointer()
        target = game.white.x + 200, game.white.y
        pointer.update(game, 0., *target, False, True)
        pointer.update(game, 1., *target, True, True)
        pointer.update(game, 4., *target, True, True)
        self.assertEqual(game.charge, .27)
        self.assertEqual(game.shots, 0)
        pointer.update(game, 5., *target, False, True)
        self.assertEqual(game.shots, 1)
        self.assertAlmostEqual(game.power, game.height * (.62 + 2.55 * .27) * 1.58)

    def test_a_slider_drag_released_over_the_table_cannot_shoot(self):
        game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)])
        pointer = TablePointer()
        target = game.white.x + 200, game.white.y
        pointer.update(game, 0., *target, False, False)
        pointer.update(game, 1., *target, True, False)
        pointer.update(game, 2., *target, True, True)
        pointer.update(game, 3., *target, False, True)
        self.assertEqual(game.shots, 0)

    def test_mouse_mode_charges_by_time_and_uses_the_release_power(self):
        game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)])
        pointer = TablePointer()
        target = game.white.x + 200, game.white.y
        pointer.update(game, 0., *target, False, True, mode=MOUSE_POWER)
        pointer.update(game, 1., *target, True, True, mode=MOUSE_POWER)
        pointer.update(game, 1.45, *target, True, True, mode=MOUSE_POWER)
        self.assertAlmostEqual(game.charge, .5)
        self.assertEqual(game.shots, 0)
        pointer.update(game, 1.63, *target, False, True, mode=MOUSE_POWER)
        self.assertAlmostEqual(game.charge, .7)
        self.assertEqual(game.shots, 1)

    def test_switching_mode_cancels_a_held_mouse_shot(self):
        game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)])
        pointer = TablePointer()
        target = game.white.x + 200, game.white.y
        pointer.update(game, 0., *target, False, True, mode=MOUSE_POWER)
        pointer.update(game, 1., *target, True, True, mode=MOUSE_POWER)
        pointer.update(game, 1.6, *target, True, True, mode=KEYBOARD_POWER, power=.28)
        pointer.update(game, 1.7, *target, False, True, mode=KEYBOARD_POWER, power=.28)
        self.assertEqual(game.shots, 0)
        self.assertAlmostEqual(game.charge, .28)

    def test_locked_jump_guide_changes_length_without_following_the_mouse(self):
        game = BilliardsMotion((0, 0, 1600, 1000), [(64, 64)] * 2, ShotSettings(elevation=55, tip_y=.60))
        for ball in game.icons:
            ball.y = game.white.y - 220
        pointer = TablePointer()
        x, y = game.white.x, game.white.y
        pointer.update(game, 1., x + 200, y, False, True, power=.60, toggle_lock=True)
        self.assertTrue(game.aim_locked)
        self.assertEqual(game.aim, (1., 0.))

        def jump_length():
            return sum(math.dist(a, b) for role, a, b in game.aim_guide() if role == 'airborne')

        short = jump_length()
        pointer.update(game, 2., x, y + 200, False, True, power=.90)
        self.assertGreater(jump_length(), short + 60)
        self.assertEqual(game.aim, (1., 0.))
        pointer.update(game, 3., x, y + 200, False, True, power=.90, toggle_lock=True)
        self.assertFalse(game.aim_locked)
        self.assertEqual(game.aim, (0., 1.))

    def test_held_space_toggles_once_and_strength_keys_repeat(self):
        keys = ShotKeys()
        self.assertEqual(keys.update(0., True, True, False, True), (1, True))
        self.assertEqual(keys.update(.15, True, True, False, True), (0, False))
        self.assertEqual(keys.update(.31, True, True, False, True), (2, False))
        self.assertEqual(keys.update(.40, True, False, False, False), (0, False))
        self.assertEqual(keys.update(.50, True, False, True, True), (-1, True))
        self.assertEqual(keys.update(.60, False, False, False, True), (0, False))
        self.assertEqual(keys.update(.70, True, False, False, True), (0, False))

    def test_keyboard_power_is_preserved_when_switching_modes(self):
        power = ShotPower(KEYBOARD_POWER, 99)
        self.assertEqual(power.adjust(2), (KEYBOARD_POWER, 100))
        power.toggle_mode()
        self.assertEqual(power.adjust(-1), (MOUSE_POWER, 100))
        power.toggle_mode()
        self.assertEqual(power.adjust(-1), (KEYBOARD_POWER, 99))


class ToolbarTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)

    def test_only_exit_hotkey_is_enabled(self):
        hotkeys = Hotkeys()
        self.addCleanup(hotkeys.close)
        self.assertNotIn(config.HIDE_HOTKEY_ID, hotkeys.registered)
        self.assertIn(config.HOTKEY_ID, hotkeys.registered)
        self.root.withdraw()
        for identifier in (config.HIDE_HOTKEY_ID, config.HOTKEY_ID):
            win32gui.PostMessage(hotkeys.hwnd, win32con.WM_HOTKEY, identifier, 0)
        self.root.after(100, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.root.state(), 'withdrawn')
        self.assertEqual(hotkeys.pending.get_nowait(), config.HOTKEY_ID)
        self.assertTrue(hotkeys.pending.empty())

    def test_all_actions_are_visible_in_one_borderless_row(self):
        calls = []
        names = ('restart', 'toggle_guide', 'toggle_rank', 'toggle_felt', 'shot_settings', 'show_avatar',
                 'check_updates', 'donate', 'quit', 'open_credit')
        callbacks = {name: lambda name=name: calls.append(name) for name in names}
        callbacks['set_power'] = lambda _: None
        callbacks['toggle_power_mode'] = lambda: calls.append('toggle_power_mode')
        panel = MainPanel(self.root, config.VERSION, callbacks, config.CREDIT)
        self.root.update()
        self.assertTrue(self.root.overrideredirect())
        self.assertEqual(set(panel.pills),
                         {'restart', 'guide', 'rank', 'felt', 'shot', 'avatar', 'update', 'donate', 'quit'})
        positions = [pill.winfo_rooty() for pill in panel.pills.values()]
        self.assertLessEqual(max(positions) - min(positions), 2)
        for pill in panel.pills.values():
            self.assertTrue(pill.winfo_ismapped())
            pill._release(SimpleNamespace(x=1, y=1))
        self.assertNotIn('hide', panel.pills)
        self.assertEqual(calls, list(names[:-1]))
        narrow_width = max(panel.readings.winfo_reqwidth(), panel.actions.winfo_reqwidth()) + 12
        panel.fit_width(narrow_width)
        self.assertLessEqual(self.root.winfo_reqwidth(), narrow_width)
        self.assertGreater(panel.actions.winfo_y(), panel.readings.winfo_y())
        self.assertTrue(panel.power_scale.winfo_ismapped() and panel.pills['quit'].winfo_ismapped())
        panel.power_mode_button._release(SimpleNamespace(x=1, y=1))
        self.assertEqual(calls[-1], 'toggle_power_mode')

    def test_mouse_drag_can_raise_then_lower_power(self):
        names = ('restart', 'toggle_guide', 'toggle_rank', 'toggle_felt', 'shot_settings', 'show_avatar',
                 'check_updates', 'donate', 'quit')
        callbacks = {name: lambda: None for name in names}
        selected = []
        callbacks['set_power'] = selected.append
        callbacks['toggle_power_mode'] = lambda: None
        panel = MainPanel(self.root, config.VERSION, callbacks, power=45)
        self.root.update()
        slider = panel.power_scale
        x, y = slider.coords(45)
        slider.event_generate('<ButtonPress-1>', x=x, y=y)
        slider.event_generate('<B1-Motion>', x=slider.coords(96)[0], y=y)
        self.root.update()
        self.assertGreaterEqual(selected[-1], 90)
        slider.event_generate('<B1-Motion>', x=slider.coords(23)[0], y=y)
        slider.event_generate('<ButtonRelease-1>', x=slider.coords(23)[0], y=y)
        self.root.update()
        self.assertLessEqual(selected[-1], 25)
        self.assertEqual(panel.power_readout.get(), f'{selected[-1]}%')
        previous = len(selected)
        panel.show_shot_controls(MOUSE_POWER, 57, True)
        self.root.update()
        self.assertEqual(len(selected), previous)
        self.assertEqual(panel.power_readout.get(), '57%')
        self.assertEqual(slider.cget('state'), 'disabled')
        self.assertEqual(panel.aim_status.cget('text'), '空格解锁')

    def test_shot_settings_sliders_and_drag_change_the_values(self):
        updates = []
        dialog = ShotSettingsDialog(self.root, ShotSettings(), updates.append)
        self.root.update()
        sliders = {str(widget.cget('variable')): widget
                   for widget in dialog.angle_view.master.winfo_children() if isinstance(widget, tk.Scale)}
        sliders[str(dialog.friction)].set(.93)
        sliders[str(dialog.elevation)].set(55)
        self.root.update()
        self.assertAlmostEqual(updates[-1].friction, .93)
        self.assertEqual(updates[-1].elevation, 55)
        center = dialog.BALL_CENTER
        drag = SimpleNamespace(x=center + 12, y=center - 5)
        results = []
        for sensitivity in (.5, 2.):
            dialog._center_tip()
            sliders[str(dialog.sensitivity)].set(sensitivity)
            dialog._select_tip(SimpleNamespace(x=center, y=center))
            dialog._drag_tip(drag)
            results.append(updates[-1])
        self.assertAlmostEqual(results[1].tip_x, 4 * results[0].tip_x)
        self.assertAlmostEqual(results[1].tip_y, 4 * results[0].tip_y)
        dialog._reset()
        self.assertEqual(updates[-1], ShotSettings())


if __name__ == '__main__':
    unittest.main()
