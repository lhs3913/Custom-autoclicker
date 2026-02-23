from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def build_test_obstacle_tab(app, tab: ttk.Frame) -> None:
    frame = ttk.LabelFrame(tab, text="Recording Obstacle Course", padding=10)
    frame.pack(fill="both", expand=True)
    app._attach_info_button(
        frame,
        "Recording Obstacle Course",
        (
            "Options in this section:\n"
            "- Buttons, entry, combobox, spinbox, checkbutton, slider, and text box create varied event types.\n"
            "- Interaction counters show total obstacle actions and last action type.\n"
            "- Use this tab to stress-test macro recording/playback payload diversity."
        ),
    )
    frame.columnconfigure(0, weight=0)
    frame.columnconfigure(1, weight=0)
    frame.columnconfigure(2, weight=1)
    frame.rowconfigure(5, weight=1)

    ttk.Label(
        frame,
        text="Interact with controls below to generate varied recording events.",
        foreground="#4b5563",
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
    ttk.Label(
        frame,
        textvariable=app.test_obstacle_counter_var,
        foreground="#1e3a8a",
    ).grid(row=1, column=0, columnspan=2, sticky="w")
    ttk.Label(frame, textvariable=app.test_obstacle_last_var).grid(row=1, column=2, sticky="w")

    ttk.Button(
        frame,
        text="Obstacle Button A",
        command=lambda: app._increment_test_obstacle_counter("Button A"),
    ).grid(row=2, column=0, sticky="w", pady=(6, 2))
    ttk.Button(
        frame,
        text="Obstacle Button B",
        command=lambda: app._increment_test_obstacle_counter("Button B"),
    ).grid(row=2, column=1, sticky="w", pady=(6, 2), padx=(6, 0))
    ttk.Button(
        frame,
        text="Obstacle Button C",
        command=lambda: app._increment_test_obstacle_counter("Button C"),
    ).grid(row=2, column=2, sticky="w", pady=(6, 2), padx=(6, 0))

    entry_one = ttk.Entry(frame, width=26)
    entry_one.grid(row=3, column=0, sticky="w", pady=(6, 2))
    entry_one.bind(
        "<KeyRelease>",
        lambda _event: app._increment_test_obstacle_counter("Entry typing"),
        add="+",
    )

    combo = ttk.Combobox(
        frame,
        values=["option-1", "option-2", "option-3"],
        state="readonly",
        width=14,
    )
    combo.grid(row=3, column=1, sticky="w", pady=(6, 2), padx=(6, 0))
    combo.bind(
        "<<ComboboxSelected>>",
        lambda _event: app._increment_test_obstacle_counter("Combobox select"),
        add="+",
    )

    spinbox = tk.Spinbox(
        frame,
        from_=0,
        to=50,
        width=8,
        command=lambda: app._increment_test_obstacle_counter("Spinbox step"),
    )
    spinbox.grid(row=3, column=2, sticky="w", pady=(6, 2), padx=(6, 0))

    ttk.Checkbutton(
        frame,
        text="Toggle checkpoint",
        variable=app.test_obstacle_toggle_var,
        command=lambda: app._increment_test_obstacle_counter("Checkbutton toggle"),
    ).grid(row=4, column=0, sticky="w", pady=(8, 2))

    slider = ttk.Scale(
        frame,
        from_=0,
        to=100,
        orient="horizontal",
        command=lambda _value: app._increment_test_obstacle_counter("Slider move"),
    )
    slider.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 2))

    text_box = tk.Text(frame, height=5, width=54)
    text_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    text_box.bind(
        "<KeyRelease>",
        lambda _event: app._increment_test_obstacle_counter("Text edit"),
        add="+",
    )
    entry_one.focus_set()


