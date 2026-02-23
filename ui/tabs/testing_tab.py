from __future__ import annotations

from tkinter import ttk


def build_testing_tab(app, tab: ttk.Frame) -> None:
    tab.columnconfigure(0, weight=1)

    summary = ttk.LabelFrame(tab, text="Testing Windows", padding=10)
    summary.grid(row=0, column=0, sticky="ew")
    app._attach_info_button(
        summary,
        "Testing Windows",
        (
            "Options in this section:\n"
            "- Open Click Targets Test: validates click precision and burst behavior.\n"
            "- Open Color Wheel Test: validates color capture and matching workflows.\n"
            "- Open Letter Counter Test: validates keyboard capture and key routing.\n"
            "- Open Recording Obstacle Test: generates mixed events for macro recording validation."
        ),
    )
    ttk.Label(
        summary,
        text=(
            "Open a test window with dedicated tabs for click targets, inkdrop colors, "
            "letter counting, and recording obstacles."
        ),
        foreground="#4b5563",
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

    ttk.Button(summary, text="Open Click Targets Test", command=lambda: app._open_test_window("click")).grid(
        row=1, column=0, sticky="w", pady=2
    )
    ttk.Button(summary, text="Open Color Wheel Test", command=lambda: app._open_test_window("color")).grid(
        row=2, column=0, sticky="w", pady=2
    )
    ttk.Button(summary, text="Open Letter Counter Test", command=lambda: app._open_test_window("letters")).grid(
        row=3, column=0, sticky="w", pady=2
    )
    ttk.Button(
        summary,
        text="Open Recording Obstacle Test",
        command=lambda: app._open_test_window("obstacle"),
    ).grid(row=4, column=0, sticky="w", pady=2)


