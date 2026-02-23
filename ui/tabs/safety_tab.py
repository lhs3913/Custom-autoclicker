from __future__ import annotations

from tkinter import ttk


def build_safety_tab(app, tab: ttk.Frame) -> None:
    timing_frame = ttk.LabelFrame(tab, text="Start Delay", padding=10)
    timing_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        timing_frame,
        "Start Delay",
        (
            "Options in this section:\n"
            "- Delay before start (s): countdown before run begins after Start/Stop is pressed."
        ),
    )

    ttk.Label(timing_frame, text="Delay before start (s):").grid(
        row=0, column=0, sticky="w", pady=3
    )
    ttk.Entry(timing_frame, textvariable=app.start_delay_var, width=16).grid(
        row=0, column=1, sticky="w", pady=3
    )

    safety_frame = ttk.LabelFrame(tab, text="Safety Limits", padding=10)
    safety_frame.grid(row=1, column=0, sticky="ew")
    app._attach_info_button(
        safety_frame,
        "Safety Limits",
        (
            "Options in this section:\n"
            "- Stop after N actions: stops run once action counter reaches the configured value.\n"
            "- Stop after N seconds: stops run after elapsed runtime limit.\n"
            "- Limits can be used independently or together."
        ),
    )

    ttk.Checkbutton(
        safety_frame,
        text="Stop after N actions",
        variable=app.stop_after_clicks_enabled_var,
        command=app._sync_safety_controls,
    ).grid(row=0, column=0, sticky="w", pady=3)

    app.stop_clicks_entry = ttk.Entry(safety_frame, textvariable=app.stop_after_clicks_var, width=16)
    app.stop_clicks_entry.grid(row=0, column=1, sticky="w", pady=3)

    ttk.Checkbutton(
        safety_frame,
        text="Stop after N seconds",
        variable=app.stop_after_seconds_enabled_var,
        command=app._sync_safety_controls,
    ).grid(row=1, column=0, sticky="w", pady=3)

    app.stop_seconds_entry = ttk.Entry(safety_frame, textvariable=app.stop_after_seconds_var, width=16)
    app.stop_seconds_entry.grid(row=1, column=1, sticky="w", pady=3)

    ttk.Label(
        safety_frame,
        text="Action counter includes burst actions",
        foreground="#4b5563",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))


