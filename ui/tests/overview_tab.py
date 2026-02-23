from __future__ import annotations

from tkinter import ttk


def build_test_overview_tab(app, tab: ttk.Frame) -> None:
    frame = ttk.LabelFrame(tab, text="Testing Overview", padding=10)
    frame.pack(fill="both", expand=True)
    app._attach_info_button(
        frame,
        "Testing Overview",
        (
            "Overview of test tabs:\n"
            "- Click Targets: validates click routing and target counting.\n"
            "- Inkdrop Colors: validates color picking and dynamic color targets.\n"
            "- Letter Counter: validates keyboard capture/focus behavior.\n"
            "- Recording Obstacles: validates recording/playback against varied UI events."
        ),
    )

    ttk.Label(
        frame,
        text="Use the tabs below for targeted manual verification.",
        font=("Segoe UI", 11, "bold"),
    ).grid(row=1, column=0, sticky="w", pady=(4, 8))

    descriptions = [
        ("Click Targets", "Create and interact with configurable button targets for click-behavior tests."),
        ("Inkdrop Colors", "Use a color wheel and dynamic target color changes for color-trigger testing."),
        ("Letter Counter", "Type letters and verify key counting and focus-dependent keyboard capture."),
        ("Recording Obstacles", "Generate diverse events (buttons, text, slider, combo, scroll) for macro tests."),
    ]
    row = 2
    for title, desc in descriptions:
        ttk.Label(frame, text=f"{title}:", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(frame, text=desc, foreground="#374151").grid(row=row + 1, column=0, sticky="w", pady=(0, 4))
        row += 2


