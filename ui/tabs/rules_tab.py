from __future__ import annotations

from tkinter import ttk


def build_rules_tab(app, tab: ttk.Frame) -> None:
    tab.columnconfigure(0, weight=1)
    window_rule_frame = ttk.LabelFrame(tab, text="Window Binding Rule", padding=10)
    window_rule_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        window_rule_frame,
        "Window Binding Rule",
        (
            "Options in this section:\n"
            "- Enable active-window title rule: requires foreground window title to match.\n"
            "- Title contains: substring that must exist in active window title.\n"
            "- Use current window: captures current foreground title into the rule field."
        ),
    )
    ttk.Checkbutton(
        window_rule_frame,
        text="Enable active-window title rule",
        variable=app.window_binding_enabled_var,
        command=app._sync_rule_controls,
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
    ttk.Label(window_rule_frame, text="Title contains:").grid(row=1, column=0, sticky="w", pady=3)
    app.window_rule_entry = ttk.Entry(window_rule_frame, textvariable=app.window_title_rule_var, width=36)
    app.window_rule_entry.grid(row=1, column=1, sticky="w", pady=3)
    ttk.Button(window_rule_frame, text="Use current window", command=app._capture_current_window_title).grid(
        row=1, column=2, sticky="w", padx=(8, 0), pady=3
    )

    time_rule_frame = ttk.LabelFrame(tab, text="Time Window Rule", padding=10)
    time_rule_frame.grid(row=1, column=0, sticky="ew")
    app._attach_info_button(
        time_rule_frame,
        "Time Window Rule",
        (
            "Options in this section:\n"
            "- Enable local time window: enforces time-based gating.\n"
            "- Start HH:MM: local start time in 24-hour format.\n"
            "- End HH:MM: local end time in 24-hour format.\n"
            "- Overnight ranges are supported (for example 22:00 to 06:00)."
        ),
    )
    ttk.Checkbutton(
        time_rule_frame,
        text="Enable local time window",
        variable=app.time_window_enabled_var,
        command=app._sync_rule_controls,
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=2)
    ttk.Label(time_rule_frame, text="Start HH:MM").grid(row=1, column=0, sticky="w", pady=3)
    app.time_start_entry = ttk.Entry(time_rule_frame, textvariable=app.time_window_start_var, width=10)
    app.time_start_entry.grid(row=1, column=1, sticky="w", pady=3)
    ttk.Label(time_rule_frame, text="End HH:MM").grid(row=1, column=2, sticky="w", pady=3, padx=(12, 0))
    app.time_end_entry = ttk.Entry(time_rule_frame, textvariable=app.time_window_end_var, width=10)
    app.time_end_entry.grid(row=1, column=3, sticky="w", pady=3)


