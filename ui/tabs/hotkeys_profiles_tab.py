from __future__ import annotations

from tkinter import ttk


def build_hotkeys_profiles_tab(app, tab: ttk.Frame) -> None:
    hotkey_frame = ttk.LabelFrame(tab, text="Hotkeys", padding=10)
    hotkey_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    app._attach_info_button(
        hotkey_frame,
        "Hotkeys",
        (
            "Options in this section:\n"
            "- Start/Stop hotkey: toggles full run state.\n"
            "- Pause/Resume hotkey: pauses active run loop without stopping.\n"
            "- Record toggle hotkey: starts/stops recording capture.\n"
            "- Play recording hotkey: plays selected recording once.\n"
            "- Apply hotkeys: rebinds listeners using current values."
        ),
    )

    ttk.Label(hotkey_frame, text="Start/Stop hotkey:").grid(row=0, column=0, sticky="w", pady=3)
    ttk.Entry(hotkey_frame, textvariable=app.start_stop_hotkey_var, width=16).grid(
        row=0, column=1, sticky="w", pady=3
    )

    ttk.Label(hotkey_frame, text="Pause/Resume hotkey:").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Entry(hotkey_frame, textvariable=app.pause_hotkey_var, width=16).grid(
        row=1, column=1, sticky="w", pady=3
    )

    ttk.Label(hotkey_frame, text="Record toggle hotkey:").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Entry(hotkey_frame, textvariable=app.record_toggle_hotkey_var, width=16).grid(
        row=2, column=1, sticky="w", pady=3
    )

    ttk.Label(hotkey_frame, text="Play recording hotkey:").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(hotkey_frame, textvariable=app.play_recording_hotkey_var, width=16).grid(
        row=3, column=1, sticky="w", pady=3
    )

    ttk.Button(hotkey_frame, text="Apply hotkeys", command=app._start_hotkeys).grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(6, 0)
    )

    profile_frame = ttk.LabelFrame(tab, text="Profiles", padding=10)
    profile_frame.grid(row=1, column=0, sticky="ew")
    app._attach_info_button(
        profile_frame,
        "Profiles",
        (
            "Options in this section:\n"
            "- Profile dropdown: chooses saved profile snapshot.\n"
            "- Load: applies selected profile values to UI and runtime settings.\n"
            "- Delete: removes selected profile from disk.\n"
            "- Save as + Save profile: writes current configuration to profile name.\n"
            "- Refresh: reloads profile list.\n"
            "- Apply profile-specific hotkeys when loading profile: controls whether hotkeys are rebound on load."
        ),
    )

    ttk.Label(profile_frame, text="Profile:").grid(row=0, column=0, sticky="w", pady=3)
    app.profile_combo = ttk.Combobox(
        profile_frame,
        textvariable=app.profile_select_var,
        values=[],
        state="readonly",
        width=28,
    )
    app.profile_combo.grid(row=0, column=1, sticky="w", pady=3)

    ttk.Button(profile_frame, text="Load", command=app._load_selected_profile).grid(
        row=0, column=2, sticky="w", padx=(8, 0), pady=3
    )
    ttk.Button(profile_frame, text="Delete", command=app._delete_selected_profile).grid(
        row=0, column=3, sticky="w", padx=(6, 0), pady=3
    )

    ttk.Label(profile_frame, text="Save as:").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Entry(profile_frame, textvariable=app.profile_name_var, width=30).grid(
        row=1, column=1, sticky="w", pady=3
    )

    ttk.Button(profile_frame, text="Save profile", command=app._save_profile).grid(
        row=1, column=2, sticky="w", padx=(8, 0), pady=3
    )
    ttk.Button(profile_frame, text="Refresh", command=app._refresh_profile_list).grid(
        row=1, column=3, sticky="w", padx=(6, 0), pady=3
    )

    ttk.Checkbutton(
        profile_frame,
        text="Apply profile-specific hotkeys when loading profile",
        variable=app.profile_hotkeys_enabled_var,
    ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

    ttk.Label(
        profile_frame,
        text=f"Profiles file: {app.profile_path}",
        foreground="#4b5563",
    ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

    testing_frame = ttk.LabelFrame(tab, text="Testing", padding=10)
    testing_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    app._attach_info_button(
        testing_frame,
        "Testing",
        (
            "Options in this section:\n"
            "- Open test window: opens the testing utility window with overview and dedicated test tabs."
        ),
    )
    ttk.Button(
        testing_frame,
        text="Open test window",
        command=app._open_test_window,
    ).grid(row=0, column=0, sticky="w")


