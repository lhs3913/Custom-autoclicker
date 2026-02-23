from __future__ import annotations

from tkinter import ttk


def build_macro_tab(app, tab: ttk.Frame) -> None:
    tab.columnconfigure(0, weight=1)

    control_frame = ttk.LabelFrame(tab, text="Macro Controls", padding=10)
    control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    control_frame.columnconfigure(1, weight=1)
    app._attach_info_button(
        control_frame,
        "Macro Controls",
        (
            "Options in this section:\n"
            "- Use selected recording instead of single click action: switches run mode to macro playback.\n"
            "- Selected recording: chooses which saved recording is active.\n"
            "- Play once: plays selected macro immediately once.\n"
            "- Refresh: reloads recording list from in-memory state.\n"
            "- Macro speed multiplier: playback timing scale (1.0 = recorded speed).\n"
            "- Toggle recording now: starts/stops capture into temporary recording.\n"
            "- Save recording as / Save temp as named: copies temporary recording to named slot.\n"
            "- Delete selected: removes the selected recording."
        ),
    )

    ttk.Checkbutton(
        control_frame,
        text="Use selected recording instead of single click action",
        variable=app.use_macro_recording_var,
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=2)

    ttk.Label(control_frame, text="Selected recording:").grid(row=1, column=0, sticky="w", pady=3)
    app.recording_combo = ttk.Combobox(
        control_frame,
        textvariable=app.selected_recording_var,
        values=[],
        state="readonly",
        width=32,
    )
    app.recording_combo.grid(row=1, column=1, sticky="ew", pady=3)
    app.recording_combo.bind("<<ComboboxSelected>>", app._on_recording_selected, add="+")
    ttk.Button(control_frame, text="Play once", command=app._play_selected_recording_once).grid(
        row=1, column=2, sticky="w", padx=(8, 0), pady=3
    )
    ttk.Button(control_frame, text="Refresh", command=app._refresh_recording_list).grid(
        row=1, column=3, sticky="w", padx=(6, 0), pady=3
    )

    ttk.Label(control_frame, text="Macro speed multiplier:").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(control_frame, textvariable=app.macro_speed_var, width=16).grid(
        row=2, column=1, sticky="w", pady=3
    )
    ttk.Button(control_frame, text="Toggle recording now", command=app._toggle_recording_hotkey).grid(
        row=2, column=2, sticky="w", padx=(8, 0), pady=3
    )

    ttk.Label(control_frame, text="Save recording as:").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(control_frame, textvariable=app.recording_name_var, width=34).grid(
        row=3, column=1, sticky="w", pady=3
    )
    ttk.Button(control_frame, text="Save temp as named", command=app._save_temp_recording_as_named).grid(
        row=3, column=2, sticky="w", padx=(8, 0), pady=3
    )
    ttk.Button(control_frame, text="Delete selected", command=app._delete_selected_recording).grid(
        row=3, column=3, sticky="w", padx=(6, 0), pady=3
    )

    options_frame = ttk.LabelFrame(tab, text="Recording & Playback Options", padding=10)
    options_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        options_frame,
        "Recording & Playback Options",
        (
            "Options in this section:\n"
            "- Coordinate mode while recording:\n"
            "  window_relative stores relative position to the anchored foreground window.\n"
            "  absolute stores raw screen coordinates.\n"
            "- Auto re-anchor playback to current foreground window: offsets/re-targets playback for moved windows.\n"
            "- Visual dry-run: draws movement/click path without sending real input."
        ),
    )
    ttk.Label(options_frame, text="Coordinate mode while recording:").grid(
        row=0, column=0, sticky="w", pady=3
    )
    ttk.Combobox(
        options_frame,
        textvariable=app.recording_coordinate_mode_var,
        values=["window_relative", "absolute"],
        state="readonly",
        width=18,
    ).grid(row=0, column=1, sticky="w", pady=3)
    ttk.Checkbutton(
        options_frame,
        text="Auto re-anchor playback to current foreground window",
        variable=app.macro_reanchor_window_var,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
    ttk.Checkbutton(
        options_frame,
        text="Visual dry-run (draw path/clicks, do not send inputs)",
        variable=app.macro_dry_run_var,
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)

    editor_frame = ttk.LabelFrame(tab, text="Step Editor", padding=10)
    editor_frame.grid(row=2, column=0, sticky="nsew")
    tab.rowconfigure(2, weight=1)
    editor_frame.columnconfigure(0, weight=1)
    editor_frame.rowconfigure(0, weight=1)
    app._attach_info_button(
        editor_frame,
        "Step Editor",
        (
            "Options in this section:\n"
            "- Step table: index, per-step delay, type, and payload summary.\n"
            "- Delay(s): time before this step relative to previous step.\n"
            "- Type: event type (key/mouse move/click/scroll).\n"
            "- Payload JSON: editable event data object for selected step.\n"
            "- Apply Step Edit: validates and writes edits.\n"
            "- Move Up/Move Down: reorders selected step.\n"
            "- Delete Step: removes selected step and retimes remaining steps."
        ),
    )

    app.macro_step_tree = ttk.Treeview(
        editor_frame,
        columns=("idx", "delay", "type", "summary"),
        show="headings",
        height=12,
        selectmode="browse",
    )
    app.macro_step_tree.heading("idx", text="#")
    app.macro_step_tree.heading("delay", text="Delay(s)")
    app.macro_step_tree.heading("type", text="Type")
    app.macro_step_tree.heading("summary", text="Payload")
    app.macro_step_tree.column("idx", width=46, anchor="center")
    app.macro_step_tree.column("delay", width=92, anchor="e")
    app.macro_step_tree.column("type", width=110, anchor="w")
    app.macro_step_tree.column("summary", width=440, anchor="w")
    app.macro_step_tree.grid(row=0, column=0, sticky="nsew")
    app.macro_step_tree.bind("<<TreeviewSelect>>", app._on_macro_step_selected, add="+")

    tree_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=app.macro_step_tree.yview)
    tree_scroll.grid(row=0, column=1, sticky="ns")
    app.macro_step_tree.configure(yscrollcommand=tree_scroll.set)

    edit_row = ttk.Frame(editor_frame)
    edit_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    edit_row.columnconfigure(7, weight=1)

    ttk.Label(edit_row, textvariable=app.macro_selected_step_var).grid(
        row=0, column=0, columnspan=8, sticky="w", pady=(0, 4)
    )
    ttk.Label(edit_row, text="Delay(s):").grid(row=1, column=0, sticky="w")
    ttk.Entry(edit_row, textvariable=app.macro_step_delay_var, width=10).grid(
        row=1, column=1, sticky="w", padx=(4, 8)
    )
    ttk.Label(edit_row, text="Type:").grid(row=1, column=2, sticky="w")
    ttk.Combobox(
        edit_row,
        textvariable=app.macro_step_type_var,
        values=["key_press", "key_release", "mouse_move", "mouse_click", "mouse_scroll"],
        state="readonly",
        width=14,
    ).grid(row=1, column=3, sticky="w", padx=(4, 8))
    ttk.Label(edit_row, text="Payload JSON:").grid(row=1, column=4, sticky="w")
    ttk.Entry(edit_row, textvariable=app.macro_step_payload_var, width=60).grid(
        row=1, column=5, columnspan=3, sticky="ew", padx=(4, 8)
    )

    app.macro_step_apply_button = ttk.Button(
        edit_row,
        text="Apply Step Edit",
        command=app._apply_macro_step_edit,
    )
    app.macro_step_apply_button.grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Button(edit_row, text="Move Up", command=app._move_macro_step_up).grid(
        row=2, column=1, sticky="w", pady=(6, 0), padx=(6, 0)
    )
    ttk.Button(edit_row, text="Move Down", command=app._move_macro_step_down).grid(
        row=2, column=2, sticky="w", pady=(6, 0), padx=(6, 0)
    )
    ttk.Button(edit_row, text="Delete Step", command=app._delete_macro_step).grid(
        row=2, column=3, sticky="w", pady=(6, 0), padx=(6, 0)
    )


