from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def build_color_tab(app, tab: ttk.Frame) -> None:
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(0, weight=1)

    outer = ttk.Frame(tab)
    outer.grid(row=0, column=0, sticky="nsew")
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)

    canvas = tk.Canvas(outer, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scroll.set)

    content = ttk.Frame(canvas, padding=(0, 0, 4, 0))
    content_id = canvas.create_window((0, 0), window=content, anchor="nw")
    content.columnconfigure(0, weight=1)

    def _on_content_resize(_event: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_resize(event: tk.Event) -> None:
        canvas.itemconfigure(content_id, width=event.width)

    def _on_mouse_wheel(event: tk.Event) -> None:
        if event.delta == 0:
            return
        canvas.yview_scroll(int(-event.delta / 120), "units")

    content.bind("<Configure>", _on_content_resize, add="+")
    canvas.bind("<Configure>", _on_canvas_resize, add="+")
    canvas.bind("<MouseWheel>", _on_mouse_wheel, add="+")
    content.bind("<MouseWheel>", _on_mouse_wheel, add="+")

    header_row = ttk.LabelFrame(content, text="Trigger", padding=10)
    header_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    header_row.columnconfigure(3, weight=1)
    app._attach_info_button(
        header_row,
        "Color Trigger",
        (
            "Options in this section:\n"
            "- Enable color trigger: gates action execution by color match result.\n"
            "- When color matches:\n"
            "  continuous = keep firing while the match stays true.\n"
            "  single = fire once on transition from non-match to match."
        ),
    )

    ttk.Checkbutton(
        header_row,
        text="Enable color trigger",
        variable=app.use_color_check_var,
    ).grid(row=0, column=0, sticky="w", pady=2)

    ttk.Label(header_row, text="When color matches:").grid(row=0, column=1, sticky="w", padx=(12, 4))
    ttk.Combobox(
        header_row,
        textvariable=app.color_trigger_mode_var,
        values=["continuous", "single"],
        state="readonly",
        width=12,
    ).grid(row=0, column=2, sticky="w")

    app.color_options_frame = content

    color_target_frame = ttk.LabelFrame(content, text="Target", padding=10)
    color_target_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        color_target_frame,
        "Color Target",
        (
            "Options in this section:\n"
            "- Target color (hex): exact color to detect (example: #A1B2C3).\n"
            "- Start inkdropper: starts live hover sampling so you can capture a color.\n"
            "- Preview: shows current target color and validation state.\n"
            "- Tolerance (0-255): allowed RGB per-channel difference from target.\n"
            "- Inkdrop lock key: key used to lock the currently hovered color while inkdropper is active."
        ),
    )

    ttk.Label(color_target_frame, text="Target color (hex):").grid(
        row=0, column=0, sticky="w", pady=3
    )
    ttk.Entry(color_target_frame, textvariable=app.target_color_var, width=16).grid(
        row=0, column=1, sticky="w", pady=3
    )

    app.inkdrop_start_button = ttk.Button(
        color_target_frame,
        text="Start inkdropper",
        command=app._start_inkdropper,
    )
    app.inkdrop_start_button.grid(row=0, column=2, sticky="w", pady=3, padx=(8, 0))

    ttk.Label(color_target_frame, text="Preview:").grid(row=1, column=0, sticky="w", pady=3)
    app.color_preview_swatch = tk.Label(
        color_target_frame,
        width=8,
        height=1,
        relief="solid",
        bd=1,
        bg="#ffffff",
    )
    app.color_preview_swatch.grid(row=1, column=1, sticky="w", pady=3)

    ttk.Label(color_target_frame, textvariable=app.color_preview_text_var).grid(
        row=1, column=2, sticky="w", pady=3, padx=(8, 0)
    )

    ttk.Label(color_target_frame, text="Tolerance (0-255):").grid(
        row=2, column=0, sticky="w", pady=3
    )
    ttk.Entry(color_target_frame, textvariable=app.tolerance_var, width=16).grid(
        row=2, column=1, sticky="w", pady=3
    )

    ttk.Label(color_target_frame, text="Inkdrop lock key:").grid(
        row=3, column=0, sticky="w", pady=3
    )
    ttk.Entry(color_target_frame, textvariable=app.inkdrop_lock_key_var, width=16).grid(
        row=3, column=1, sticky="w", pady=3
    )

    ttk.Label(
        color_target_frame,
        text="Hover any window and press lock key to capture color",
        foreground="#4b5563",
    ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(3, 0))

    sample_frame = ttk.LabelFrame(content, text="Sampling Source", padding=10)
    sample_frame.grid(row=2, column=0, sticky="ew")
    app._attach_info_button(
        sample_frame,
        "Sampling Source",
        (
            "Options in this section:\n"
            "- Sample mode:\n"
            "  cursor = read the pixel under current cursor position.\n"
            "  point = read one fixed coordinate.\n"
            "  region = detect whether any pixel in a rectangle matches.\n"
            "- Monitor: optional monitor boundary filter for multi-monitor setups.\n"
            "- Point X / Y + Use cursor: set fixed point manually or from cursor.\n"
            "- Region x1,y1,x2,y2: explicit rectangle bounds.\n"
            "- Quick region size + Center at cursor: creates a square region centered on cursor."
        ),
    )

    ttk.Label(sample_frame, text="Sample mode:").grid(row=0, column=0, sticky="w", pady=3)
    sample_mode_combo = ttk.Combobox(
        sample_frame,
        textvariable=app.color_sample_mode_var,
        values=["cursor", "point", "region"],
        state="readonly",
        width=14,
    )
    sample_mode_combo.grid(row=0, column=1, sticky="w", pady=3)
    sample_mode_combo.bind("<<ComboboxSelected>>", app._on_color_sample_mode_changed)

    ttk.Label(sample_frame, text="Monitor:").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Combobox(
        sample_frame,
        textvariable=app.monitor_var,
        values=list(app.monitor_options.keys()),
        state="readonly",
        width=34,
    ).grid(row=1, column=1, columnspan=3, sticky="w", pady=3)

    point_label = ttk.Label(sample_frame, text="Point X / Y:")
    point_label.grid(row=2, column=0, sticky="w", pady=3)
    point_x_entry = ttk.Entry(sample_frame, textvariable=app.point_x_var, width=8)
    point_x_entry.grid(row=2, column=1, sticky="w", pady=3)
    point_y_entry = ttk.Entry(sample_frame, textvariable=app.point_y_var, width=8)
    point_y_entry.grid(row=2, column=2, sticky="w", pady=3, padx=(4, 0))
    point_cursor_btn = ttk.Button(
        sample_frame,
        text="Use cursor",
        command=app._set_point_from_cursor,
    )
    point_cursor_btn.grid(row=2, column=3, sticky="w", pady=3, padx=(8, 0))

    region_label = ttk.Label(sample_frame, text="Region x1,y1,x2,y2:")
    region_label.grid(row=3, column=0, sticky="w", pady=3)
    region_x1_entry = ttk.Entry(sample_frame, textvariable=app.region_x1_var, width=8)
    region_x1_entry.grid(row=3, column=1, sticky="w", pady=3)
    region_y1_entry = ttk.Entry(sample_frame, textvariable=app.region_y1_var, width=8)
    region_y1_entry.grid(row=3, column=2, sticky="w", pady=3, padx=(4, 0))

    region_x2_entry = ttk.Entry(sample_frame, textvariable=app.region_x2_var, width=8)
    region_x2_entry.grid(row=4, column=1, sticky="w", pady=3)
    region_y2_entry = ttk.Entry(sample_frame, textvariable=app.region_y2_var, width=8)
    region_y2_entry.grid(row=4, column=2, sticky="w", pady=3, padx=(4, 0))

    ttk.Label(sample_frame, text="Quick region size:").grid(row=5, column=0, sticky="w", pady=3)
    region_size_entry = ttk.Entry(sample_frame, textvariable=app.region_size_var, width=8)
    region_size_entry.grid(row=5, column=1, sticky="w", pady=3)
    region_cursor_btn = ttk.Button(
        sample_frame,
        text="Center at cursor",
        command=app._set_region_around_cursor,
    )
    region_cursor_btn.grid(row=5, column=3, sticky="w", pady=3, padx=(8, 0))

    history_frame = ttk.LabelFrame(content, text="Pixel History", padding=10)
    history_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    app._attach_info_button(
        history_frame,
        "Pixel History",
        (
            "Options in this section:\n"
            "- Enable history panel: turns recent sample logging on/off.\n"
            "- List panel: shows recent sampled values and MATCH/MISS outcomes.\n"
            "- Clear history: clears all currently shown history entries."
        ),
    )
    ttk.Checkbutton(
        history_frame,
        text="Enable history panel",
        variable=app.pixel_history_enabled_var,
    ).grid(row=0, column=0, sticky="w", pady=2)
    app.pixel_history_listbox = tk.Listbox(history_frame, height=7, width=44)
    app.pixel_history_listbox.grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
    ttk.Button(history_frame, text="Clear history", command=app._clear_pixel_history).grid(
        row=2, column=0, sticky="w"
    )

    app.point_widgets = [point_label, point_x_entry, point_y_entry, point_cursor_btn]
    app.region_widgets = [
        region_label,
        region_x1_entry,
        region_y1_entry,
        region_x2_entry,
        region_y2_entry,
        region_size_entry,
        region_cursor_btn,
    ]


