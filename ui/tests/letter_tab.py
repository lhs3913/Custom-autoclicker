from __future__ import annotations

from tkinter import ttk


def build_test_letter_tab(app, tab: ttk.Frame) -> None:
    frame = ttk.LabelFrame(tab, text="Letter Counter", padding=10)
    frame.pack(fill="x", anchor="nw")
    app._attach_info_button(
        frame,
        "Letter Counter",
        (
            "Options in this section:\n"
            "- Character stats labels: total typed chars, last char, and per-char breakdown.\n"
            "- Counts include spaces, punctuation, digits, and case-sensitive letters.\n"
            "- Type while this window is focused to validate keyboard event capture."
        ),
    )
    ttk.Label(
        frame,
        text="Click inside this window and type characters. Counts are case-sensitive.",
        foreground="#4b5563",
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    ttk.Label(frame, textvariable=app.test_letter_total_var).grid(row=1, column=0, sticky="w", pady=2)
    ttk.Label(frame, textvariable=app.test_letter_last_var).grid(row=1, column=1, sticky="w", pady=2)
    ttk.Label(frame, textvariable=app.test_letter_breakdown_var).grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(2, 0)
    )


