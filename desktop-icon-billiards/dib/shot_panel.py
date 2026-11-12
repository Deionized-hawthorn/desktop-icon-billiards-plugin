"""The live settings window for the cloth and the cue."""
import math
import tkinter as tk
from tkinter import ttk

from .panel import ACCENT, BG, CARD, FONT, MUTED, NUMBERS, TEXT, place_below_toolbar
from .shot import FRICTION_RANGE, MAX_ELEVATION, MAX_TIP_OFFSET, SENSITIVITY_RANGE, ShotSettings, limit_tip


class ShotSettingsDialog:
    BALL_CENTER = 67
    BALL_RADIUS = 52

    def __init__(self, root, settings, on_change):
        self.window = window = tk.Toplevel(root)
        window.title('击球设置')
        window.transient(root)
        window.configure(bg=BG)
        window.resizable(False, False)
        window.bind('<Escape>', lambda _: window.destroy())
        self.on_change = on_change
        self.tip = settings.tip_x, settings.tip_y
        self.drag_at = None
        self.friction = tk.DoubleVar(window, value=settings.friction)
        self.sensitivity = tk.DoubleVar(window, value=settings.tip_sensitivity)
        self.elevation = tk.DoubleVar(window, value=settings.elevation)

        body = tk.Frame(window, bg=BG, padx=16, pady=14)
        body.pack(fill='both', expand=True)
        ball_box = tk.Frame(body, bg=CARD, padx=14, pady=12)
        ball_box.grid(row=0, column=0, sticky='ns')
        tk.Label(ball_box, text='母球加塞位置', bg=CARD, fg=TEXT, font=(FONT, 10, 'bold')).pack()
        self.ball = tk.Canvas(ball_box, width=134, height=134, bg=CARD, bd=0, highlightthickness=0,
                              cursor='crosshair', takefocus=True)
        self.ball.pack(pady=(4, 0))
        center, radius = self.BALL_CENTER, self.BALL_RADIUS
        self.ball.create_oval(center - radius, center - radius, center + radius, center + radius,
                             fill='#f3f9f7', outline='#a6bdb8', width=2)
        edge = radius * MAX_TIP_OFFSET
        self.ball.create_oval(center - edge, center - edge, center + edge, center + edge,
                             outline='#b1c5bf', dash=(3, 3))
        self.ball.create_line(center - edge, center, center + edge, center, fill='#d1dfda')
        self.ball.create_line(center, center - edge, center, center + edge, fill='#d1dfda')
        self.dot = self.ball.create_oval(0, 0, 0, 0, fill='#176450', outline='#ffffff', width=2)
        self.ball.bind('<ButtonPress-1>', self._select_tip)
        self.ball.bind('<B1-Motion>', self._drag_tip)
        self.ball.bind('<KeyPress>', self._nudge_tip)
        for text in ('点击定位，拖动微调', '上高杆 · 下低杆 · 左右侧塞'):
            tk.Label(ball_box, text=text, bg=CARD, fg=MUTED, font=(FONT, 8)).pack()
        ttk.Button(ball_box, text='击打点居中', style='Table.TButton', command=self._center_tip).pack(pady=(8, 0))

        controls = tk.Frame(body, bg=BG)
        controls.grid(row=0, column=1, padx=(18, 0), sticky='nsew')
        self.friction_readout = self._slider(controls, '台面摩擦系数', self.friction, FRICTION_RANGE, .01)
        self.sensitivity_readout = self._slider(controls, '击打点灵敏度', self.sensitivity, SENSITIVITY_RANGE, .01)
        self.elevation_readout = self._slider(controls, '杆尾仰角', self.elevation, (0, MAX_ELEVATION), 1)
        self.angle_view = tk.Canvas(controls, width=218, height=72, bg=CARD, bd=0, highlightthickness=0)
        self.angle_view.pack(fill='x', pady=(2, 0))
        self.angle_view.create_line(18, 59, 200, 59, fill='#42665b', width=2)
        self.angle_view.create_oval(154, 40, 172, 58, fill='#f3f9f7', outline='#a6bdb8')
        self.cue_line = self.angle_view.create_line(0, 0, 0, 0, fill='#efc187', width=4, capstyle='round')

        actions = tk.Frame(body, bg=BG)
        actions.grid(row=1, column=0, columnspan=2, pady=(12, 0), sticky='ew')
        ttk.Button(actions, text='恢复默认', style='Table.TButton', command=self._reset).pack(side='left')
        ttk.Button(actions, text='完成', style='Table.TButton', command=window.destroy).pack(side='right')
        self._changed()
        place_below_toolbar(window, root)

    def _slider(self, parent, title, variable, limits, resolution):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x')
        tk.Label(row, text=title, bg=BG, fg=TEXT, font=(FONT, 10)).pack(side='left')
        readout = tk.Label(row, bg=BG, fg=ACCENT, font=(NUMBERS, 10), width=7, anchor='e')
        readout.pack(side='right')
        slider = tk.Scale(parent, from_=limits[0], to=limits[1], resolution=resolution, variable=variable,
                          orient='horizontal', showvalue=False, length=218, sliderlength=18, bd=0,
                          bg=BG, activebackground=ACCENT, troughcolor='#31544a', highlightthickness=0,
                          command=self._changed)
        slider.pack(fill='x', pady=(2, 8))
        return readout

    def _dot_position(self):
        c, r = self.BALL_CENTER, self.BALL_RADIUS
        return c + r * self.tip[0], c - r * self.tip[1]

    def _select_tip(self, event):
        self.ball.focus_set()
        self.drag_at = event.x, event.y
        if math.dist(self.drag_at, self._dot_position()) > 8:
            c, r = self.BALL_CENTER, self.BALL_RADIUS
            self.tip = limit_tip((event.x - c) / r, (c - event.y) / r)
            self._changed()

    def _drag_tip(self, event):
        if self.drag_at is None:
            return
        x, y = self.drag_at
        self.drag_at = event.x, event.y
        self._move_tip((event.x - x) / self.BALL_RADIUS, (y - event.y) / self.BALL_RADIUS)

    def _move_tip(self, dx, dy):
        gain = self.sensitivity.get()
        self.tip = limit_tip(self.tip[0] + dx * gain, self.tip[1] + dy * gain)
        self._changed()

    def _nudge_tip(self, event):
        direction = {'Left': (-1, 0), 'Right': (1, 0), 'Up': (0, 1), 'Down': (0, -1)}.get(event.keysym)
        if direction is not None:
            self._move_tip(direction[0] * .045, direction[1] * .045)
            return 'break'

    def _center_tip(self):
        self.tip = 0., 0.
        self.drag_at = None
        self._changed()

    def _reset(self):
        defaults = ShotSettings()
        self.friction.set(defaults.friction)
        self.sensitivity.set(defaults.tip_sensitivity)
        self.elevation.set(defaults.elevation)
        self._center_tip()

    def _changed(self, _value=None):
        settings = ShotSettings(self.friction.get(), self.sensitivity.get(), *self.tip, self.elevation.get())
        self.friction_readout.configure(text=f'{settings.friction:.2f}')
        self.sensitivity_readout.configure(text=f'{settings.tip_sensitivity:.2f}×')
        self.elevation_readout.configure(text=f'{settings.elevation:.0f}°')
        x, y = self._dot_position()
        self.ball.coords(self.dot, x - 6, y - 6, x + 6, y + 6)
        angle = math.radians(settings.elevation)
        self.angle_view.coords(self.cue_line, 155 - 48 * math.cos(angle), 49 - 48 * math.sin(angle), 155, 49)
        self.on_change(settings)
