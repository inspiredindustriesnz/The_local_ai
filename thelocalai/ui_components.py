from __future__ import annotations

import random
import time
from typing import Optional

import tkinter as tk
from tkinter import ttk

from .config import THEME
from .runtime import random_matrix_speed


class ChatLog(tk.Frame):
    def __init__(self, master: tk.Widget):
        super().__init__(master, bg=THEME["bg"])

        self.text = tk.Text(
            self,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg=THEME["bg"],
            fg=THEME["green"],
            insertbackground=THEME["green"],
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["green"],
            padx=10,
            pady=10,
            undo=False,
        )
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.vbar.set)

        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.text.config(state=tk.DISABLED)

        self.text.tag_configure("system", foreground=THEME["green_dim"], font=("Consolas", 10, "italic"))
        self.text.tag_configure("error", foreground=THEME["error"], font=("Consolas", 11, "bold"))
        self.text.tag_configure("user", foreground=THEME["green"], font=("Consolas", 11, "bold"))
        self.text.tag_configure("assistant", foreground=THEME["green"], font=("Consolas", 11))

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy", command=self.copy_selection)
        self.menu.add_command(label="Copy All", command=self.copy_all)

        self.text.bind("<Button-3>", self._popup_menu)
        self.text.bind("<Button-2>", self._popup_menu)
        self.text.bind("<Control-a>", self._select_all)

    def _popup_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.menu.grab_release()
            except Exception:
                pass

    def _select_all(self, _event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)

    def write(self, text: str, kind: str = "assistant"):
        text = (text or "")
        if not text.endswith("\n"):
            text += "\n"
        if not text.endswith("\n\n"):
            text += "\n"

        tag = kind if kind in {"system", "error", "user", "assistant"} else "assistant"

        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, text, tag)
        self.text.config(state=tk.DISABLED)
        self.text.see(tk.END)

    def copy_selection(self):
        try:
            sel = self.text.get("sel.first", "sel.last")
        except Exception:
            sel = ""
        if not sel:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(sel)
        except Exception:
            pass

    def copy_all(self):
        try:
            all_text = self.text.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(all_text)
        except Exception:
            pass


class MatrixRain:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.running = False

        self.font = ("Consolas", 13, "bold")
        self.chars = (
            "アイウエオカキクケコサシスセソタチツテトナニヌネノ"
            "ハヒフヘホマミムメモヤユヨラリルレロワ"
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )

        self.col_w = 12
        self.step_y = 18
        self.trail_len = 20
        self.max_cols = 160

        self.base_fps = 18
        self.fps = self.base_fps
        self._after_id: Optional[str] = None
        self._frame = 0

        self.columns_x: list[int] = []
        self.drop_y: list[int] = []
        self.speed: list[int] = []
        self.speed_drift: list[int] = []
        self.item_ids: list[list[int]] = []

        self._last_tick = 0.0
        self.last_dt_ms = 0.0
        self.avg_dt_ms = 0.0
        self.frames = 0

        self._skip_mod = 2

    def reset(self):
        w = max(1, int(self.canvas.winfo_width()))
        h = max(1, int(self.canvas.winfo_height()))
        self.canvas.delete("matrix")

        self._frame = 0
        self.frames = 0
        self._last_tick = time.perf_counter()
        self.last_dt_ms = 0.0
        self.avg_dt_ms = 0.0

        if w < self.col_w * 10 or h < 120:
            self.columns_x = []
            self.drop_y = []
            self.speed = []
            self.speed_drift = []
            self.item_ids = []
            return

        usable_w = int(w * 0.95)
        ncols = max(1, usable_w // self.col_w)
        ncols = min(ncols, self.max_cols)

        band_w = ncols * self.col_w
        start_x = max(0, (w - band_w) // 2)

        self.columns_x = [start_x + i * self.col_w + (self.col_w // 2) for i in range(ncols)]
        self.drop_y = [random.randint(-h, 0) for _ in range(ncols)]

        self.speed = [random_matrix_speed() for _ in range(ncols)]
        self.speed_drift = [random.choice([-2, -1, 0, 0, 1, 2]) for _ in range(ncols)]
        self.item_ids = []

        for i in range(ncols):
            col_items: list[int] = []
            x = self.columns_x[i]
            base_y = self.drop_y[i]
            for t in range(self.trail_len):
                y = base_y - t * self.step_y
                fill = (
                    THEME["green"]
                    if t == 0
                    else (THEME["green_dim"] if t < (self.trail_len * 0.60) else THEME["green_dim2"])
                )
                item = self.canvas.create_text(
                    x,
                    y,
                    text=random.choice(self.chars),
                    fill=fill,
                    font=self.font,
                    tags=("matrix",),
                )
                col_items.append(item)
            self.item_ids.append(col_items)

    def set_low_power(self, enabled: bool):
        self.fps = 12 if enabled else self.base_fps

    def start(self):
        if self.running:
            return
        self.running = True
        self.reset()
        self._tick()

    def stop(self):
        self.running = False
        if self._after_id:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = None
        self.canvas.delete("matrix")

    def _adapt(self):
        if self.avg_dt_ms > 70:
            self._skip_mod = min(4, self._skip_mod + 1)
            self.fps = max(12, self.fps - 1)
        elif self.avg_dt_ms < 38:
            self._skip_mod = max(2, self._skip_mod - 1)
            self.fps = min(self.base_fps, self.fps + 1)

    def _tick(self):
        if not self.running:
            return

        now = time.perf_counter()
        dt = (now - self._last_tick) * 1000.0
        self._last_tick = now
        self.last_dt_ms = dt
        self.avg_dt_ms = (self.avg_dt_ms * 0.90) + (dt * 0.10) if self.frames > 0 else dt
        self.frames += 1

        self._adapt()

        h = max(1, int(self.canvas.winfo_height()))
        if not self.columns_x:
            self._after_id = self.canvas.after(int(1000 / max(1, self.fps)), self._tick)
            return

        mod = max(1, self._skip_mod)
        slice_idx = self._frame % mod

        for i, x in enumerate(self.columns_x):
            if (i % mod) != slice_idx:
                continue

            if random.random() < 0.04:
                self.speed[i] = max(8, min(50, self.speed[i] + self.speed_drift[i]))
                if random.random() < 0.10:
                    self.speed_drift[i] = random.choice([-2, -1, 0, 0, 1, 2])

            head_y = self.drop_y[i] + self.speed[i]
            if head_y > h + random.randint(0, 240):
                head_y = random.randint(-h // 2, 0)
                self.speed[i] = random_matrix_speed()

            self.drop_y[i] = head_y

            col_items = self.item_ids[i]
            for t, item in enumerate(col_items):
                y = head_y - t * self.step_y
                self.canvas.coords(item, x, y)
                if t == 0 or t < 7:
                    self.canvas.itemconfig(item, text=random.choice(self.chars))
                else:
                    if random.random() < 0.14:
                        self.canvas.itemconfig(item, text=random.choice(self.chars))

        self._frame += 1
        self._after_id = self.canvas.after(int(1000 / max(1, self.fps)), self._tick)
