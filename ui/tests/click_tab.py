from __future__ import annotations

from tkinter import ttk


def build_test_click_tab(app, tab: ttk.Frame) -> None:
    frame = ttk.LabelFrame(tab, text="Autoclick Button Targets", padding=10)
    frame.pack(fill="x", anchor="nw")
    app._attach_info_button(
        frame,
        "Autoclick Button Targets",
        (
            "Options in this section:\n"
            "- Increment mode:\n"
            "  tap_to_increment = increment when button is clicked/released.\n"
            "  hold_to_increment = increment only if held for at least Hold threshold.\n"
            "- Hold threshold (s): required hold duration in hold mode.\n"
            "- New button label + Add button: create additional click targets dynamically.\n"
            "- Dynamic target rows: each target shows current count and responds using selected increment mode."
        ),
    )
    ttk.Label(
        frame,
        text="Use these targets to validate single-click, burst behavior, and hold gating.",
        foreground="#4b5563",
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 6))

    ttk.Label(frame, text="New button label:").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(frame, textvariable=app.test_click_new_button_name_var, width=24).grid(
        row=2, column=1, sticky="w", pady=3
    )
    ttk.Button(frame, text="Add button", command=app._add_test_click_target_from_ui).grid(
        row=2, column=2, sticky="w", pady=3, padx=(10, 0)
    )

    targets_container = ttk.Frame(frame)
    targets_container.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))
    app.test_click_buttons_container = targets_container
    app._add_test_click_target("Test Button 1")
    app._add_test_click_target("Test Button 2")


