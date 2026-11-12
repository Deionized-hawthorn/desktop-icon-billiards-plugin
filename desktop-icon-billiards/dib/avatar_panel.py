"""Photo selection, face crop, and the animated character preview."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .avatar import DANCE_FPS, cartoon_head, crop_square, dance_frame, dance_pose, open_photo
from .panel import ACCENT, BG, CARD, FONT, MUTED, TEXT, place_below_toolbar

CROP_VIEW = (230, 222)
PREVIEW_VIEW = (182, 222)


class AvatarDialog:
    def __init__(self, root, head, on_save):
        self.window = window = tk.Toplevel(root)
        window.title('照片角色')
        window.transient(root)
        window.configure(bg=BG)
        window.resizable(False, False)
        window.bind('<Escape>', lambda _: window.destroy())
        window.bind('<Destroy>', self._cancel_jobs)
        self.on_save = on_save
        self.photo = None
        self.preview_head = head
        self.preview_job = self.crop_job = None
        self.preview_pose = None
        self.began = time.monotonic()

        body = tk.Frame(window, bg=BG, padx=15, pady=13)
        body.pack()
        for column, title in enumerate(('脸部取景', '舞蹈预览')):
            tk.Label(body, text=title, bg=BG, fg=TEXT, font=(FONT, 10, 'bold')).grid(
                row=0, column=column, sticky='w', pady=(0, 6))

        self.crop_view = tk.Canvas(body, width=CROP_VIEW[0], height=CROP_VIEW[1], bg=CARD,
                                   bd=0, highlightthickness=0, cursor='crosshair')
        self.crop_view.grid(row=1, column=0)
        self.photo_item = self.crop_view.create_image(*[length / 2 for length in CROP_VIEW])
        self.crop_empty = self.crop_view.create_text(*[length / 2 for length in CROP_VIEW],
                                                      text='选择一张人物照片', fill=MUTED, font=(FONT, 9))
        self.crop_border = self.crop_view.create_oval(0, 0, 0, 0, outline=ACCENT, width=2, state='hidden')
        self.crop_view.bind('<ButtonPress-1>', self._move_crop)
        self.crop_view.bind('<B1-Motion>', self._move_crop)
        self.preview = tk.Canvas(body, width=PREVIEW_VIEW[0], height=PREVIEW_VIEW[1], bg=CARD,
                                 bd=0, highlightthickness=0)
        self.preview.grid(row=1, column=1, padx=(12, 0))
        self.preview_item = self.preview.create_image(*[length / 2 for length in PREVIEW_VIEW])
        self.preview_empty = self.preview.create_text(*[length / 2 for length in PREVIEW_VIEW],
                                                       text='选好脸部后预览', fill=MUTED, font=(FONT, 9))

        adjustment = tk.Frame(body, bg=BG)
        adjustment.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        tk.Label(adjustment, text='取景范围', bg=BG, fg=TEXT, font=(FONT, 9)).pack(side='left')
        self.crop_scale = tk.Scale(adjustment, from_=35, to=100, resolution=1, orient='horizontal',
                                   length=118, showvalue=False, bg=BG, troughcolor='#31544a',
                                   activebackground=ACCENT, highlightthickness=0, bd=0)
        self.crop_scale.set(80)
        self.crop_scale.configure(state='disabled', command=self._update_crop)
        self.crop_scale.pack(side='left', padx=5)
        tk.Label(adjustment, text='拖动选框对准脸部', bg=BG, fg=MUTED, font=(FONT, 8)).pack(side='right')

        actions = tk.Frame(body, bg=BG)
        actions.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(12, 0))
        ttk.Button(actions, text='选择照片', style='Table.TButton', command=self._choose_photo).pack(side='left')
        remove = ttk.Button(actions, text='移除角色', style='Table.TButton', command=lambda: self._save(None))
        remove.pack(side='left', padx=(8, 0))
        if head is None:
            remove.state(['disabled'])
        self.save_button = ttk.Button(actions, text='保存角色', style='Table.TButton', command=self._save_crop)
        self.save_button.pack(side='right')
        self.save_button.state(['disabled'])
        if head is not None:
            self._animate()
        place_below_toolbar(window, root)

    def _choose_photo(self):
        path = filedialog.askopenfilename(parent=self.window, title='选择人物照片',
                                          filetypes=[('图片', '*.jpg *.jpeg *.png *.webp *.bmp')])
        if path:
            try:
                self._set_photo(open_photo(path))
            except (ValueError, Image.DecompressionBombError):
                messagebox.showerror('无法打开照片', '照片尺寸过大，请缩小后重新选择。', parent=self.window)
            except OSError:
                messagebox.showerror('无法打开照片', '请选择可读取的 JPG、PNG、WebP 或 BMP 图片。',
                                     parent=self.window)

    def _set_photo(self, photo):
        self.photo = photo
        self.center = photo.width / 2, photo.height / 2
        thumb = photo.copy()
        thumb.thumbnail(CROP_VIEW, Image.Resampling.LANCZOS)
        self.view_scale = thumb.width / photo.width, thumb.height / photo.height
        self.view_origin = (CROP_VIEW[0] - thumb.width) / 2, (CROP_VIEW[1] - thumb.height) / 2
        self.thumb = ImageTk.PhotoImage(thumb, master=self.window)
        self.crop_view.itemconfigure(self.photo_item, image=self.thumb)
        self.crop_view.itemconfigure(self.crop_empty, state='hidden')
        self.crop_scale.configure(state='normal')
        self.crop_view.itemconfigure(self.crop_border, state='normal')
        self._update_crop()
        self.save_button.state(['!disabled'])

    def _move_crop(self, event):
        if self.photo is not None:
            ox, oy = self.view_origin
            sx, sy = self.view_scale
            self.center = (event.x - ox) / sx, (event.y - oy) / sy
            self._update_crop()

    def _update_crop(self, _value=None):
        if self.photo is None:
            return
        self.crop = crop_square(self.photo.size, self.center, self.crop_scale.get() / 100)
        left, top, right, bottom = self.crop
        ox, oy = self.view_origin
        sx, sy = self.view_scale
        self.crop_view.coords(self.crop_border, ox + left * sx, oy + top * sy, ox + right * sx, oy + bottom * sy)
        if self.crop_job is not None:
            self.window.after_cancel(self.crop_job)
        self.crop_job = self.window.after(45, self._refresh_head)

    def _refresh_head(self):
        self.crop_job = None
        self.preview_head = cartoon_head(self.photo, self.crop)
        self.preview_pose = None
        if self.preview_job is None:
            self._animate()

    def _animate(self):
        pose = dance_pose(time.monotonic() - self.began)
        if pose != self.preview_pose:
            frame = dance_frame(self.preview_head, pose)
            self.preview_image = ImageTk.PhotoImage(frame, master=self.window)
            self.preview.itemconfigure(self.preview_item, image=self.preview_image)
            self.preview.itemconfigure(self.preview_empty, state='hidden')
            self.preview_pose = pose
        self.preview_job = self.window.after(round(1000 / DANCE_FPS), self._animate)

    def _save_crop(self):
        self._save(cartoon_head(self.photo, self.crop))

    def _save(self, head):
        try:
            self.on_save(head)
        except OSError:
            messagebox.showerror('保存失败', '无法写入角色设置，请稍后重试。', parent=self.window)
        else:
            self.window.destroy()

    def _cancel_jobs(self, event):
        if event.widget is self.window:
            for job in (self.crop_job, self.preview_job):
                if job is not None:
                    self.window.after_cancel(job)
