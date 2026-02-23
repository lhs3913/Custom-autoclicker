from __future__ import annotations

from tkinter import ttk


def build_click_tab(app, tab: ttk.Frame) -> None:
    action_frame = ttk.LabelFrame(tab, text="Input Action", padding=10)
    action_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        action_frame,
        "Input Action",
        (
            "Options in this section:\n"
            "- Action type: choose 'mouse' to send mouse clicks or 'keyboard' to send key presses.\n"
            "- Mouse button: only used when Action type is mouse; picks left/right/middle click.\n"
            "- Keyboard key: only used when Action type is keyboard; accepts single chars and supported named keys."
        ),
    )

    ttk.Label(action_frame, text="Action type:").grid(row=0, column=0, sticky="w", pady=3)
    action_combo = ttk.Combobox(
        action_frame,
        textvariable=app.action_type_var,
        values=["mouse", "keyboard"],
        state="readonly",
        width=14,
    )
    action_combo.grid(row=0, column=1, sticky="w", pady=3)
    action_combo.bind("<<ComboboxSelected>>", app._on_action_type_changed)

    app.mouse_button_label = ttk.Label(action_frame, text="Mouse button:")
    app.mouse_button_label.grid(row=1, column=0, sticky="w", pady=3)
    app.mouse_button_combo = ttk.Combobox(
        action_frame,
        textvariable=app.button_var,
        values=["left", "right", "middle"],
        state="readonly",
        width=14,
    )
    app.mouse_button_combo.grid(row=1, column=1, sticky="w", pady=3)

    app.keyboard_key_label = ttk.Label(action_frame, text="Keyboard key:")
    app.keyboard_key_label.grid(row=2, column=0, sticky="w", pady=3)
    app.keyboard_key_entry = ttk.Entry(action_frame, textvariable=app.keyboard_key_var, width=16)
    app.keyboard_key_entry.grid(row=2, column=1, sticky="w", pady=3)

    behavior_frame = ttk.LabelFrame(tab, text="Behavior", padding=10)
    behavior_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        behavior_frame,
        "Behavior",
        (
            "Options in this section:\n"
            "- Click style: 'tap' sends a quick click/keypress, 'hold' keeps it down for Hold duration.\n"
            "- Hold duration (s): press time used only in hold mode.\n"
            "- Burst count: number of actions in one cycle.\n"
            "- Gap between burst actions (s): delay between each action inside a burst."
        ),
    )

    ttk.Label(behavior_frame, text="Click style:").grid(row=0, column=0, sticky="w", pady=3)
    click_style_combo = ttk.Combobox(
        behavior_frame,
        textvariable=app.click_style_var,
        values=["tap", "hold"],
        state="readonly",
        width=14,
    )
    click_style_combo.grid(row=0, column=1, sticky="w", pady=3)
    click_style_combo.bind("<<ComboboxSelected>>", app._on_click_style_changed)

    app.hold_duration_label = ttk.Label(behavior_frame, text="Hold duration (s):")
    app.hold_duration_label.grid(row=1, column=0, sticky="w", pady=3)
    app.hold_duration_entry = ttk.Entry(behavior_frame, textvariable=app.hold_duration_var, width=16)
    app.hold_duration_entry.grid(row=1, column=1, sticky="w", pady=3)

    ttk.Label(behavior_frame, text="Burst count:").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(behavior_frame, textvariable=app.burst_count_var, width=16).grid(
        row=2, column=1, sticky="w", pady=3
    )

    ttk.Label(behavior_frame, text="Gap between burst actions (s):").grid(
        row=3, column=0, sticky="w", pady=3
    )
    ttk.Entry(behavior_frame, textvariable=app.burst_gap_var, width=16).grid(
        row=3, column=1, sticky="w", pady=3
    )

    ttk.Label(
        behavior_frame,
        text="Double-click = burst count 2",
        foreground="#4b5563",
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(3, 0))

    timing_frame = ttk.LabelFrame(tab, text="Timing", padding=10)
    timing_frame.grid(row=2, column=0, sticky="ew")
    app._attach_info_button(
        timing_frame,
        "Timing",
        (
            "Options in this section:\n"
            "- Base interval (s): main delay between cycles.\n"
            "- Randomize interval: enables min/max range randomization each cycle.\n"
            "- Random min/max (s): lower/upper bounds used when randomization is on.\n"
            "- Enable anti-detection timing model: adds timing variance.\n"
            "- Jitter (%): +/- percentage applied to the chosen interval.\n"
            "- Micro-pause chance (%): probability of adding an extra pause.\n"
            "- Max micro-pause (s): maximum added pause duration."
        ),
    )

    ttk.Label(timing_frame, text="Base interval (s):").grid(row=0, column=0, sticky="w", pady=3)
    ttk.Entry(timing_frame, textvariable=app.interval_var, width=16).grid(
        row=0, column=1, sticky="w", pady=3
    )

    ttk.Checkbutton(
        timing_frame,
        text="Randomize interval",
        variable=app.randomize_interval_var,
        command=app._sync_timing_controls,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 4))

    app.interval_min_label = ttk.Label(timing_frame, text="Random min (s):")
    app.interval_min_label.grid(row=2, column=0, sticky="w", pady=3)
    app.interval_min_entry = ttk.Entry(timing_frame, textvariable=app.interval_min_var, width=16)
    app.interval_min_entry.grid(row=2, column=1, sticky="w", pady=3)

    app.interval_max_label = ttk.Label(timing_frame, text="Random max (s):")
    app.interval_max_label.grid(row=3, column=0, sticky="w", pady=3)
    app.interval_max_entry = ttk.Entry(timing_frame, textvariable=app.interval_max_var, width=16)
    app.interval_max_entry.grid(row=3, column=1, sticky="w", pady=3)

    ttk.Checkbutton(
        timing_frame,
        text="Enable anti-detection timing model",
        variable=app.anti_detection_enabled_var,
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 2))
    ttk.Label(timing_frame, text="Jitter (%):").grid(row=5, column=0, sticky="w", pady=2)
    ttk.Entry(timing_frame, textvariable=app.anti_detection_jitter_pct_var, width=16).grid(
        row=5, column=1, sticky="w", pady=2
    )
    ttk.Label(timing_frame, text="Micro-pause chance (%):").grid(row=6, column=0, sticky="w", pady=2)
    ttk.Entry(timing_frame, textvariable=app.anti_detection_pause_chance_var, width=16).grid(
        row=6, column=1, sticky="w", pady=2
    )
    ttk.Label(timing_frame, text="Max micro-pause (s):").grid(row=7, column=0, sticky="w", pady=2)
    ttk.Entry(timing_frame, textvariable=app.anti_detection_max_pause_var, width=16).grid(
        row=7, column=1, sticky="w", pady=2
    )


