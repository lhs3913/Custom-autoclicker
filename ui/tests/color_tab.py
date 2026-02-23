from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def build_test_color_tab(app, tab: ttk.Frame) -> None:
    frame = ttk.LabelFrame(tab, text="Inkdrop Color Wheel", padding=10)
    frame.pack(anchor="nw")
    app._attach_info_button(
        frame,
        "Inkdrop Color Wheel",
        (
            "Options in this section:\n"
            "- Color wheel + center target: visual area for color capture testing.\n"
            "- Center button: acts as fixed target; pressing it does not change color.\n"
            "- Wheel lock hotkey + Toggle lock: toggles live wheel inkdropper mode.\n"
            "  while enabled, center color follows hovered wheel color.\n"
            "- Random interval (s): timing for automatic color changes.\n"
            "- Start/Stop random colors: toggles auto color cycling.\n"
            "- Status labels: show current color and click count."
        ),
    )
    ttk.Label(
        frame,
        text="Use this target to validate inkdrop lock capture and color-trigger matching.",
        foreground="#4b5563",
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))

    wheel_size = 260
    app.test_color_wheel_image = app._create_test_color_wheel_image(wheel_size)
    wheel_canvas = tk.Canvas(
        frame,
        width=wheel_size,
        height=wheel_size,
        bg="white",
        highlightthickness=1,
        highlightbackground="#d1d5db",
    )
    wheel_canvas.grid(row=1, column=0, sticky="w")
    wheel_canvas.create_image(wheel_size // 2, wheel_size // 2, image=app.test_color_wheel_image)
    app.test_color_wheel_canvas = wheel_canvas
    app.test_color_wheel_size = wheel_size

    app.test_center_button = tk.Button(
        wheel_canvas,
        command=app._cycle_test_center_color,
        relief="raised",
        font=("Segoe UI", 9, "bold"),
        fg="white",
        bd=1,
    )
    wheel_canvas.create_window(
        wheel_size // 2,
        wheel_size // 2,
        width=130,
        height=48,
        window=app.test_center_button,
    )
    app._apply_test_center_color()

    lock_row = ttk.Frame(frame)
    lock_row.grid(row=2, column=0, sticky="w", pady=(6, 2))
    ttk.Label(lock_row, text="Wheel lock hotkey:").grid(row=0, column=0, sticky="w")
    ttk.Entry(lock_row, textvariable=app.test_color_wheel_lock_key_var, width=6).grid(
        row=0, column=1, sticky="w", padx=(6, 10)
    )
    ttk.Button(lock_row, text="Toggle lock", command=app._toggle_test_color_wheel_lock).grid(
        row=0, column=2, sticky="w"
    )
    ttk.Label(lock_row, textvariable=app.test_color_wheel_lock_status_var).grid(
        row=0, column=3, sticky="w", padx=(10, 0)
    )

    ttk.Label(frame, textvariable=app.test_center_counter_var).grid(row=3, column=0, sticky="w", pady=(6, 2))
    ttk.Label(frame, textvariable=app.test_center_color_var).grid(row=4, column=0, sticky="w")
    auto_color_frame = ttk.Frame(frame)
    auto_color_frame.grid(row=5, column=0, sticky="w", pady=(8, 0))
    ttk.Label(auto_color_frame, text="Random interval (s):").grid(row=0, column=0, sticky="w")
    ttk.Entry(auto_color_frame, textvariable=app.test_center_random_interval_var, width=8).grid(
        row=0, column=1, sticky="w", padx=(6, 8)
    )
    app.test_center_auto_toggle_button = ttk.Button(
        auto_color_frame,
        command=app._toggle_test_center_auto_color,
        width=20,
    )
    app.test_center_auto_toggle_button.grid(row=0, column=2, sticky="w")
    ttk.Label(frame, textvariable=app.test_center_auto_status_var).grid(
        row=6, column=0, sticky="w", pady=(4, 0)
    )
    app._sync_test_center_auto_toggle_button()


