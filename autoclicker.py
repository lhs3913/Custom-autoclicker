import ctypes
import colorsys
import json
import math
import os
import random
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk

from PIL import Image, ImageGrab, ImageTk
from pynput import keyboard, mouse
from pynput.mouse import Button


PROFILE_FILE_NAME = "profiles.json"
RECORDINGS_FILE_NAME = "recordings.json"
TEMP_RECORDING_NAME = "(temporary)"


ActionTarget = Button | keyboard.Key | keyboard.KeyCode
Rect = tuple[int, int, int, int]


@dataclass(slots=True)
class ClickSettings:
    interval: float
    randomize_interval: bool
    interval_min: float
    interval_max: float
    action_type: str
    action_target: ActionTarget
    hold_mode: bool
    hold_duration: float
    burst_count: int
    burst_gap: float
    use_color: bool
    target_rgb: tuple[int, int, int]
    tolerance: int
    color_sample_mode: str
    point_sample: tuple[int, int] | None
    region_sample: Rect | None
    selected_monitor_bounds: Rect | None
    start_delay: float
    stop_after_clicks: int | None
    stop_after_seconds: float | None
    condition_logic_mode: str
    window_binding_enabled: bool
    window_title_rule: str
    time_window_enabled: bool
    allowed_start_time: str
    allowed_end_time: str
    edge_trigger_enabled: bool
    anti_detection_enabled: bool
    anti_detection_jitter_pct: float
    anti_detection_pause_chance: float
    anti_detection_max_pause: float
    use_macro_recording: bool
    selected_recording_name: str
    macro_speed: float


@dataclass(slots=True)
class RecordingEvent:
    t: float
    type: str
    payload: dict[str, object]


def evaluate_rule_conditions(enabled_results: list[bool], mode: str) -> bool:
    if not enabled_results:
        return True

    if mode == "or":
        return any(enabled_results)
    return all(enabled_results)


def edge_trigger_allows_fire(previous_match: bool, current_match: bool, enabled: bool) -> bool:
    if not enabled:
        return current_match
    return (not previous_match) and current_match


def compute_anti_detection_interval(
    base_interval: float,
    enabled: bool,
    jitter_pct: float,
    pause_chance: float,
    max_pause: float,
    rng: random.Random | None = None,
) -> float:
    if not enabled:
        return max(0.001, base_interval)

    rng_obj = rng or random
    jitter_amount = base_interval * max(0.0, jitter_pct / 100.0)
    jitter = rng_obj.uniform(-jitter_amount, jitter_amount)
    interval = base_interval + jitter

    if pause_chance > 0 and rng_obj.random() < min(1.0, max(0.0, pause_chance / 100.0)):
        interval += rng_obj.uniform(0.0, max(0.0, max_pause))

    return max(0.001, interval)


class AutoClickerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Custom Auto Clicker")
        self.root.geometry("780x730")
        self.root.resizable(False, False)

        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()

        self.running = False
        self.paused = False
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None

        self.hotkey_listener: keyboard.GlobalHotKeys | None = None
        self.inkdrop_lock_listener: keyboard.Listener | None = None
        self.inkdrop_lock_key: keyboard.Key | keyboard.KeyCode | None = None

        self.inkdropper_active = False
        self.inkdrop_after_id: str | None = None

        self.crosshair_enabled = False
        self.crosshair_overlay: tk.Toplevel | None = None
        self.crosshair_canvas: tk.Canvas | None = None
        self.crosshair_after_id: str | None = None
        self.crosshair_overlay_origin = (0, 0)

        self.profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PROFILE_FILE_NAME)
        self.recordings_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), RECORDINGS_FILE_NAME
        )
        self.profiles: dict[str, dict[str, object]] = {}
        self.recordings: dict[str, list[dict[str, object]]] = {}

        self.monitor_options = self._detect_monitors()

        self.recording_active = False
        self.recording_started_at = 0.0
        self.recording_events: list[RecordingEvent] = []
        self.recording_keyboard_listener: keyboard.Listener | None = None
        self.recording_mouse_listener: mouse.Listener | None = None
        self.recording_last_move_time = 0.0
        self.recording_last_move_pos: tuple[int, int] | None = None

        self.pixel_history: list[str] = []
        self.last_color_condition_match = False

        self.start_stop_hotkey_var = tk.StringVar(value="<f8>")
        self.pause_hotkey_var = tk.StringVar(value="<f9>")
        self.record_toggle_hotkey_var = tk.StringVar(value="<f6>")
        self.play_recording_hotkey_var = tk.StringVar(value="<f7>")

        self.action_type_var = tk.StringVar(value="mouse")
        self.button_var = tk.StringVar(value="left")
        self.keyboard_key_var = tk.StringVar(value="a")

        self.click_style_var = tk.StringVar(value="tap")
        self.hold_duration_var = tk.StringVar(value="0.20")

        self.interval_var = tk.StringVar(value="0.10")
        self.randomize_interval_var = tk.BooleanVar(value=False)
        self.interval_min_var = tk.StringVar(value="0.08")
        self.interval_max_var = tk.StringVar(value="0.12")
        self.anti_detection_enabled_var = tk.BooleanVar(value=False)
        self.anti_detection_jitter_pct_var = tk.StringVar(value="12")
        self.anti_detection_pause_chance_var = tk.StringVar(value="4")
        self.anti_detection_max_pause_var = tk.StringVar(value="0.25")

        self.burst_count_var = tk.StringVar(value="1")
        self.burst_gap_var = tk.StringVar(value="0.03")

        self.start_delay_var = tk.StringVar(value="0")
        self.stop_after_clicks_enabled_var = tk.BooleanVar(value=False)
        self.stop_after_clicks_var = tk.StringVar(value="1000")
        self.stop_after_seconds_enabled_var = tk.BooleanVar(value=False)
        self.stop_after_seconds_var = tk.StringVar(value="60")

        self.use_color_check_var = tk.BooleanVar(value=False)
        self.color_options_visible_var = tk.BooleanVar(value=False)
        self.target_color_var = tk.StringVar(value="#ffffff")
        self.tolerance_var = tk.StringVar(value="20")
        self.color_preview_text_var = tk.StringVar(value="#FFFFFF")
        self.edge_trigger_var = tk.BooleanVar(value=False)
        self.pixel_history_enabled_var = tk.BooleanVar(value=True)
        self.condition_logic_mode_var = tk.StringVar(value="and")

        self.color_sample_mode_var = tk.StringVar(value="cursor")
        monitor_names = list(self.monitor_options.keys())
        self.monitor_var = tk.StringVar(value=monitor_names[0] if monitor_names else "All monitors")

        self.point_x_var = tk.StringVar(value="0")
        self.point_y_var = tk.StringVar(value="0")

        self.region_x1_var = tk.StringVar(value="0")
        self.region_y1_var = tk.StringVar(value="0")
        self.region_x2_var = tk.StringVar(value="200")
        self.region_y2_var = tk.StringVar(value="200")
        self.region_size_var = tk.StringVar(value="120")

        self.inkdrop_lock_key_var = tk.StringVar(value="s")
        self.window_binding_enabled_var = tk.BooleanVar(value=False)
        self.window_title_rule_var = tk.StringVar(value="")
        self.time_window_enabled_var = tk.BooleanVar(value=False)
        self.time_window_start_var = tk.StringVar(value="00:00")
        self.time_window_end_var = tk.StringVar(value="23:59")

        self.profile_name_var = tk.StringVar(value="")
        self.profile_select_var = tk.StringVar(value="")
        self.profile_hotkeys_enabled_var = tk.BooleanVar(value=True)

        self.use_macro_recording_var = tk.BooleanVar(value=False)
        self.selected_recording_var = tk.StringVar(value=TEMP_RECORDING_NAME)
        self.recording_name_var = tk.StringVar(value="")
        self.macro_speed_var = tk.StringVar(value="1.0")

        self.status_var = tk.StringVar(value="Idle")
        self.session_info_var = tk.StringVar(value="Clicks: 0 | Elapsed: 0.0s")

        self.mouse_button_label: ttk.Label | None = None
        self.mouse_button_combo: ttk.Combobox | None = None
        self.keyboard_key_label: ttk.Label | None = None
        self.keyboard_key_entry: ttk.Entry | None = None

        self.hold_duration_label: ttk.Label | None = None
        self.hold_duration_entry: ttk.Entry | None = None

        self.interval_min_label: ttk.Label | None = None
        self.interval_min_entry: ttk.Entry | None = None
        self.interval_max_label: ttk.Label | None = None
        self.interval_max_entry: ttk.Entry | None = None

        self.color_options_frame: ttk.Frame | None = None
        self.color_toggle_button: ttk.Button | None = None
        self.color_preview_swatch: tk.Label | None = None

        self.point_widgets: list[tk.Widget] = []
        self.region_widgets: list[tk.Widget] = []

        self.crosshair_button: ttk.Button | None = None
        self.inkdrop_start_button: ttk.Button | None = None

        self.stop_clicks_entry: ttk.Entry | None = None
        self.stop_seconds_entry: ttk.Entry | None = None

        self.profile_combo: ttk.Combobox | None = None
        self.recording_combo: ttk.Combobox | None = None
        self.pixel_history_listbox: tk.Listbox | None = None
        self.window_rule_entry: ttk.Entry | None = None
        self.time_start_entry: ttk.Entry | None = None
        self.time_end_entry: ttk.Entry | None = None

        self.test_window: tk.Toplevel | None = None
        self.test_center_button: tk.Button | None = None
        self.test_center_auto_toggle_button: ttk.Button | None = None
        self.test_color_wheel_image: ImageTk.PhotoImage | None = None
        self.test_center_auto_after_id: str | None = None

        self.test_button_one_count = 0
        self.test_button_two_count = 0
        self.test_center_click_count = 0
        self.test_center_current_color = "#1f7a8c"
        self.test_center_auto_color_enabled = False
        self.test_letter_total_count = 0
        self.test_letter_counts: dict[str, int] = {}
        self.test_obstacle_count = 0

        self.test_obstacle_toggle_var = tk.BooleanVar(value=False)

        self.test_button_one_var = tk.StringVar(value="Button 1 clicks: 0")
        self.test_button_two_var = tk.StringVar(value="Button 2 clicks: 0")
        self.test_center_counter_var = tk.StringVar(value="Center button clicks: 0")
        self.test_center_color_var = tk.StringVar(value="Current center color: #1F7A8C")
        self.test_center_random_interval_var = tk.StringVar(value="0.75")
        self.test_center_auto_status_var = tk.StringVar(value="Auto random color: off")
        self.test_letter_total_var = tk.StringVar(value="Letters pressed: 0")
        self.test_letter_last_var = tk.StringVar(value="Last letter: none")
        self.test_letter_breakdown_var = tk.StringVar(value="Breakdown: none")
        self.test_obstacle_counter_var = tk.StringVar(value="Obstacle interactions: 0")
        self.test_obstacle_last_var = tk.StringVar(value="Last obstacle action: none")

        self._build_ui()
        self._sync_action_controls()
        self._sync_hold_controls()
        self._sync_timing_controls()
        self._set_color_options_visible(self.color_options_visible_var.get())
        self._sync_color_mode_controls()
        self._sync_safety_controls()
        self._sync_rule_controls()

        self.target_color_var.trace_add("write", self._on_target_color_change)
        self._update_color_preview()

        self._load_profiles_from_disk()
        self._load_recordings_from_disk()
        self._refresh_profile_list()
        self._refresh_recording_list()
        self._start_hotkeys()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        header_frame = ttk.Frame(container)
        header_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(
            header_frame,
            text="Custom Auto Clicker",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header_frame,
            textvariable=self.session_info_var,
            foreground="#374151",
        ).pack(anchor="w", pady=(2, 0))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        click_tab = ttk.Frame(notebook, padding=10)
        color_tab = ttk.Frame(notebook, padding=10)
        safety_tab = ttk.Frame(notebook, padding=10)
        hotkey_profile_tab = ttk.Frame(notebook, padding=10)

        notebook.add(click_tab, text="Click")
        notebook.add(color_tab, text="Color Trigger")
        notebook.add(safety_tab, text="Safety")
        notebook.add(hotkey_profile_tab, text="Hotkeys & Profiles")

        self._build_click_tab(click_tab)
        self._build_color_tab(color_tab)
        self._build_safety_tab(safety_tab)
        self._build_hotkeys_profiles_tab(hotkey_profile_tab)

        controls = ttk.Frame(container)
        controls.pack(fill="x", pady=(8, 2))

        ttk.Button(controls, text="Start / Stop", command=self.toggle_running).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(controls, text="Pause / Resume", command=self.toggle_paused).pack(
            side="left"
        )

        ttk.Label(container, textvariable=self.status_var, foreground="#1e3a8a").pack(
            anchor="w", pady=(6, 0)
        )

    def _build_click_tab(self, tab: ttk.Frame) -> None:
        action_frame = ttk.LabelFrame(tab, text="Input Action", padding=10)
        action_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(action_frame, text="Action type:").grid(row=0, column=0, sticky="w", pady=3)
        action_combo = ttk.Combobox(
            action_frame,
            textvariable=self.action_type_var,
            values=["mouse", "keyboard"],
            state="readonly",
            width=14,
        )
        action_combo.grid(row=0, column=1, sticky="w", pady=3)
        action_combo.bind("<<ComboboxSelected>>", self._on_action_type_changed)

        self.mouse_button_label = ttk.Label(action_frame, text="Mouse button:")
        self.mouse_button_label.grid(row=1, column=0, sticky="w", pady=3)
        self.mouse_button_combo = ttk.Combobox(
            action_frame,
            textvariable=self.button_var,
            values=["left", "right", "middle"],
            state="readonly",
            width=14,
        )
        self.mouse_button_combo.grid(row=1, column=1, sticky="w", pady=3)

        self.keyboard_key_label = ttk.Label(action_frame, text="Keyboard key:")
        self.keyboard_key_label.grid(row=2, column=0, sticky="w", pady=3)
        self.keyboard_key_entry = ttk.Entry(action_frame, textvariable=self.keyboard_key_var, width=16)
        self.keyboard_key_entry.grid(row=2, column=1, sticky="w", pady=3)

        behavior_frame = ttk.LabelFrame(tab, text="Behavior", padding=10)
        behavior_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(behavior_frame, text="Click style:").grid(row=0, column=0, sticky="w", pady=3)
        click_style_combo = ttk.Combobox(
            behavior_frame,
            textvariable=self.click_style_var,
            values=["tap", "hold"],
            state="readonly",
            width=14,
        )
        click_style_combo.grid(row=0, column=1, sticky="w", pady=3)
        click_style_combo.bind("<<ComboboxSelected>>", self._on_click_style_changed)

        self.hold_duration_label = ttk.Label(behavior_frame, text="Hold duration (s):")
        self.hold_duration_label.grid(row=1, column=0, sticky="w", pady=3)
        self.hold_duration_entry = ttk.Entry(behavior_frame, textvariable=self.hold_duration_var, width=16)
        self.hold_duration_entry.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(behavior_frame, text="Burst count:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(behavior_frame, textvariable=self.burst_count_var, width=16).grid(
            row=2, column=1, sticky="w", pady=3
        )

        ttk.Label(behavior_frame, text="Gap between burst actions (s):").grid(
            row=3, column=0, sticky="w", pady=3
        )
        ttk.Entry(behavior_frame, textvariable=self.burst_gap_var, width=16).grid(
            row=3, column=1, sticky="w", pady=3
        )

        ttk.Label(
            behavior_frame,
            text="Double-click = burst count 2",
            foreground="#4b5563",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(3, 0))

        timing_frame = ttk.LabelFrame(tab, text="Timing", padding=10)
        timing_frame.grid(row=2, column=0, sticky="ew")

        ttk.Label(timing_frame, text="Base interval (s):").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(timing_frame, textvariable=self.interval_var, width=16).grid(
            row=0, column=1, sticky="w", pady=3
        )

        ttk.Checkbutton(
            timing_frame,
            text="Randomize interval",
            variable=self.randomize_interval_var,
            command=self._sync_timing_controls,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 4))

        self.interval_min_label = ttk.Label(timing_frame, text="Random min (s):")
        self.interval_min_label.grid(row=2, column=0, sticky="w", pady=3)
        self.interval_min_entry = ttk.Entry(timing_frame, textvariable=self.interval_min_var, width=16)
        self.interval_min_entry.grid(row=2, column=1, sticky="w", pady=3)

        self.interval_max_label = ttk.Label(timing_frame, text="Random max (s):")
        self.interval_max_label.grid(row=3, column=0, sticky="w", pady=3)
        self.interval_max_entry = ttk.Entry(timing_frame, textvariable=self.interval_max_var, width=16)
        self.interval_max_entry.grid(row=3, column=1, sticky="w", pady=3)

        ttk.Checkbutton(
            timing_frame,
            text="Enable anti-detection timing model",
            variable=self.anti_detection_enabled_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Label(timing_frame, text="Jitter (%):").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Entry(timing_frame, textvariable=self.anti_detection_jitter_pct_var, width=16).grid(
            row=5, column=1, sticky="w", pady=2
        )
        ttk.Label(timing_frame, text="Micro-pause chance (%):").grid(row=6, column=0, sticky="w", pady=2)
        ttk.Entry(timing_frame, textvariable=self.anti_detection_pause_chance_var, width=16).grid(
            row=6, column=1, sticky="w", pady=2
        )
        ttk.Label(timing_frame, text="Max micro-pause (s):").grid(row=7, column=0, sticky="w", pady=2)
        ttk.Entry(timing_frame, textvariable=self.anti_detection_max_pause_var, width=16).grid(
            row=7, column=1, sticky="w", pady=2
        )

        macro_frame = ttk.LabelFrame(tab, text="Macro / Recording", padding=10)
        macro_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        ttk.Checkbutton(
            macro_frame,
            text="Use selected recording instead of single click action",
            variable=self.use_macro_recording_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=2)

        ttk.Label(macro_frame, text="Selected recording:").grid(row=1, column=0, sticky="w", pady=3)
        self.recording_combo = ttk.Combobox(
            macro_frame,
            textvariable=self.selected_recording_var,
            values=[],
            state="readonly",
            width=28,
        )
        self.recording_combo.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Button(macro_frame, text="Play once", command=self._play_selected_recording_once).grid(
            row=1, column=2, sticky="w", padx=(8, 0), pady=3
        )
        ttk.Button(macro_frame, text="Refresh", command=self._refresh_recording_list).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=3
        )

        ttk.Label(macro_frame, text="Macro speed multiplier:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(macro_frame, textvariable=self.macro_speed_var, width=16).grid(
            row=2, column=1, sticky="w", pady=3
        )

        ttk.Label(macro_frame, text="Save recording as:").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(macro_frame, textvariable=self.recording_name_var, width=30).grid(
            row=3, column=1, sticky="w", pady=3
        )
        ttk.Button(macro_frame, text="Save temp as named", command=self._save_temp_recording_as_named).grid(
            row=3, column=2, sticky="w", padx=(8, 0), pady=3
        )
        ttk.Button(macro_frame, text="Delete selected", command=self._delete_selected_recording).grid(
            row=3, column=3, sticky="w", padx=(6, 0), pady=3
        )
        ttk.Button(macro_frame, text="Toggle recording now", command=self._toggle_recording_hotkey).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

    def _build_color_tab(self, tab: ttk.Frame) -> None:
        header_row = ttk.Frame(tab)
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        ttk.Checkbutton(
            header_row,
            text="Enable color trigger",
            variable=self.use_color_check_var,
        ).pack(side="left")

        ttk.Label(header_row, text="Rule logic:").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            header_row,
            textvariable=self.condition_logic_mode_var,
            values=["and", "or"],
            state="readonly",
            width=6,
        ).pack(side="left")

        self.color_toggle_button = ttk.Button(
            header_row,
            text="Show color options",
            command=self._toggle_color_options,
        )
        self.color_toggle_button.pack(side="right")

        self.color_options_frame = ttk.Frame(tab)
        self.color_options_frame.grid(row=1, column=0, sticky="nsew")

        color_target_frame = ttk.LabelFrame(self.color_options_frame, text="Target", padding=10)
        color_target_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(color_target_frame, text="Target color (hex):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        ttk.Entry(color_target_frame, textvariable=self.target_color_var, width=16).grid(
            row=0, column=1, sticky="w", pady=3
        )

        self.inkdrop_start_button = ttk.Button(
            color_target_frame,
            text="Start inkdropper",
            command=self._start_inkdropper,
        )
        self.inkdrop_start_button.grid(row=0, column=2, sticky="w", pady=3, padx=(8, 0))

        ttk.Label(color_target_frame, text="Preview:").grid(row=1, column=0, sticky="w", pady=3)
        self.color_preview_swatch = tk.Label(
            color_target_frame,
            width=8,
            height=1,
            relief="solid",
            bd=1,
            bg="#ffffff",
        )
        self.color_preview_swatch.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(color_target_frame, textvariable=self.color_preview_text_var).grid(
            row=1, column=2, sticky="w", pady=3, padx=(8, 0)
        )

        ttk.Label(color_target_frame, text="Tolerance (0-255):").grid(
            row=2, column=0, sticky="w", pady=3
        )
        ttk.Entry(color_target_frame, textvariable=self.tolerance_var, width=16).grid(
            row=2, column=1, sticky="w", pady=3
        )

        ttk.Label(color_target_frame, text="Inkdrop lock key:").grid(
            row=3, column=0, sticky="w", pady=3
        )
        ttk.Entry(color_target_frame, textvariable=self.inkdrop_lock_key_var, width=16).grid(
            row=3, column=1, sticky="w", pady=3
        )

        ttk.Label(
            color_target_frame,
            text="Hover any window and press lock key to capture color",
            foreground="#4b5563",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(3, 0))

        ttk.Checkbutton(
            color_target_frame,
            text="Edge-trigger mode (fire only on non-match -> match transition)",
            variable=self.edge_trigger_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))

        sample_frame = ttk.LabelFrame(self.color_options_frame, text="Sampling Source", padding=10)
        sample_frame.grid(row=1, column=0, sticky="ew")

        ttk.Label(sample_frame, text="Sample mode:").grid(row=0, column=0, sticky="w", pady=3)
        sample_mode_combo = ttk.Combobox(
            sample_frame,
            textvariable=self.color_sample_mode_var,
            values=["cursor", "point", "region"],
            state="readonly",
            width=14,
        )
        sample_mode_combo.grid(row=0, column=1, sticky="w", pady=3)
        sample_mode_combo.bind("<<ComboboxSelected>>", self._on_color_sample_mode_changed)

        ttk.Label(sample_frame, text="Monitor:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(
            sample_frame,
            textvariable=self.monitor_var,
            values=list(self.monitor_options.keys()),
            state="readonly",
            width=34,
        ).grid(row=1, column=1, columnspan=3, sticky="w", pady=3)

        point_label = ttk.Label(sample_frame, text="Point X / Y:")
        point_label.grid(row=2, column=0, sticky="w", pady=3)
        point_x_entry = ttk.Entry(sample_frame, textvariable=self.point_x_var, width=8)
        point_x_entry.grid(row=2, column=1, sticky="w", pady=3)
        point_y_entry = ttk.Entry(sample_frame, textvariable=self.point_y_var, width=8)
        point_y_entry.grid(row=2, column=2, sticky="w", pady=3, padx=(4, 0))
        point_cursor_btn = ttk.Button(
            sample_frame,
            text="Use cursor",
            command=self._set_point_from_cursor,
        )
        point_cursor_btn.grid(row=2, column=3, sticky="w", pady=3, padx=(8, 0))

        region_label = ttk.Label(sample_frame, text="Region x1,y1,x2,y2:")
        region_label.grid(row=3, column=0, sticky="w", pady=3)
        region_x1_entry = ttk.Entry(sample_frame, textvariable=self.region_x1_var, width=8)
        region_x1_entry.grid(row=3, column=1, sticky="w", pady=3)
        region_y1_entry = ttk.Entry(sample_frame, textvariable=self.region_y1_var, width=8)
        region_y1_entry.grid(row=3, column=2, sticky="w", pady=3, padx=(4, 0))

        region_x2_entry = ttk.Entry(sample_frame, textvariable=self.region_x2_var, width=8)
        region_x2_entry.grid(row=4, column=1, sticky="w", pady=3)
        region_y2_entry = ttk.Entry(sample_frame, textvariable=self.region_y2_var, width=8)
        region_y2_entry.grid(row=4, column=2, sticky="w", pady=3, padx=(4, 0))

        ttk.Label(sample_frame, text="Quick region size:").grid(row=5, column=0, sticky="w", pady=3)
        region_size_entry = ttk.Entry(sample_frame, textvariable=self.region_size_var, width=8)
        region_size_entry.grid(row=5, column=1, sticky="w", pady=3)
        region_cursor_btn = ttk.Button(
            sample_frame,
            text="Center at cursor",
            command=self._set_region_around_cursor,
        )
        region_cursor_btn.grid(row=5, column=3, sticky="w", pady=3, padx=(8, 0))

        self.crosshair_button = ttk.Button(
            sample_frame,
            text="Show crosshair",
            command=self._toggle_crosshair,
        )
        self.crosshair_button.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        window_rule_frame = ttk.LabelFrame(self.color_options_frame, text="Window Binding Rule", padding=10)
        window_rule_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            window_rule_frame,
            text="Enable active-window title rule",
            variable=self.window_binding_enabled_var,
            command=self._sync_rule_controls,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(window_rule_frame, text="Title contains:").grid(row=1, column=0, sticky="w", pady=3)
        self.window_rule_entry = ttk.Entry(window_rule_frame, textvariable=self.window_title_rule_var, width=36)
        self.window_rule_entry.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Button(window_rule_frame, text="Use current window", command=self._capture_current_window_title).grid(
            row=1, column=2, sticky="w", padx=(8, 0), pady=3
        )

        time_rule_frame = ttk.LabelFrame(self.color_options_frame, text="Time Window Rule", padding=10)
        time_rule_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            time_rule_frame,
            text="Enable local time window",
            variable=self.time_window_enabled_var,
            command=self._sync_rule_controls,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(time_rule_frame, text="Start HH:MM").grid(row=1, column=0, sticky="w", pady=3)
        self.time_start_entry = ttk.Entry(time_rule_frame, textvariable=self.time_window_start_var, width=10)
        self.time_start_entry.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(time_rule_frame, text="End HH:MM").grid(row=1, column=2, sticky="w", pady=3, padx=(12, 0))
        self.time_end_entry = ttk.Entry(time_rule_frame, textvariable=self.time_window_end_var, width=10)
        self.time_end_entry.grid(row=1, column=3, sticky="w", pady=3)

        history_frame = ttk.LabelFrame(self.color_options_frame, text="Pixel History", padding=10)
        history_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            history_frame,
            text="Enable history panel",
            variable=self.pixel_history_enabled_var,
        ).grid(row=0, column=0, sticky="w", pady=2)
        self.pixel_history_listbox = tk.Listbox(history_frame, height=7, width=44)
        self.pixel_history_listbox.grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(history_frame, text="Clear history", command=self._clear_pixel_history).grid(
            row=2, column=0, sticky="w"
        )

        self.point_widgets = [point_label, point_x_entry, point_y_entry, point_cursor_btn]
        self.region_widgets = [
            region_label,
            region_x1_entry,
            region_y1_entry,
            region_x2_entry,
            region_y2_entry,
            region_size_entry,
            region_cursor_btn,
        ]

    def _build_safety_tab(self, tab: ttk.Frame) -> None:
        timing_frame = ttk.LabelFrame(tab, text="Start Delay", padding=10)
        timing_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(timing_frame, text="Delay before start (s):").grid(
            row=0, column=0, sticky="w", pady=3
        )
        ttk.Entry(timing_frame, textvariable=self.start_delay_var, width=16).grid(
            row=0, column=1, sticky="w", pady=3
        )

        safety_frame = ttk.LabelFrame(tab, text="Safety Limits", padding=10)
        safety_frame.grid(row=1, column=0, sticky="ew")

        ttk.Checkbutton(
            safety_frame,
            text="Stop after N actions",
            variable=self.stop_after_clicks_enabled_var,
            command=self._sync_safety_controls,
        ).grid(row=0, column=0, sticky="w", pady=3)

        self.stop_clicks_entry = ttk.Entry(safety_frame, textvariable=self.stop_after_clicks_var, width=16)
        self.stop_clicks_entry.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Checkbutton(
            safety_frame,
            text="Stop after N seconds",
            variable=self.stop_after_seconds_enabled_var,
            command=self._sync_safety_controls,
        ).grid(row=1, column=0, sticky="w", pady=3)

        self.stop_seconds_entry = ttk.Entry(safety_frame, textvariable=self.stop_after_seconds_var, width=16)
        self.stop_seconds_entry.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(
            safety_frame,
            text="Action counter includes burst actions",
            foreground="#4b5563",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _build_hotkeys_profiles_tab(self, tab: ttk.Frame) -> None:
        hotkey_frame = ttk.LabelFrame(tab, text="Hotkeys", padding=10)
        hotkey_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(hotkey_frame, text="Start/Stop hotkey:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(hotkey_frame, textvariable=self.start_stop_hotkey_var, width=16).grid(
            row=0, column=1, sticky="w", pady=3
        )

        ttk.Label(hotkey_frame, text="Pause/Resume hotkey:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(hotkey_frame, textvariable=self.pause_hotkey_var, width=16).grid(
            row=1, column=1, sticky="w", pady=3
        )

        ttk.Label(hotkey_frame, text="Record toggle hotkey:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(hotkey_frame, textvariable=self.record_toggle_hotkey_var, width=16).grid(
            row=2, column=1, sticky="w", pady=3
        )

        ttk.Label(hotkey_frame, text="Play recording hotkey:").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(hotkey_frame, textvariable=self.play_recording_hotkey_var, width=16).grid(
            row=3, column=1, sticky="w", pady=3
        )

        ttk.Button(hotkey_frame, text="Apply hotkeys", command=self._start_hotkeys).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        profile_frame = ttk.LabelFrame(tab, text="Profiles", padding=10)
        profile_frame.grid(row=1, column=0, sticky="ew")

        ttk.Label(profile_frame, text="Profile:").grid(row=0, column=0, sticky="w", pady=3)
        self.profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.profile_select_var,
            values=[],
            state="readonly",
            width=28,
        )
        self.profile_combo.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Button(profile_frame, text="Load", command=self._load_selected_profile).grid(
            row=0, column=2, sticky="w", padx=(8, 0), pady=3
        )
        ttk.Button(profile_frame, text="Delete", command=self._delete_selected_profile).grid(
            row=0, column=3, sticky="w", padx=(6, 0), pady=3
        )

        ttk.Label(profile_frame, text="Save as:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(profile_frame, textvariable=self.profile_name_var, width=30).grid(
            row=1, column=1, sticky="w", pady=3
        )

        ttk.Button(profile_frame, text="Save profile", command=self._save_profile).grid(
            row=1, column=2, sticky="w", padx=(8, 0), pady=3
        )
        ttk.Button(profile_frame, text="Refresh", command=self._refresh_profile_list).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=3
        )

        ttk.Checkbutton(
            profile_frame,
            text="Apply profile-specific hotkeys when loading profile",
            variable=self.profile_hotkeys_enabled_var,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        ttk.Label(
            profile_frame,
            text=f"Profiles file: {self.profile_path}",
            foreground="#4b5563",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        testing_frame = ttk.LabelFrame(tab, text="Testing", padding=10)
        testing_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            testing_frame,
            text="Open a standalone playground for clicks, inkdrop colors, keys, and recording.",
            foreground="#4b5563",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Button(
            testing_frame,
            text="Open test window",
            command=self._open_test_window,
        ).grid(row=1, column=0, sticky="w")

    def _open_test_window(self) -> None:
        if self.test_window is not None:
            try:
                if self.test_window.winfo_exists():
                    self.test_window.deiconify()
                    self.test_window.lift()
                    self.test_window.focus_force()
                    return
            except tk.TclError:
                self.test_window = None

        window = tk.Toplevel(self.root)
        window.title("Autoclicker Testing Window")
        window.geometry("960x780")
        window.minsize(760, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_test_window)
        window.bind("<KeyPress>", self._on_test_window_key_press, add="+")
        self.test_window = window

        self._reset_test_window_state()

        outer = ttk.Frame(window)
        outer.pack(fill="both", expand=True)

        scroll_canvas = tk.Canvas(outer, highlightthickness=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        y_scroll = ttk.Scrollbar(outer, orient="vertical", command=scroll_canvas.yview)
        y_scroll.pack(side="right", fill="y")
        scroll_canvas.configure(yscrollcommand=y_scroll.set)

        container = ttk.Frame(scroll_canvas, padding=12)
        scroll_window_id = scroll_canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_content_resize(_event: tk.Event) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _on_canvas_resize(event: tk.Event) -> None:
            scroll_canvas.itemconfigure(scroll_window_id, width=event.width)

        def _on_mouse_wheel(event: tk.Event) -> None:
            if event.delta == 0:
                return
            scroll_canvas.yview_scroll(int(-event.delta / 120), "units")

        container.bind("<Configure>", _on_content_resize, add="+")
        scroll_canvas.bind("<Configure>", _on_canvas_resize, add="+")
        window.bind("<MouseWheel>", _on_mouse_wheel, add="+")

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(4, weight=1)

        ttk.Label(
            container,
            text="Testing Playground",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            container,
            text="Use this window to verify clicking, inkdrop color checks, key counting, and recording behavior.",
            foreground="#4b5563",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        click_frame = ttk.LabelFrame(container, text="Autoclick Button Targets", padding=10)
        click_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))

        ttk.Button(
            click_frame,
            text="Test Button 1",
            command=lambda: self._increment_test_button_counter(1),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(click_frame, textvariable=self.test_button_one_var).grid(
            row=0, column=1, sticky="w", pady=4
        )

        ttk.Button(
            click_frame,
            text="Test Button 2",
            command=lambda: self._increment_test_button_counter(2),
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(click_frame, textvariable=self.test_button_two_var).grid(
            row=1, column=1, sticky="w", pady=4
        )

        color_frame = ttk.LabelFrame(container, text="Inkdrop Color Wheel", padding=10)
        color_frame.grid(row=2, column=1, sticky="nsew", pady=(0, 8))

        wheel_size = 240
        self.test_color_wheel_image = self._create_test_color_wheel_image(wheel_size)
        wheel_canvas = tk.Canvas(
            color_frame,
            width=wheel_size,
            height=wheel_size,
            bg="white",
            highlightthickness=1,
            highlightbackground="#d1d5db",
        )
        wheel_canvas.grid(row=0, column=0, sticky="w")
        wheel_canvas.create_image(wheel_size // 2, wheel_size // 2, image=self.test_color_wheel_image)

        self.test_center_button = tk.Button(
            wheel_canvas,
            command=self._cycle_test_center_color,
            relief="raised",
            font=("Segoe UI", 9, "bold"),
            fg="white",
            bd=1,
        )
        wheel_canvas.create_window(
            wheel_size // 2,
            wheel_size // 2,
            width=120,
            height=46,
            window=self.test_center_button,
        )
        self._apply_test_center_color()

        ttk.Label(color_frame, textvariable=self.test_center_counter_var).grid(
            row=1, column=0, sticky="w", pady=(6, 2)
        )
        ttk.Label(color_frame, textvariable=self.test_center_color_var).grid(
            row=2, column=0, sticky="w"
        )
        auto_color_frame = ttk.Frame(color_frame)
        auto_color_frame.grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(auto_color_frame, text="Random interval (s):").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(
            auto_color_frame,
            textvariable=self.test_center_random_interval_var,
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=(6, 8))
        self.test_center_auto_toggle_button = ttk.Button(
            auto_color_frame,
            command=self._toggle_test_center_auto_color,
            width=20,
        )
        self.test_center_auto_toggle_button.grid(row=0, column=2, sticky="w")
        ttk.Label(color_frame, textvariable=self.test_center_auto_status_var).grid(
            row=4, column=0, sticky="w", pady=(4, 0)
        )
        self._sync_test_center_auto_toggle_button()

        letter_frame = ttk.LabelFrame(container, text="Letter Counter", padding=10)
        letter_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(
            letter_frame,
            text="Click into this window and type letters. Every A-Z keypress increments the counter.",
            foreground="#4b5563",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(letter_frame, textvariable=self.test_letter_total_var).grid(
            row=1, column=0, sticky="w", pady=2
        )
        ttk.Label(letter_frame, textvariable=self.test_letter_last_var).grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Label(letter_frame, textvariable=self.test_letter_breakdown_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(2, 0)
        )

        obstacle_frame = ttk.LabelFrame(container, text="Recording Obstacle Course", padding=10)
        obstacle_frame.grid(row=4, column=0, columnspan=2, sticky="nsew")
        obstacle_frame.columnconfigure(0, weight=0)
        obstacle_frame.columnconfigure(1, weight=0)
        obstacle_frame.columnconfigure(2, weight=1)
        obstacle_frame.rowconfigure(5, weight=1)

        ttk.Label(
            obstacle_frame,
            text="Interact with controls below to generate varied recording events.",
            foreground="#4b5563",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(
            obstacle_frame,
            textvariable=self.test_obstacle_counter_var,
            foreground="#1e3a8a",
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(obstacle_frame, textvariable=self.test_obstacle_last_var).grid(
            row=1, column=2, sticky="w"
        )

        ttk.Button(
            obstacle_frame,
            text="Obstacle Button A",
            command=lambda: self._increment_test_obstacle_counter("Button A"),
        ).grid(row=2, column=0, sticky="w", pady=(6, 2))
        ttk.Button(
            obstacle_frame,
            text="Obstacle Button B",
            command=lambda: self._increment_test_obstacle_counter("Button B"),
        ).grid(row=2, column=1, sticky="w", pady=(6, 2), padx=(6, 0))
        ttk.Button(
            obstacle_frame,
            text="Obstacle Button C",
            command=lambda: self._increment_test_obstacle_counter("Button C"),
        ).grid(row=2, column=2, sticky="w", pady=(6, 2), padx=(6, 0))

        entry_one = ttk.Entry(obstacle_frame, width=26)
        entry_one.grid(row=3, column=0, sticky="w", pady=(6, 2))
        entry_one.bind(
            "<KeyRelease>",
            lambda _event: self._increment_test_obstacle_counter("Entry typing"),
            add="+",
        )

        combo = ttk.Combobox(
            obstacle_frame,
            values=["option-1", "option-2", "option-3"],
            state="readonly",
            width=14,
        )
        combo.grid(row=3, column=1, sticky="w", pady=(6, 2), padx=(6, 0))
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._increment_test_obstacle_counter("Combobox select"),
            add="+",
        )

        spinbox = tk.Spinbox(
            obstacle_frame,
            from_=0,
            to=50,
            width=8,
            command=lambda: self._increment_test_obstacle_counter("Spinbox step"),
        )
        spinbox.grid(row=3, column=2, sticky="w", pady=(6, 2), padx=(6, 0))

        ttk.Checkbutton(
            obstacle_frame,
            text="Toggle checkpoint",
            variable=self.test_obstacle_toggle_var,
            command=lambda: self._increment_test_obstacle_counter("Checkbutton toggle"),
        ).grid(row=4, column=0, sticky="w", pady=(8, 2))

        slider = ttk.Scale(
            obstacle_frame,
            from_=0,
            to=100,
            orient="horizontal",
            command=lambda _value: self._increment_test_obstacle_counter("Slider move"),
        )
        slider.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 2))

        text_box = tk.Text(obstacle_frame, height=5, width=54)
        text_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        text_box.bind(
            "<KeyRelease>",
            lambda _event: self._increment_test_obstacle_counter("Text edit"),
            add="+",
        )

        entry_one.focus_set()
        self._set_status("Testing window opened")

    def _close_test_window(self) -> None:
        window = self.test_window
        self.test_window = None
        self.test_center_button = None
        self.test_center_auto_toggle_button = None
        self.test_color_wheel_image = None
        self._cancel_test_center_auto_job()
        self.test_center_auto_color_enabled = False

        if window is None:
            return

        try:
            window.destroy()
        except tk.TclError:
            pass

    def _reset_test_window_state(self) -> None:
        self.test_button_one_count = 0
        self.test_button_two_count = 0
        self.test_center_click_count = 0
        self.test_center_current_color = "#1f7a8c"
        self.test_center_auto_color_enabled = False
        self._cancel_test_center_auto_job()
        self.test_letter_total_count = 0
        self.test_letter_counts.clear()
        self.test_obstacle_count = 0
        self.test_obstacle_toggle_var.set(False)

        self.test_button_one_var.set("Button 1 clicks: 0")
        self.test_button_two_var.set("Button 2 clicks: 0")
        self.test_center_counter_var.set("Center button clicks: 0")
        self.test_center_color_var.set("Current center color: #1F7A8C")
        self.test_center_random_interval_var.set("0.75")
        self.test_center_auto_status_var.set("Auto random color: off")
        self.test_letter_total_var.set("Letters pressed: 0")
        self.test_letter_last_var.set("Last letter: none")
        self.test_letter_breakdown_var.set("Breakdown: none")
        self.test_obstacle_counter_var.set("Obstacle interactions: 0")
        self.test_obstacle_last_var.set("Last obstacle action: none")

    def _increment_test_button_counter(self, button_index: int) -> None:
        if button_index == 1:
            self.test_button_one_count += 1
            self.test_button_one_var.set(f"Button 1 clicks: {self.test_button_one_count}")
            return

        self.test_button_two_count += 1
        self.test_button_two_var.set(f"Button 2 clicks: {self.test_button_two_count}")

    def _create_test_color_wheel_image(self, size: int) -> ImageTk.PhotoImage:
        image = Image.new("RGB", (size, size), (255, 255, 255))
        pixels = image.load()

        center = (size - 1) / 2.0
        outer_radius = center - 1
        inner_radius = outer_radius * 0.33

        for y in range(size):
            dy = y - center
            for x in range(size):
                dx = x - center
                distance = math.hypot(dx, dy)
                if distance > outer_radius:
                    continue
                if distance < inner_radius:
                    pixels[x, y] = (245, 245, 245)
                    continue

                hue = ((math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0) / 360.0
                saturation = min(1.0, max(0.0, distance / outer_radius))
                red, green, blue = colorsys.hsv_to_rgb(hue, saturation, 1.0)
                pixels[x, y] = (int(red * 255), int(green * 255), int(blue * 255))

        return ImageTk.PhotoImage(image)

    def _cycle_test_center_color(self) -> None:
        self.test_center_click_count += 1
        self.test_center_current_color = self._generate_random_test_color()
        self._apply_test_center_color()

    def _apply_test_center_color(self) -> None:
        color = self.test_center_current_color
        luminance = (0.299 * int(color[1:3], 16)) + (0.587 * int(color[3:5], 16)) + (0.114 * int(color[5:7], 16))
        text_color = "black" if luminance > 150 else "white"
        if self.test_center_button is not None:
            self.test_center_button.configure(
                text=f"Random Color\n{self.test_center_click_count} clicks",
                bg=color,
                activebackground=color,
                fg=text_color,
                activeforeground=text_color,
            )

        self.test_center_counter_var.set(f"Center button clicks: {self.test_center_click_count}")
        self.test_center_color_var.set(f"Current center color: {color.upper()}")

    def _generate_random_test_color(self) -> str:
        return f"#{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}"

    def _parse_test_center_interval_seconds(self) -> float | None:
        try:
            seconds = float(self.test_center_random_interval_var.get().strip())
        except ValueError:
            self._set_status("Test center random interval must be a number.")
            return None
        if seconds < 0.05:
            self._set_status("Test center random interval must be at least 0.05 seconds.")
            return None
        return seconds

    def _sync_test_center_auto_toggle_button(self) -> None:
        if self.test_center_auto_toggle_button is None:
            return
        if self.test_center_auto_color_enabled:
            self.test_center_auto_toggle_button.configure(text="Stop random colors")
            return
        self.test_center_auto_toggle_button.configure(text="Start random colors")

    def _toggle_test_center_auto_color(self) -> None:
        if self.test_center_auto_color_enabled:
            self.test_center_auto_color_enabled = False
            self._cancel_test_center_auto_job()
            self.test_center_auto_status_var.set("Auto random color: off")
            self._sync_test_center_auto_toggle_button()
            return

        interval_seconds = self._parse_test_center_interval_seconds()
        if interval_seconds is None:
            return

        self.test_center_auto_color_enabled = True
        self.test_center_auto_status_var.set(
            f"Auto random color: on ({interval_seconds:.2f}s interval)"
        )
        self._sync_test_center_auto_toggle_button()
        self._schedule_test_center_auto_color(interval_seconds)

    def _schedule_test_center_auto_color(self, interval_seconds: float | None = None) -> None:
        if not self.test_center_auto_color_enabled:
            return

        if interval_seconds is None:
            interval_seconds = self._parse_test_center_interval_seconds()
            if interval_seconds is None:
                self.test_center_auto_color_enabled = False
                self.test_center_auto_status_var.set("Auto random color: off")
                self._sync_test_center_auto_toggle_button()
                return

        self._cancel_test_center_auto_job()
        delay_ms = max(50, int(interval_seconds * 1000))
        self.test_center_auto_after_id = self.root.after(delay_ms, self._run_test_center_auto_color)

    def _run_test_center_auto_color(self) -> None:
        self.test_center_auto_after_id = None
        if not self.test_center_auto_color_enabled or self.test_window is None:
            return

        self.test_center_current_color = self._generate_random_test_color()
        self._apply_test_center_color()
        self._schedule_test_center_auto_color()

    def _cancel_test_center_auto_job(self) -> None:
        if self.test_center_auto_after_id is None:
            return
        try:
            self.root.after_cancel(self.test_center_auto_after_id)
        except tk.TclError:
            pass
        self.test_center_auto_after_id = None

    def _on_test_window_key_press(self, event: tk.Event) -> None:
        char = event.char
        if not char or len(char) != 1:
            return
        if not char.isalpha():
            return

        letter = char.lower()
        self.test_letter_total_count += 1
        self.test_letter_counts[letter] = self.test_letter_counts.get(letter, 0) + 1
        self.test_letter_total_var.set(f"Letters pressed: {self.test_letter_total_count}")
        self.test_letter_last_var.set(f"Last letter: {letter.upper()}")

        top_letters = sorted(self.test_letter_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        breakdown = ", ".join(f"{token.upper()}:{count}" for token, count in top_letters)
        self.test_letter_breakdown_var.set(f"Breakdown: {breakdown or 'none'}")

    def _increment_test_obstacle_counter(self, action_name: str) -> None:
        self.test_obstacle_count += 1
        self.test_obstacle_counter_var.set(f"Obstacle interactions: {self.test_obstacle_count}")
        self.test_obstacle_last_var.set(f"Last obstacle action: {action_name}")

    def _set_status(self, text: str) -> None:
        if threading.current_thread() is threading.main_thread():
            try:
                self.status_var.set(text)
            except tk.TclError:
                pass
            return

        try:
            self.root.after(0, lambda value=text: self.status_var.set(value))
        except tk.TclError:
            pass

    def _set_session_info(self, clicks: int, elapsed: float) -> None:
        text = f"Clicks: {clicks} | Elapsed: {elapsed:.1f}s"
        if threading.current_thread() is threading.main_thread():
            try:
                self.session_info_var.set(text)
            except tk.TclError:
                pass
            return

        try:
            self.root.after(0, lambda value=text: self.session_info_var.set(value))
        except tk.TclError:
            pass

    @staticmethod
    def _enable_dpi_awareness() -> None:
        if sys.platform != "win32":
            return

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass

        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    @staticmethod
    def _detect_monitors() -> dict[str, Rect | None]:
        options: dict[str, Rect | None] = {"All monitors": None}
        if sys.platform != "win32":
            return options

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong),
                ("szDevice", ctypes.c_wchar * 32),
            ]

        user32 = ctypes.windll.user32
        monitor_rects: list[Rect] = []

        monitor_enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        def callback(hmonitor: int, _hdc: int, _lprc: ctypes.POINTER(RECT), _lparam: int) -> int:
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                r = info.rcMonitor
                monitor_rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
            return 1

        try:
            user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
        except Exception:
            return options

        monitor_rects.sort(key=lambda rect: (rect[1], rect[0]))
        for idx, rect in enumerate(monitor_rects, start=1):
            x1, y1, x2, y2 = rect
            width = x2 - x1
            height = y2 - y1
            label = f"Monitor {idx} ({width}x{height} @ {x1},{y1})"
            options[label] = rect

        return options

    @staticmethod
    def _virtual_screen_bounds() -> Rect:
        if sys.platform != "win32":
            return 0, 0, 0, 0

        user32 = ctypes.windll.user32
        x = int(user32.GetSystemMetrics(76))
        y = int(user32.GetSystemMetrics(77))
        w = int(user32.GetSystemMetrics(78))
        h = int(user32.GetSystemMetrics(79))
        return x, y, x + w, y + h

    def _start_hotkeys(self) -> None:
        start_stop = self.start_stop_hotkey_var.get().strip().lower()
        pause = self.pause_hotkey_var.get().strip().lower()
        record_toggle = self.record_toggle_hotkey_var.get().strip().lower()
        play_recording = self.play_recording_hotkey_var.get().strip().lower()

        if not start_stop or not pause or not record_toggle or not play_recording:
            self._set_status("Hotkeys cannot be empty.")
            return

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        try:
            self.hotkey_listener = keyboard.GlobalHotKeys(
                {
                    start_stop: self.toggle_running,
                    pause: self.toggle_paused,
                    record_toggle: self._toggle_recording_hotkey,
                    play_recording: self._play_recording_hotkey,
                }
            )
            self.hotkey_listener.start()
            self._set_status(
                "Hotkeys active: "
                f"start/stop {start_stop}, pause {pause}, "
                f"record {record_toggle}, play {play_recording}"
            )
        except Exception as exc:
            self._set_status(f"Invalid hotkey format: {exc}")

    def _on_action_type_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_action_controls()

    def _on_click_style_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_hold_controls()

    def _on_color_sample_mode_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_color_mode_controls()

    def _sync_action_controls(self) -> None:
        if (
            self.mouse_button_label is None
            or self.mouse_button_combo is None
            or self.keyboard_key_label is None
            or self.keyboard_key_entry is None
        ):
            return

        if self.action_type_var.get().strip().lower() == "keyboard":
            self.mouse_button_label.grid_remove()
            self.mouse_button_combo.grid_remove()
            self.keyboard_key_label.grid()
            self.keyboard_key_entry.grid()
            return

        self.keyboard_key_label.grid_remove()
        self.keyboard_key_entry.grid_remove()
        self.mouse_button_label.grid()
        self.mouse_button_combo.grid()

    def _sync_hold_controls(self) -> None:
        if self.hold_duration_label is None or self.hold_duration_entry is None:
            return

        if self.click_style_var.get().strip().lower() == "hold":
            self.hold_duration_label.grid()
            self.hold_duration_entry.grid()
            return

        self.hold_duration_label.grid_remove()
        self.hold_duration_entry.grid_remove()

    def _sync_timing_controls(self) -> None:
        widgets = [
            self.interval_min_label,
            self.interval_min_entry,
            self.interval_max_label,
            self.interval_max_entry,
        ]
        if any(widget is None for widget in widgets):
            return

        if self.randomize_interval_var.get():
            for widget in widgets:
                widget.grid()
            return

        for widget in widgets:
            widget.grid_remove()

    def _sync_color_mode_controls(self) -> None:
        mode = self.color_sample_mode_var.get().strip().lower()

        if mode == "point":
            for widget in self.point_widgets:
                widget.grid()
            for widget in self.region_widgets:
                widget.grid_remove()
            return

        if mode == "region":
            for widget in self.point_widgets:
                widget.grid_remove()
            for widget in self.region_widgets:
                widget.grid()
            return

        for widget in self.point_widgets:
            widget.grid_remove()
        for widget in self.region_widgets:
            widget.grid_remove()

    def _sync_safety_controls(self) -> None:
        if self.stop_clicks_entry is not None:
            self.stop_clicks_entry.configure(
                state="normal" if self.stop_after_clicks_enabled_var.get() else "disabled"
            )
        if self.stop_seconds_entry is not None:
            self.stop_seconds_entry.configure(
                state="normal" if self.stop_after_seconds_enabled_var.get() else "disabled"
            )

    def _sync_rule_controls(self) -> None:
        if self.window_rule_entry is not None:
            self.window_rule_entry.configure(
                state="normal" if self.window_binding_enabled_var.get() else "disabled"
            )
        if self.time_start_entry is not None:
            self.time_start_entry.configure(
                state="normal" if self.time_window_enabled_var.get() else "disabled"
            )
        if self.time_end_entry is not None:
            self.time_end_entry.configure(
                state="normal" if self.time_window_enabled_var.get() else "disabled"
            )

    def _toggle_color_options(self) -> None:
        self._set_color_options_visible(not self.color_options_visible_var.get())

    def _set_color_options_visible(self, visible: bool) -> None:
        self.color_options_visible_var.set(visible)

        if self.color_toggle_button is not None:
            self.color_toggle_button.configure(
                text="Hide color options" if visible else "Show color options"
            )

        if self.color_options_frame is not None:
            if visible:
                self.color_options_frame.grid()
            else:
                self.color_options_frame.grid_remove()
                self._stop_inkdropper()
                self._stop_crosshair()

    @staticmethod
    def _current_window_title() -> str:
        if sys.platform != "win32":
            return ""

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""

            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value.strip()
        except Exception:
            return ""

    def _capture_current_window_title(self) -> None:
        title = self._current_window_title()
        if not title:
            self._set_status("No active window title found")
            return

        self.window_title_rule_var.set(title)
        self._set_status(f"Window title rule set to '{title}'")

    @staticmethod
    def _is_time_in_window(now_hhmm: str, start_hhmm: str, end_hhmm: str) -> bool:
        try:
            now_dt = datetime.strptime(now_hhmm, "%H:%M")
            start_dt = datetime.strptime(start_hhmm, "%H:%M")
            end_dt = datetime.strptime(end_hhmm, "%H:%M")
        except ValueError:
            return False

        now_m = now_dt.hour * 60 + now_dt.minute
        start_m = start_dt.hour * 60 + start_dt.minute
        end_m = end_dt.hour * 60 + end_dt.minute

        if start_m <= end_m:
            return start_m <= now_m <= end_m
        return now_m >= start_m or now_m <= end_m

    def _time_window_allows(self, start_hhmm: str, end_hhmm: str) -> bool:
        current = datetime.now().strftime("%H:%M")
        return self._is_time_in_window(current, start_hhmm, end_hhmm)

    def _append_pixel_history(self, pixel: tuple[int, int, int] | None, match: bool) -> None:
        if not self.pixel_history_enabled_var.get():
            return

        if pixel is None:
            entry = f"REGION {'MATCH' if match else 'MISS'}"
        else:
            entry = f"{pixel[0]:02X}{pixel[1]:02X}{pixel[2]:02X} {'MATCH' if match else 'MISS'}"
        self.pixel_history.append(entry)
        if len(self.pixel_history) > 40:
            self.pixel_history = self.pixel_history[-40:]

        if self.pixel_history_listbox is not None:
            self.pixel_history_listbox.delete(0, tk.END)
            for item in self.pixel_history[-12:]:
                self.pixel_history_listbox.insert(tk.END, item)

    def _clear_pixel_history(self) -> None:
        self.pixel_history = []
        if self.pixel_history_listbox is not None:
            self.pixel_history_listbox.delete(0, tk.END)

    @staticmethod
    def _normalize_recording_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                continue

            event_type = event.get("type")
            event_time = event.get("t")
            payload = event.get("payload")
            if not isinstance(event_type, str) or not isinstance(event_time, (int, float)):
                continue
            if not isinstance(payload, dict):
                continue

            normalized.append(
                {
                    "type": event_type,
                    "t": float(event_time),
                    "payload": payload,
                }
            )

        normalized.sort(key=lambda item: float(item["t"]))
        return normalized

    @staticmethod
    def _parse_keyboard_key(raw_key: str) -> keyboard.Key | keyboard.KeyCode | None:
        token = raw_key.strip().lower()
        if token.startswith("<") and token.endswith(">"):
            token = token[1:-1].strip()
        token = token.replace(" ", "").replace("-", "_")

        if len(token) == 1:
            return keyboard.KeyCode.from_char(token)

        key_map: dict[str, keyboard.Key] = {
            "space": keyboard.Key.space,
            "enter": keyboard.Key.enter,
            "return": keyboard.Key.enter,
            "tab": keyboard.Key.tab,
            "esc": keyboard.Key.esc,
            "escape": keyboard.Key.esc,
            "backspace": keyboard.Key.backspace,
            "delete": keyboard.Key.delete,
            "del": keyboard.Key.delete,
            "insert": keyboard.Key.insert,
            "home": keyboard.Key.home,
            "end": keyboard.Key.end,
            "page_up": keyboard.Key.page_up,
            "pageup": keyboard.Key.page_up,
            "pgup": keyboard.Key.page_up,
            "page_down": keyboard.Key.page_down,
            "pagedown": keyboard.Key.page_down,
            "pgdn": keyboard.Key.page_down,
            "up": keyboard.Key.up,
            "down": keyboard.Key.down,
            "left": keyboard.Key.left,
            "right": keyboard.Key.right,
            "shift": keyboard.Key.shift,
            "ctrl": keyboard.Key.ctrl,
            "control": keyboard.Key.ctrl,
            "alt": keyboard.Key.alt,
            "caps_lock": keyboard.Key.caps_lock,
            "capslock": keyboard.Key.caps_lock,
            "num_lock": keyboard.Key.num_lock,
            "numlock": keyboard.Key.num_lock,
            "print_screen": keyboard.Key.print_screen,
            "printscreen": keyboard.Key.print_screen,
            "scroll_lock": keyboard.Key.scroll_lock,
            "scrolllock": keyboard.Key.scroll_lock,
            "pause": keyboard.Key.pause,
            "menu": keyboard.Key.menu,
        }
        if token in key_map:
            return key_map[token]

        if token.startswith("f") and token[1:].isdigit():
            function_key_name = f"f{int(token[1:])}"
            if hasattr(keyboard.Key, function_key_name):
                return getattr(keyboard.Key, function_key_name)

        return None

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
        stripped = hex_color.strip().lstrip("#")
        if len(stripped) != 6:
            return None

        try:
            return tuple(int(stripped[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None

    def _on_target_color_change(self, *_: str) -> None:
        self._update_color_preview()

    def _update_color_preview(self) -> None:
        if self.color_preview_swatch is None:
            return

        rgb = self._hex_to_rgb(self.target_color_var.get())
        if rgb is None:
            self.color_preview_swatch.configure(bg="#d1d5db")
            self.color_preview_text_var.set("Invalid hex")
            return

        hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        self.color_preview_swatch.configure(bg=hex_color)
        self.color_preview_text_var.set(hex_color.upper())

    @staticmethod
    def _key_matches(
        pressed_key: keyboard.Key | keyboard.KeyCode,
        expected_key: keyboard.Key | keyboard.KeyCode,
    ) -> bool:
        if isinstance(pressed_key, keyboard.KeyCode) and isinstance(expected_key, keyboard.KeyCode):
            if pressed_key.char is None or expected_key.char is None:
                return False
            return pressed_key.char.lower() == expected_key.char.lower()

        return pressed_key == expected_key

    def _on_inkdrop_lock_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self.inkdropper_active or self.inkdrop_lock_key is None:
            return

        if self._key_matches(key, self.inkdrop_lock_key):
            try:
                self.root.after(0, self._lock_inkdropper_color_if_active)
            except tk.TclError:
                pass

    def _start_inkdrop_lock_listener(self) -> bool:
        parsed_key = self._parse_keyboard_key(self.inkdrop_lock_key_var.get())
        if parsed_key is None:
            self._set_status("Invalid inkdrop lock key. Use one key like s, enter, or f8.")
            return False

        self._stop_inkdrop_lock_listener()
        self.inkdrop_lock_key = parsed_key

        try:
            self.inkdrop_lock_listener = keyboard.Listener(on_press=self._on_inkdrop_lock_key_press)
            self.inkdrop_lock_listener.start()
            return True
        except Exception as exc:
            self._set_status(f"Failed to start inkdrop key listener: {exc}")
            self.inkdrop_lock_listener = None
            self.inkdrop_lock_key = None
            return False

    def _stop_inkdrop_lock_listener(self) -> None:
        if self.inkdrop_lock_listener is not None:
            self.inkdrop_lock_listener.stop()
            self.inkdrop_lock_listener = None
        self.inkdrop_lock_key = None

    def _start_inkdropper(self) -> None:
        if self.inkdropper_active:
            return

        if not self._start_inkdrop_lock_listener():
            return

        self.inkdropper_active = True
        if self.inkdrop_start_button is not None:
            self.inkdrop_start_button.configure(state="disabled")

        lock_key = self.inkdrop_lock_key_var.get().strip().lower()
        self._set_status(
            f"Inkdropper active: hover target color, then press {lock_key} to lock."
        )
        self._poll_hovered_color()

    def _poll_hovered_color(self) -> None:
        if not self.inkdropper_active:
            return

        pixel = self._pixel_under_cursor()
        if pixel is not None:
            hex_color = f"#{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}"
            self.target_color_var.set(hex_color)

        try:
            self.inkdrop_after_id = self.root.after(70, self._poll_hovered_color)
        except tk.TclError:
            self.inkdrop_after_id = None

    def _lock_inkdropper_color(self) -> None:
        if not self.inkdropper_active:
            self._set_status("Inkdropper is not active.")
            return

        locked_color = self.target_color_var.get().strip().upper()
        self._stop_inkdropper()
        self._set_status(f"Locked color {locked_color}")

    def _lock_inkdropper_color_if_active(self) -> None:
        if self.inkdropper_active:
            self._lock_inkdropper_color()

    def _stop_inkdropper(self) -> None:
        self.inkdropper_active = False
        if self.inkdrop_after_id is not None:
            try:
                self.root.after_cancel(self.inkdrop_after_id)
            except tk.TclError:
                pass
            self.inkdrop_after_id = None

        self._stop_inkdrop_lock_listener()
        if self.inkdrop_start_button is not None:
            self.inkdrop_start_button.configure(state="normal")

    @staticmethod
    def _button_to_token(button: Button) -> str:
        mapping = {
            Button.left: "left",
            Button.right: "right",
            Button.middle: "middle",
        }
        return mapping.get(button, "left")

    @staticmethod
    def _button_from_token(token: str) -> Button | None:
        mapping = {
            "left": Button.left,
            "right": Button.right,
            "middle": Button.middle,
        }
        return mapping.get(token.strip().lower())

    @staticmethod
    def _key_to_token(key: keyboard.Key | keyboard.KeyCode) -> str | None:
        if isinstance(key, keyboard.KeyCode):
            if key.char is None:
                return None
            return key.char.lower()

        if isinstance(key, keyboard.Key):
            return key.name.lower() if key.name else None

        return None

    def _record_event(self, event_type: str, payload: dict[str, object]) -> None:
        if not self.recording_active:
            return

        timestamp = time.monotonic() - self.recording_started_at
        self.recording_events.append(
            RecordingEvent(t=timestamp, type=event_type, payload=payload)
        )

    def _control_hotkey_tokens(self) -> set[str]:
        tokens: set[str] = set()
        for value in (
            self.start_stop_hotkey_var.get(),
            self.pause_hotkey_var.get(),
            self.record_toggle_hotkey_var.get(),
            self.play_recording_hotkey_var.get(),
        ):
            parsed = self._parse_keyboard_key(value)
            if parsed is None:
                continue
            token = self._key_to_token(parsed)
            if token:
                tokens.add(token)
        return tokens

    def _on_recording_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        token = self._key_to_token(key)
        if token is None:
            return

        if token in self._control_hotkey_tokens():
            return

        self._record_event("key_press", {"key": token})

    def _on_recording_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        token = self._key_to_token(key)
        if token is None:
            return

        if token in self._control_hotkey_tokens():
            return

        self._record_event("key_release", {"key": token})

    def _on_recording_mouse_move(self, x: float, y: float) -> None:
        now = time.monotonic()
        point = (int(x), int(y))
        if self.recording_last_move_pos == point and (now - self.recording_last_move_time) < 0.05:
            return

        self.recording_last_move_pos = point
        self.recording_last_move_time = now
        self._record_event("mouse_move", {"x": point[0], "y": point[1]})

    def _on_recording_mouse_click(
        self,
        x: float,
        y: float,
        button: Button,
        pressed: bool,
    ) -> None:
        token = self._button_to_token(button)
        self._record_event(
            "mouse_click",
            {
                "x": int(x),
                "y": int(y),
                "button": token,
                "pressed": bool(pressed),
            },
        )

    def _on_recording_mouse_scroll(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
    ) -> None:
        self._record_event(
            "mouse_scroll",
            {
                "x": int(x),
                "y": int(y),
                "dx": float(dx),
                "dy": float(dy),
            },
        )

    def _start_recording_capture(self) -> bool:
        if self.recording_active:
            return True

        self.recording_events = []
        self.recording_started_at = time.monotonic()
        self.recording_last_move_time = 0.0
        self.recording_last_move_pos = None

        try:
            self.recording_keyboard_listener = keyboard.Listener(
                on_press=self._on_recording_key_press,
                on_release=self._on_recording_key_release,
            )
            self.recording_mouse_listener = mouse.Listener(
                on_move=self._on_recording_mouse_move,
                on_click=self._on_recording_mouse_click,
                on_scroll=self._on_recording_mouse_scroll,
            )
            self.recording_keyboard_listener.start()
            self.recording_mouse_listener.start()
            self.recording_active = True
            self._set_status("Recording started. Press record hotkey again to stop/save temporary.")
            return True
        except Exception as exc:
            self.recording_keyboard_listener = None
            self.recording_mouse_listener = None
            self.recording_active = False
            self._set_status(f"Failed to start recording: {exc}")
            return False

    def _stop_recording_capture(self) -> None:
        if self.recording_keyboard_listener is not None:
            self.recording_keyboard_listener.stop()
            self.recording_keyboard_listener = None
        if self.recording_mouse_listener is not None:
            self.recording_mouse_listener.stop()
            self.recording_mouse_listener = None
        self.recording_active = False

    def _serialize_recording_events(self) -> list[dict[str, object]]:
        serialized: list[dict[str, object]] = []
        for event in self.recording_events:
            serialized.append(
                {
                    "t": round(event.t, 6),
                    "type": event.type,
                    "payload": dict(event.payload),
                }
            )
        return serialized

    def _toggle_recording_hotkey(self) -> None:
        if self.recording_active:
            self._stop_recording_capture()
            serialized = self._serialize_recording_events()
            self.recordings[TEMP_RECORDING_NAME] = serialized
            self.selected_recording_var.set(TEMP_RECORDING_NAME)
            self._save_recordings_to_disk()
            self._refresh_recording_list()
            self._set_status(f"Recording saved as temporary ({len(serialized)} events)")
            return

        self._start_recording_capture()

    def _save_temp_recording_as_named(self) -> None:
        name = self.recording_name_var.get().strip()
        if not name:
            self._set_status("Enter a recording name to save temporary recording")
            return

        temp = self.recordings.get(TEMP_RECORDING_NAME)
        if not temp:
            self._set_status("No temporary recording available")
            return

        self.recordings[name] = [dict(item) for item in temp]
        if not self._save_recordings_to_disk():
            return

        self.selected_recording_var.set(name)
        self._refresh_recording_list()
        self._set_status(f"Saved recording as '{name}'")

    def _delete_selected_recording(self) -> None:
        name = self.selected_recording_var.get().strip()
        if not name:
            self._set_status("Select a recording to delete")
            return

        if name not in self.recordings:
            self._set_status(f"Recording '{name}' not found")
            return

        del self.recordings[name]
        if not self._save_recordings_to_disk():
            return

        self.selected_recording_var.set(TEMP_RECORDING_NAME if TEMP_RECORDING_NAME in self.recordings else "")
        self._refresh_recording_list()
        self._set_status(f"Deleted recording '{name}'")

    def _load_recordings_from_disk(self) -> None:
        if not os.path.exists(self.recordings_path):
            self.recordings = {}
            return

        try:
            with open(self.recordings_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            self.recordings = {}
            self._set_status(f"Failed reading recordings: {exc}")
            return

        cleaned: dict[str, list[dict[str, object]]] = {}
        if isinstance(data, dict):
            for name, events in data.items():
                if not isinstance(name, str) or not isinstance(events, list):
                    continue
                cleaned[name] = self._normalize_recording_events(events)

        self.recordings = cleaned

    def _save_recordings_to_disk(self) -> bool:
        try:
            with open(self.recordings_path, "w", encoding="utf-8") as handle:
                json.dump(self.recordings, handle, indent=2)
            return True
        except Exception as exc:
            self._set_status(f"Failed saving recordings: {exc}")
            return False

    def _refresh_recording_list(self) -> None:
        names = sorted(self.recordings.keys())
        if self.recording_combo is not None:
            self.recording_combo.configure(values=names)

        current = self.selected_recording_var.get().strip()
        if current and current not in self.recordings:
            self.selected_recording_var.set(names[0] if names else "")

    def _play_recording_hotkey(self) -> None:
        self._play_selected_recording_once()

    def _play_selected_recording_once(self) -> None:
        name = self.selected_recording_var.get().strip()
        if not name:
            self._set_status("No recording selected")
            return

        events = self.recordings.get(name)
        if not events:
            self._set_status(f"Recording '{name}' is empty or missing")
            return

        try:
            speed = float(self.macro_speed_var.get().strip())
            if speed <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Macro speed must be a positive number")
            return

        local_stop = threading.Event()
        played = self._play_recording_events(events, speed, local_stop)
        if played:
            self._set_status(f"Played recording '{name}'")

    def _parse_recorded_key_token(self, token: str) -> keyboard.Key | keyboard.KeyCode | None:
        if len(token) == 1:
            return keyboard.KeyCode.from_char(token)
        return self._parse_keyboard_key(token)

    def _play_recording_events(
        self,
        events: list[dict[str, object]],
        speed: float,
        stop_event: threading.Event,
    ) -> bool:
        normalized = self._normalize_recording_events(events)
        if not normalized:
            return False

        previous_t = 0.0
        for item in normalized:
            if stop_event.is_set():
                return False

            event_t = float(item["t"])
            delta = max(0.0, (event_t - previous_t) / max(0.01, speed))
            previous_t = event_t
            if delta > 0 and self._sleep_with_custom_stop(delta, stop_event):
                return False

            event_type = str(item["type"])
            payload = item["payload"] if isinstance(item["payload"], dict) else {}
            self._execute_recording_event(event_type, payload)

        return True

    def _execute_recording_event(self, event_type: str, payload: dict[str, object]) -> None:
        try:
            if event_type == "key_press":
                token = str(payload.get("key", ""))
                key_obj = self._parse_recorded_key_token(token)
                if key_obj is not None:
                    self.keyboard_controller.press(key_obj)
                return

            if event_type == "key_release":
                token = str(payload.get("key", ""))
                key_obj = self._parse_recorded_key_token(token)
                if key_obj is not None:
                    self.keyboard_controller.release(key_obj)
                return

            if event_type == "mouse_move":
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
                self.mouse_controller.position = (x, y)
                return

            if event_type == "mouse_click":
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
                button_token = str(payload.get("button", "left"))
                pressed = bool(payload.get("pressed", False))
                button = self._button_from_token(button_token)
                if button is None:
                    return
                self.mouse_controller.position = (x, y)
                if pressed:
                    self.mouse_controller.press(button)
                else:
                    self.mouse_controller.release(button)
                return

            if event_type == "mouse_scroll":
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
                dx = int(float(payload.get("dx", 0.0)))
                dy = int(float(payload.get("dy", 0.0)))
                self.mouse_controller.position = (x, y)
                self.mouse_controller.scroll(dx, dy)
        except Exception:
            return

    def _toggle_crosshair(self) -> None:
        if self.crosshair_enabled:
            self._stop_crosshair()
            return

        self._start_crosshair()

    def _start_crosshair(self) -> None:
        if self.crosshair_enabled:
            return

        x1, y1, x2, y2 = self._virtual_screen_bounds()
        if x1 == x2 and y1 == y2:
            x1 = 0
            y1 = 0
            x2 = self.root.winfo_screenwidth()
            y2 = self.root.winfo_screenheight()

        width = x2 - x1
        height = y2 - y1

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{width}x{height}+{x1}+{y1}")

        transparent_bg = "#12ab34"
        overlay.configure(bg=transparent_bg)
        try:
            overlay.wm_attributes("-transparentcolor", transparent_bg)
        except tk.TclError:
            pass

        canvas = tk.Canvas(overlay, bg=transparent_bg, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        self.crosshair_overlay = overlay
        self.crosshair_canvas = canvas
        self.crosshair_overlay_origin = (x1, y1)
        self.crosshair_enabled = True

        if self.crosshair_button is not None:
            self.crosshair_button.configure(text="Hide crosshair")

        self._update_crosshair_overlay()

    def _stop_crosshair(self) -> None:
        self.crosshair_enabled = False

        if self.crosshair_after_id is not None:
            try:
                self.root.after_cancel(self.crosshair_after_id)
            except tk.TclError:
                pass
            self.crosshair_after_id = None

        if self.crosshair_overlay is not None:
            try:
                self.crosshair_overlay.destroy()
            except tk.TclError:
                pass

        self.crosshair_overlay = None
        self.crosshair_canvas = None

        if self.crosshair_button is not None:
            self.crosshair_button.configure(text="Show crosshair")

    def _update_crosshair_overlay(self) -> None:
        if not self.crosshair_enabled or self.crosshair_canvas is None:
            return

        point = self._crosshair_world_point()
        canvas = self.crosshair_canvas
        canvas.delete("crosshair")

        if point is not None:
            origin_x, origin_y = self.crosshair_overlay_origin
            local_x = point[0] - origin_x
            local_y = point[1] - origin_y

            length = 16
            canvas.create_line(
                local_x - length,
                local_y,
                local_x + length,
                local_y,
                fill="#ef4444",
                width=2,
                tags="crosshair",
            )
            canvas.create_line(
                local_x,
                local_y - length,
                local_x,
                local_y + length,
                fill="#ef4444",
                width=2,
                tags="crosshair",
            )
            canvas.create_oval(
                local_x - 4,
                local_y - 4,
                local_x + 4,
                local_y + 4,
                outline="#ef4444",
                width=2,
                tags="crosshair",
            )

        try:
            self.crosshair_after_id = self.root.after(50, self._update_crosshair_overlay)
        except tk.TclError:
            self.crosshair_after_id = None

    def _crosshair_world_point(self) -> tuple[int, int] | None:
        mode = self.color_sample_mode_var.get().strip().lower()
        if mode == "cursor":
            x, y = self.mouse_controller.position
            return int(x), int(y)

        if mode == "point":
            parsed = self._parse_point_sample()
            if parsed is None:
                return None
            return parsed

        if mode == "region":
            parsed_region = self._parse_region_sample()
            if parsed_region is None:
                return None
            x1, y1, x2, y2 = parsed_region
            return (x1 + x2) // 2, (y1 + y2) // 2

        return None

    def _set_point_from_cursor(self) -> None:
        x, y = self.mouse_controller.position
        self.point_x_var.set(str(int(x)))
        self.point_y_var.set(str(int(y)))
        self._set_status(f"Point set to {int(x)}, {int(y)}")

    def _set_region_around_cursor(self) -> None:
        try:
            size = int(self.region_size_var.get().strip())
            if size <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Quick region size must be a positive integer")
            return

        x, y = self.mouse_controller.position
        half = size // 2
        x1 = int(x) - half
        y1 = int(y) - half
        x2 = x1 + size
        y2 = y1 + size

        self.region_x1_var.set(str(x1))
        self.region_y1_var.set(str(y1))
        self.region_x2_var.set(str(x2))
        self.region_y2_var.set(str(y2))
        self._set_status(f"Region centered at cursor with size {size}x{size}")

    def _parse_point_sample(self) -> tuple[int, int] | None:
        try:
            x = int(self.point_x_var.get().strip())
            y = int(self.point_y_var.get().strip())
            return x, y
        except ValueError:
            return None

    def _parse_region_sample(self) -> Rect | None:
        try:
            x1 = int(self.region_x1_var.get().strip())
            y1 = int(self.region_y1_var.get().strip())
            x2 = int(self.region_x2_var.get().strip())
            y2 = int(self.region_y2_var.get().strip())
        except ValueError:
            return None

        left = min(x1, x2)
        right = max(x1, x2)
        top = min(y1, y2)
        bottom = max(y1, y2)

        if left == right or top == bottom:
            return None

        return left, top, right, bottom

    @staticmethod
    def _point_in_bounds(point: tuple[int, int], bounds: Rect) -> bool:
        x, y = point
        x1, y1, x2, y2 = bounds
        return x1 <= x < x2 and y1 <= y < y2

    @staticmethod
    def _clip_rect(rect: Rect, bounds: Rect) -> Rect | None:
        x1, y1, x2, y2 = rect
        bx1, by1, bx2, by2 = bounds

        cx1 = max(x1, bx1)
        cy1 = max(y1, by1)
        cx2 = min(x2, bx2)
        cy2 = min(y2, by2)

        if cx1 >= cx2 or cy1 >= cy2:
            return None

        return cx1, cy1, cx2, cy2

    @staticmethod
    def _colors_match(c1: tuple[int, int, int], c2: tuple[int, int, int], tolerance: int) -> bool:
        return all(abs(a - b) <= tolerance for a, b in zip(c1, c2))

    @staticmethod
    def _win32_pixel_at(x: int, y: int) -> tuple[int, int, int] | None:
        hdc = None
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            if not hdc:
                return None

            color_ref = ctypes.windll.gdi32.GetPixel(hdc, x, y)
            if color_ref == -1:
                return None

            red = color_ref & 0xFF
            green = (color_ref >> 8) & 0xFF
            blue = (color_ref >> 16) & 0xFF
            return red, green, blue
        except Exception:
            return None
        finally:
            if hdc:
                ctypes.windll.user32.ReleaseDC(0, hdc)

    def _pixel_at(self, x: int, y: int) -> tuple[int, int, int] | None:
        try:
            if sys.platform == "win32":
                win_pixel = self._win32_pixel_at(x, y)
                if win_pixel is not None:
                    return win_pixel

            pixel = ImageGrab.grab(
                bbox=(x, y, x + 1, y + 1),
                all_screens=(sys.platform == "win32"),
            ).getpixel((0, 0))
            return pixel[:3] if isinstance(pixel, tuple) else None
        except Exception:
            return None

    def _pixel_under_cursor(self) -> tuple[int, int, int] | None:
        x, y = self.mouse_controller.position
        return self._pixel_at(int(x), int(y))

    def _grab_region_image(self, region: Rect) -> Image.Image | None:
        x1, y1, x2, y2 = region
        try:
            return ImageGrab.grab(
                bbox=(x1, y1, x2, y2),
                all_screens=(sys.platform == "win32"),
            ).convert("RGB")
        except Exception:
            return None

    def _region_contains_color(
        self,
        image: Image.Image,
        target_rgb: tuple[int, int, int],
        tolerance: int,
    ) -> bool:
        width, height = image.size
        pixels = image.load()
        area = width * height

        if area <= 50000:
            step = 1
        elif area <= 200000:
            step = 2
        else:
            step = 4

        for y in range(0, height, step):
            for x in range(0, width, step):
                r, g, b = pixels[x, y]
                if self._colors_match((r, g, b), target_rgb, tolerance):
                    return True

        return False

    def _sample_matches_color(self, settings: ClickSettings) -> bool:
        mode = settings.color_sample_mode
        monitor_bounds = settings.selected_monitor_bounds
        raw_match = False
        sampled_pixel: tuple[int, int, int] | None = None

        if mode == "cursor":
            x, y = self.mouse_controller.position
            point = (int(x), int(y))
            if monitor_bounds is not None and not self._point_in_bounds(point, monitor_bounds):
                return False

            sampled_pixel = self._pixel_at(point[0], point[1])
            if sampled_pixel is None:
                return False
            raw_match = self._colors_match(sampled_pixel, settings.target_rgb, settings.tolerance)
            self._append_pixel_history(sampled_pixel, raw_match)
            match = edge_trigger_allows_fire(
                self.last_color_condition_match,
                raw_match,
                settings.edge_trigger_enabled,
            )
            self.last_color_condition_match = raw_match
            return match

        if mode == "point":
            if settings.point_sample is None:
                return False

            if monitor_bounds is not None and not self._point_in_bounds(settings.point_sample, monitor_bounds):
                return False

            sampled_pixel = self._pixel_at(settings.point_sample[0], settings.point_sample[1])
            if sampled_pixel is None:
                return False
            raw_match = self._colors_match(sampled_pixel, settings.target_rgb, settings.tolerance)
            self._append_pixel_history(sampled_pixel, raw_match)
            match = edge_trigger_allows_fire(
                self.last_color_condition_match,
                raw_match,
                settings.edge_trigger_enabled,
            )
            self.last_color_condition_match = raw_match
            return match

        if mode == "region":
            if settings.region_sample is None:
                return False

            region = settings.region_sample
            if monitor_bounds is not None:
                clipped = self._clip_rect(region, monitor_bounds)
                if clipped is None:
                    return False
                region = clipped

            image = self._grab_region_image(region)
            if image is None:
                return False
            raw_match = self._region_contains_color(image, settings.target_rgb, settings.tolerance)
            self._append_pixel_history(None, raw_match)
            match = edge_trigger_allows_fire(
                self.last_color_condition_match,
                raw_match,
                settings.edge_trigger_enabled,
            )
            self.last_color_condition_match = raw_match
            return match

        return False

    def _selected_monitor_bounds(self) -> Rect | None:
        selected = self.monitor_var.get().strip()
        if selected in self.monitor_options:
            return self.monitor_options[selected]

        fallback = next(iter(self.monitor_options.keys()), "All monitors")
        self.monitor_var.set(fallback)
        return self.monitor_options.get(fallback)

    def _parse_settings(self) -> ClickSettings | None:
        try:
            interval = float(self.interval_var.get().strip())
            if interval <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Base interval must be a positive number")
            return None

        randomize = self.randomize_interval_var.get()
        interval_min = interval
        interval_max = interval
        if randomize:
            try:
                interval_min = float(self.interval_min_var.get().strip())
                interval_max = float(self.interval_max_var.get().strip())
                if interval_min <= 0 or interval_max <= 0 or interval_min > interval_max:
                    raise ValueError
            except ValueError:
                self._set_status("Random interval min/max must be positive, and min <= max")
                return None

        action_type = self.action_type_var.get().strip().lower()
        action_target: ActionTarget | None = None
        if action_type == "mouse":
            button_map = {
                "left": Button.left,
                "right": Button.right,
                "middle": Button.middle,
            }
            action_target = button_map.get(self.button_var.get().strip().lower())
            if action_target is None:
                self._set_status("Invalid mouse button selected")
                return None
        elif action_type == "keyboard":
            key_text = self.keyboard_key_var.get().strip()
            if not key_text:
                self._set_status("Keyboard key cannot be empty")
                return None

            action_target = self._parse_keyboard_key(key_text)
            if action_target is None:
                self._set_status("Invalid keyboard key. Try: a, enter, space, f8")
                return None
        else:
            self._set_status("Invalid action type selected")
            return None

        click_style = self.click_style_var.get().strip().lower()
        hold_mode = click_style == "hold"
        hold_duration = 0.0
        if hold_mode:
            try:
                hold_duration = float(self.hold_duration_var.get().strip())
                if hold_duration <= 0:
                    raise ValueError
            except ValueError:
                self._set_status("Hold duration must be a positive number")
                return None

        try:
            burst_count = int(self.burst_count_var.get().strip())
            if burst_count <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Burst count must be a positive integer")
            return None

        try:
            burst_gap = float(self.burst_gap_var.get().strip())
            if burst_gap < 0:
                raise ValueError
        except ValueError:
            self._set_status("Burst gap must be zero or greater")
            return None

        try:
            start_delay = float(self.start_delay_var.get().strip())
            if start_delay < 0:
                raise ValueError
        except ValueError:
            self._set_status("Start delay must be zero or greater")
            return None

        stop_after_clicks: int | None = None
        if self.stop_after_clicks_enabled_var.get():
            try:
                stop_after_clicks = int(self.stop_after_clicks_var.get().strip())
                if stop_after_clicks <= 0:
                    raise ValueError
            except ValueError:
                self._set_status("Stop-after-actions must be a positive integer")
                return None

        stop_after_seconds: float | None = None
        if self.stop_after_seconds_enabled_var.get():
            try:
                stop_after_seconds = float(self.stop_after_seconds_var.get().strip())
                if stop_after_seconds <= 0:
                    raise ValueError
            except ValueError:
                self._set_status("Stop-after-seconds must be a positive number")
                return None

        try:
            anti_detection_jitter_pct = float(self.anti_detection_jitter_pct_var.get().strip())
            anti_detection_pause_chance = float(self.anti_detection_pause_chance_var.get().strip())
            anti_detection_max_pause = float(self.anti_detection_max_pause_var.get().strip())
            if anti_detection_jitter_pct < 0 or anti_detection_pause_chance < 0 or anti_detection_max_pause < 0:
                raise ValueError
        except ValueError:
            self._set_status("Anti-detection values must be valid non-negative numbers")
            return None

        condition_logic_mode = self.condition_logic_mode_var.get().strip().lower()
        if condition_logic_mode not in {"and", "or"}:
            self._set_status("Rule logic mode must be 'and' or 'or'")
            return None

        window_binding_enabled = self.window_binding_enabled_var.get()
        window_title_rule = self.window_title_rule_var.get().strip()
        if window_binding_enabled and not window_title_rule:
            self._set_status("Window binding rule is enabled but title rule is empty")
            return None

        time_window_enabled = self.time_window_enabled_var.get()
        allowed_start_time = self.time_window_start_var.get().strip()
        allowed_end_time = self.time_window_end_var.get().strip()
        if time_window_enabled:
            try:
                datetime.strptime(allowed_start_time, "%H:%M")
                datetime.strptime(allowed_end_time, "%H:%M")
            except ValueError:
                self._set_status("Time window must use HH:MM 24-hour format")
                return None

        use_macro_recording = self.use_macro_recording_var.get()
        selected_recording_name = self.selected_recording_var.get().strip()
        if use_macro_recording:
            if not selected_recording_name:
                self._set_status("Macro mode is enabled but no recording is selected")
                return None
            recording_events = self.recordings.get(selected_recording_name)
            if not recording_events:
                self._set_status(f"Selected recording '{selected_recording_name}' is missing or empty")
                return None

        try:
            macro_speed = float(self.macro_speed_var.get().strip())
            if macro_speed <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Macro speed must be a positive number")
            return None

        use_color = self.use_color_check_var.get()
        target_rgb = (255, 255, 255)
        tolerance = 0
        color_mode = self.color_sample_mode_var.get().strip().lower()
        point_sample: tuple[int, int] | None = None
        region_sample: Rect | None = None

        if use_color:
            parsed_rgb = self._hex_to_rgb(self.target_color_var.get())
            if parsed_rgb is None:
                self._set_status("Target color must be a valid 6-digit hex value")
                return None
            target_rgb = parsed_rgb

            try:
                tolerance = int(self.tolerance_var.get().strip())
                if not 0 <= tolerance <= 255:
                    raise ValueError
            except ValueError:
                self._set_status("Tolerance must be an integer from 0 to 255")
                return None

            if color_mode not in {"cursor", "point", "region"}:
                self._set_status("Invalid color sample mode")
                return None

            if color_mode == "point":
                point_sample = self._parse_point_sample()
                if point_sample is None:
                    self._set_status("Point mode requires valid integer X and Y")
                    return None

            if color_mode == "region":
                region_sample = self._parse_region_sample()
                if region_sample is None:
                    self._set_status("Region mode requires valid x1,y1,x2,y2 with non-zero size")
                    return None

        return ClickSettings(
            interval=interval,
            randomize_interval=randomize,
            interval_min=interval_min,
            interval_max=interval_max,
            action_type=action_type,
            action_target=action_target,
            hold_mode=hold_mode,
            hold_duration=hold_duration,
            burst_count=burst_count,
            burst_gap=burst_gap,
            use_color=use_color,
            target_rgb=target_rgb,
            tolerance=tolerance,
            color_sample_mode=color_mode,
            point_sample=point_sample,
            region_sample=region_sample,
            selected_monitor_bounds=self._selected_monitor_bounds(),
            start_delay=start_delay,
            stop_after_clicks=stop_after_clicks,
            stop_after_seconds=stop_after_seconds,
            condition_logic_mode=condition_logic_mode,
            window_binding_enabled=window_binding_enabled,
            window_title_rule=window_title_rule,
            time_window_enabled=time_window_enabled,
            allowed_start_time=allowed_start_time,
            allowed_end_time=allowed_end_time,
            edge_trigger_enabled=self.edge_trigger_var.get(),
            anti_detection_enabled=self.anti_detection_enabled_var.get(),
            anti_detection_jitter_pct=anti_detection_jitter_pct,
            anti_detection_pause_chance=anti_detection_pause_chance,
            anti_detection_max_pause=anti_detection_max_pause,
            use_macro_recording=use_macro_recording,
            selected_recording_name=selected_recording_name,
            macro_speed=macro_speed,
        )

    def _sleep_with_stop(self, duration: float) -> bool:
        end_time = time.monotonic() + duration
        while not self.stop_event.is_set():
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.02, remaining))
        return True

    @staticmethod
    def _sleep_with_custom_stop(duration: float, stop_event: threading.Event) -> bool:
        end_time = time.monotonic() + duration
        while not stop_event.is_set():
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.02, remaining))
        return True

    def _perform_single_action(self, settings: ClickSettings) -> bool:
        try:
            if settings.action_type == "mouse":
                button = settings.action_target
                if settings.hold_mode:
                    self.mouse_controller.press(button)
                    interrupted = self._sleep_with_stop(settings.hold_duration)
                    self.mouse_controller.release(button)
                    return not interrupted

                self.mouse_controller.click(button)
                return True

            key_target = settings.action_target
            if settings.hold_mode:
                self.keyboard_controller.press(key_target)
                interrupted = self._sleep_with_stop(settings.hold_duration)
                self.keyboard_controller.release(key_target)
                return not interrupted

            self.keyboard_controller.press(key_target)
            self.keyboard_controller.release(key_target)
            return True
        except Exception as exc:
            self._set_status(f"Input action failed: {exc}")
            self.stop_event.set()
            return False

    def _perform_action_cycle(self, settings: ClickSettings, burst_count: int) -> int:
        performed = 0
        for idx in range(burst_count):
            if self.stop_event.is_set():
                break

            if not self._perform_single_action(settings):
                break

            performed += 1
            if idx < burst_count - 1 and settings.burst_gap > 0:
                if self._sleep_with_stop(settings.burst_gap):
                    break

        return performed

    def _countdown_start_delay(self, start_delay: float) -> bool:
        if start_delay <= 0:
            return False

        remaining = start_delay
        last_second = -1

        while remaining > 0:
            if self.stop_event.is_set():
                return True

            this_second = int(remaining + 0.999)
            if this_second != last_second:
                self._set_status(f"Starting in {this_second}s...")
                last_second = this_second

            step = min(0.1, remaining)
            if self._sleep_with_stop(step):
                return True
            remaining -= step

        return False

    def _click_loop(self, settings: ClickSettings) -> None:
        if self._countdown_start_delay(settings.start_delay):
            self.running = False
            self._set_status("Stopped")
            return

        click_count = 0
        run_start = time.monotonic()
        stop_reason: str | None = None

        self._set_status("Running")
        self._set_session_info(click_count, 0.0)

        while not self.stop_event.is_set():
            if self.paused:
                time.sleep(0.05)
                continue

            elapsed = time.monotonic() - run_start
            if settings.stop_after_seconds is not None and elapsed >= settings.stop_after_seconds:
                stop_reason = f"Stopped: reached {settings.stop_after_seconds:.2f}s limit"
                break

            enabled_condition_results: list[bool] = []
            if settings.use_color:
                enabled_condition_results.append(self._sample_matches_color(settings))

            if settings.window_binding_enabled:
                current_title = self._current_window_title().lower()
                enabled_condition_results.append(settings.window_title_rule.lower() in current_title)

            if settings.time_window_enabled:
                enabled_condition_results.append(
                    self._time_window_allows(settings.allowed_start_time, settings.allowed_end_time)
                )

            should_fire = evaluate_rule_conditions(enabled_condition_results, settings.condition_logic_mode)

            if should_fire:
                if settings.use_macro_recording:
                    if settings.stop_after_clicks is not None and click_count >= settings.stop_after_clicks:
                        stop_reason = f"Stopped: reached {settings.stop_after_clicks} action limit"
                        break

                    events = self.recordings.get(settings.selected_recording_name, [])
                    played = self._play_recording_events(events, settings.macro_speed, self.stop_event)
                    if played:
                        click_count += 1
                else:
                    burst_count = settings.burst_count
                    if settings.stop_after_clicks is not None:
                        remaining_actions = settings.stop_after_clicks - click_count
                        if remaining_actions <= 0:
                            stop_reason = f"Stopped: reached {settings.stop_after_clicks} action limit"
                            break
                        burst_count = min(burst_count, remaining_actions)

                    performed = self._perform_action_cycle(settings, burst_count)
                    click_count += performed

                elapsed = time.monotonic() - run_start
                self._set_session_info(click_count, elapsed)

                if settings.stop_after_clicks is not None and click_count >= settings.stop_after_clicks:
                    stop_reason = f"Stopped: reached {settings.stop_after_clicks} action limit"
                    break

            interval = settings.interval
            if settings.randomize_interval:
                interval = random.uniform(settings.interval_min, settings.interval_max)
            interval = compute_anti_detection_interval(
                base_interval=interval,
                enabled=settings.anti_detection_enabled,
                jitter_pct=settings.anti_detection_jitter_pct,
                pause_chance=settings.anti_detection_pause_chance,
                max_pause=settings.anti_detection_max_pause,
            )

            if self._sleep_with_stop(interval):
                break

        self.running = False
        if stop_reason is not None:
            self._set_status(stop_reason)
        else:
            self._set_status("Stopped")

    def toggle_running(self) -> None:
        if self.running:
            self.running = False
            self.stop_event.set()
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=0.5)
            self._set_status("Stopped")
            return

        settings = self._parse_settings()
        if settings is None:
            return

        self.stop_event.clear()
        self.running = True
        self.paused = False
        self.last_color_condition_match = False
        self._set_session_info(0, 0.0)

        self.worker_thread = threading.Thread(target=self._click_loop, args=(settings,), daemon=True)
        self.worker_thread.start()
        self._set_status("Starting...")

    def toggle_paused(self) -> None:
        if not self.running:
            self._set_status("Not running. Start the clicker first.")
            return

        self.paused = not self.paused
        if self.paused:
            self._set_status("Paused")
        else:
            self._set_status("Running")

    def _profile_payload(self) -> dict[str, object]:
        var_names = [
            "start_stop_hotkey_var",
            "pause_hotkey_var",
            "record_toggle_hotkey_var",
            "play_recording_hotkey_var",
            "action_type_var",
            "button_var",
            "keyboard_key_var",
            "click_style_var",
            "hold_duration_var",
            "interval_var",
            "randomize_interval_var",
            "interval_min_var",
            "interval_max_var",
            "anti_detection_enabled_var",
            "anti_detection_jitter_pct_var",
            "anti_detection_pause_chance_var",
            "anti_detection_max_pause_var",
            "burst_count_var",
            "burst_gap_var",
            "start_delay_var",
            "stop_after_clicks_enabled_var",
            "stop_after_clicks_var",
            "stop_after_seconds_enabled_var",
            "stop_after_seconds_var",
            "use_color_check_var",
            "color_options_visible_var",
            "target_color_var",
            "tolerance_var",
            "edge_trigger_var",
            "pixel_history_enabled_var",
            "condition_logic_mode_var",
            "color_sample_mode_var",
            "monitor_var",
            "point_x_var",
            "point_y_var",
            "region_x1_var",
            "region_y1_var",
            "region_x2_var",
            "region_y2_var",
            "region_size_var",
            "inkdrop_lock_key_var",
            "window_binding_enabled_var",
            "window_title_rule_var",
            "time_window_enabled_var",
            "time_window_start_var",
            "time_window_end_var",
            "profile_hotkeys_enabled_var",
            "use_macro_recording_var",
            "selected_recording_var",
            "recording_name_var",
            "macro_speed_var",
        ]

        payload: dict[str, object] = {}
        for name in var_names:
            var = getattr(self, name, None)
            if isinstance(var, tk.Variable):
                payload[name] = var.get()

        return payload

    def _apply_profile_payload(self, payload: dict[str, object]) -> None:
        for name, value in payload.items():
            var = getattr(self, name, None)
            if isinstance(var, tk.Variable):
                try:
                    var.set(value)
                except tk.TclError:
                    continue

        if self.monitor_var.get() not in self.monitor_options:
            self.monitor_var.set(next(iter(self.monitor_options.keys()), "All monitors"))

        self._sync_action_controls()
        self._sync_hold_controls()
        self._sync_timing_controls()
        self._set_color_options_visible(self.color_options_visible_var.get())
        self._sync_color_mode_controls()
        self._sync_safety_controls()
        self._sync_rule_controls()
        self._update_color_preview()
        self._refresh_recording_list()
        if self.profile_hotkeys_enabled_var.get():
            self._start_hotkeys()

    def _load_profiles_from_disk(self) -> None:
        if not os.path.exists(self.profile_path):
            self.profiles = {}
            return

        try:
            with open(self.profile_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            self.profiles = {}
            self._set_status(f"Failed reading profiles: {exc}")
            return

        if isinstance(data, dict):
            cleaned: dict[str, dict[str, object]] = {}
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, dict):
                    cleaned[key] = value
            self.profiles = cleaned
            return

        self.profiles = {}

    def _save_profiles_to_disk(self) -> bool:
        try:
            with open(self.profile_path, "w", encoding="utf-8") as handle:
                json.dump(self.profiles, handle, indent=2)
            return True
        except Exception as exc:
            self._set_status(f"Failed saving profiles: {exc}")
            return False

    def _refresh_profile_list(self) -> None:
        if self.profile_combo is None:
            return

        names = sorted(self.profiles.keys())
        self.profile_combo.configure(values=names)

        selected = self.profile_select_var.get().strip()
        if selected and selected not in self.profiles:
            self.profile_select_var.set("")

    def _save_profile(self) -> None:
        name = self.profile_name_var.get().strip() or self.profile_select_var.get().strip()
        if not name:
            self._set_status("Provide a profile name to save")
            return

        self.profiles[name] = self._profile_payload()
        if not self._save_profiles_to_disk():
            return

        self.profile_select_var.set(name)
        self.profile_name_var.set(name)
        self._refresh_profile_list()
        self._set_status(f"Saved profile '{name}'")

    def _load_selected_profile(self) -> None:
        name = self.profile_select_var.get().strip() or self.profile_name_var.get().strip()
        if not name:
            self._set_status("Select a profile to load")
            return

        payload = self.profiles.get(name)
        if payload is None:
            self._set_status(f"Profile '{name}' not found")
            return

        self._apply_profile_payload(payload)
        self.profile_select_var.set(name)
        self.profile_name_var.set(name)
        self._set_status(f"Loaded profile '{name}'")

    def _delete_selected_profile(self) -> None:
        name = self.profile_select_var.get().strip() or self.profile_name_var.get().strip()
        if not name:
            self._set_status("Select a profile to delete")
            return

        if name not in self.profiles:
            self._set_status(f"Profile '{name}' not found")
            return

        del self.profiles[name]
        if not self._save_profiles_to_disk():
            return

        self.profile_select_var.set("")
        if self.profile_name_var.get().strip() == name:
            self.profile_name_var.set("")
        self._refresh_profile_list()
        self._set_status(f"Deleted profile '{name}'")

    def on_close(self) -> None:
        self.running = False
        self.stop_event.set()

        self._stop_recording_capture()
        self._stop_inkdropper()
        self._stop_crosshair()
        self._close_test_window()

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()

        self.root.destroy()


def main() -> None:
    AutoClickerApp._enable_dpi_awareness()
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
