from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .config import APP_TITLE, DEFAULT_MODEL, THEME
from .ui_components import ChatLog, MatrixRain


def configure_ttk() -> None:
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=THEME["bg"])
    style.configure("TLabel", background=THEME["bg"], foreground=THEME["green"])
    style.configure("TButton", background=THEME["panel_bg"], foreground=THEME["green"])
    style.configure("TCheckbutton", background=THEME["bg"], foreground=THEME["green"])
    style.configure("TCombobox", fieldbackground=THEME["panel_bg"], background=THEME["panel_bg"], foreground=THEME["green"])
    style.configure("Accent.TButton", background=THEME["green"], foreground="black")
    style.map("Accent.TButton", background=[("active", "#33ff88")])


def build_ui(app) -> None:
    header = tk.Frame(app.root, bg=THEME["panel_bg"])
    header.pack(fill=tk.X)

    tk.Label(header, text=APP_TITLE, bg=THEME["panel_bg"], fg=THEME["green"], font=("Consolas", 16, "bold")).pack(
        side=tk.LEFT, padx=12, pady=10
    )

    app.dev_state = tk.StringVar(value="STOCK")
    tk.Label(
        header,
        textvariable=app.dev_state,
        bg=THEME["panel_bg"],
        fg=THEME["green_dim"],
        font=("Consolas", 10, "bold"),
    ).pack(side=tk.LEFT, padx=(10, 0))

    ttk.Button(header, text="Unlock Dev", command=app.unlock_dev_mode).pack(side=tk.LEFT, padx=(10, 0))
    ttk.Button(header, text="Lock", command=app.lock_dev_mode).pack(side=tk.LEFT, padx=(6, 0))

    ttk.Checkbutton(
        header,
        text="Voice (TTS)",
        variable=app.voice_enabled_var,
        command=app._toggle_tts_enabled,
    ).pack(side=tk.LEFT, padx=(18, 0))

    ttk.Checkbutton(
        header,
        text="Mic Listen",
        variable=app.mic_listen_var,
        command=app._toggle_mic_listen,
    ).pack(side=tk.LEFT, padx=(8, 0))

    app.status = tk.StringVar(value="Ready")
    tk.Label(
        header,
        textvariable=app.status,
        bg=THEME["panel_bg"],
        fg=THEME["green_dim"],
        font=("Consolas", 10),
    ).pack(side=tk.RIGHT, padx=12)

    body = tk.Frame(app.root, bg=THEME["bg"])
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

    left = tk.Frame(body, bg=THEME["bg"])
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    right = tk.Frame(body, bg=THEME["bg"], width=360)
    right.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
    right.pack_propagate(False)

    app.chat = ChatLog(left)
    app.chat.pack(fill=tk.BOTH, expand=True)

    toolbar = tk.Frame(left, bg=THEME["bg"])
    toolbar.pack(fill=tk.X, pady=(10, 10))

    tk.Label(toolbar, text="Model:", bg=THEME["bg"], fg=THEME["green"], font=("Consolas", 10)).pack(side=tk.LEFT)
    app.model_var = tk.StringVar(value=DEFAULT_MODEL)
    app.model_combo = ttk.Combobox(toolbar, textvariable=app.model_var, values=[DEFAULT_MODEL], state="readonly", width=28)
    app.model_combo.pack(side=tk.LEFT, padx=(6, 10))

    ttk.Button(toolbar, text="Refresh", command=app.refresh_models).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(toolbar, text="Clear Chat", command=app._clear_chat).pack(side=tk.LEFT, padx=(0, 8))

    input_frame = tk.Frame(left, bg=THEME["bg"])
    input_frame.pack(fill=tk.X)

    app.input = tk.Text(
        input_frame,
        height=3,
        wrap=tk.WORD,
        font=("Consolas", 11),
        bg=THEME["panel_bg"],
        fg=THEME["green"],
        insertbackground=THEME["green"],
        highlightthickness=1,
        highlightbackground=THEME["border"],
        highlightcolor=THEME["green"],
        padx=10,
        pady=8,
    )
    app.input.pack(side=tk.LEFT, fill=tk.X, expand=True)
    app.input.bind("<Return>", app._enter_send)
    app.input.bind("<Shift-Return>", app._shift_enter)

    telemetry = tk.Frame(right, bg=THEME["panel_bg"], highlightthickness=1, highlightbackground=THEME["border"])
    telemetry.pack(fill=tk.X, pady=(0, 8))

    app.tlm_text = tk.StringVar(value="Telemetry: initializing…")
    tk.Label(
        telemetry,
        textvariable=app.tlm_text,
        bg=THEME["panel_bg"],
        fg=THEME["green_dim"],
        font=("Consolas", 9),
        justify="left",
        anchor="w",
    ).pack(fill=tk.X, padx=8, pady=6)

    app.matrix_canvas = tk.Canvas(right, bg="#000000", highlightthickness=1, highlightbackground=THEME["border"])
    app.matrix_canvas.pack(fill=tk.BOTH, expand=True)

    app.matrix = MatrixRain(app.matrix_canvas)
    app.matrix_canvas.bind("<Configure>", app._on_matrix_resize)
