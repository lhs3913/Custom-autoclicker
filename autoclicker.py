import ctypes
import colorsys
import copy
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
from tkinter import messagebox, ttk

from PIL import Image, ImageGrab, ImageTk
from pynput import keyboard, mouse
from pynput.mouse import Button

from ui.tabs.click_tab import build_click_tab as build_click_tab_ui
from ui.tabs.color_tab import build_color_tab as build_color_tab_ui
from ui.tabs.hotkeys_profiles_tab import build_hotkeys_profiles_tab as build_hotkeys_profiles_tab_ui
from ui.tabs.macro_tab import build_macro_tab as build_macro_tab_ui
from ui.tabs.rules_tab import build_rules_tab as build_rules_tab_ui
from ui.tabs.safety_tab import build_safety_tab as build_safety_tab_ui
from ui.tabs.testing_tab import build_testing_tab as build_testing_tab_ui
from ui.tests.click_tab import build_test_click_tab as build_test_click_tab_ui
from ui.tests.color_tab import build_test_color_tab as build_test_color_tab_ui
from ui.tests.letter_tab import build_test_letter_tab as build_test_letter_tab_ui
from ui.tests.obstacle_tab import build_test_obstacle_tab as build_test_obstacle_tab_ui
from ui.tests.overview_tab import build_test_overview_tab as build_test_overview_tab_ui
from ui.tests.window import open_test_window as open_test_window_ui


PROFILE_FILE_NAME = "profiles.json"
RECORDINGS_FILE_NAME = "recordings.json"
RUN_LOG_FILE_NAME = "run_logs.jsonl"
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
    macro_reanchor_window: bool
    macro_dry_run: bool


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
        self.run_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), RUN_LOG_FILE_NAME)
        self.profiles: dict[str, dict[str, object]] = {}
        self.recordings: dict[str, dict[str, object]] = {}

        self.monitor_options = self._detect_monitors()

        self.recording_active = False
        self.recording_started_at = 0.0
        self.recording_events: list[RecordingEvent] = []
        self.recording_keyboard_listener: keyboard.Listener | None = None
        self.recording_mouse_listener: mouse.Listener | None = None
        self.recording_last_move_time = 0.0
        self.recording_last_move_pos: tuple[int, int] | None = None
        self.recording_anchor_title = ""
        self.recording_anchor_rect: Rect | None = None

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
        self.color_trigger_mode_var = tk.StringVar(value="continuous")
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
        self.recording_coordinate_mode_var = tk.StringVar(value="window_relative")
        self.macro_reanchor_window_var = tk.BooleanVar(value=True)
        self.macro_dry_run_var = tk.BooleanVar(value=False)

        self.macro_selected_step_var = tk.StringVar(value="No step selected")
        self.macro_step_delay_var = tk.StringVar(value="0.000")
        self.macro_step_type_var = tk.StringVar(value="")
        self.macro_step_payload_var = tk.StringVar(value="")

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
        self.macro_step_tree: ttk.Treeview | None = None
        self.macro_step_apply_button: ttk.Button | None = None
        self.pixel_history_listbox: tk.Listbox | None = None
        self.window_rule_entry: ttk.Entry | None = None
        self.time_start_entry: ttk.Entry | None = None
        self.time_end_entry: ttk.Entry | None = None

        self.test_window: tk.Toplevel | None = None
        self.test_notebook: ttk.Notebook | None = None
        self.test_tab_frames: dict[str, ttk.Frame] = {}
        self.test_center_button: tk.Button | None = None
        self.test_center_auto_toggle_button: ttk.Button | None = None
        self.test_color_wheel_image: ImageTk.PhotoImage | None = None
        self.test_center_auto_after_id: str | None = None
        self.test_click_buttons_container: ttk.Frame | None = None
        self.test_color_wheel_canvas: tk.Canvas | None = None
        self.test_color_wheel_size = 0
        self.test_color_wheel_pick_enabled = False
        self.test_color_wheel_pick_after_id: str | None = None

        self.dry_run_overlay: tk.Toplevel | None = None
        self.dry_run_canvas: tk.Canvas | None = None
        self.dry_run_overlay_origin = (0, 0)
        self.dry_run_last_point: tuple[int, int] | None = None
        self.dry_run_clear_after_id: str | None = None

        self.test_button_one_count = 0
        self.test_button_two_count = 0
        self.test_click_targets: dict[int, dict[str, object]] = {}
        self.test_click_target_next_id = 1
        self.test_click_new_button_name_var = tk.StringVar(value="")
        self.test_center_click_count = 0
        self.test_center_current_color = "#1f7a8c"
        self.test_center_auto_color_enabled = False
        self.test_color_wheel_lock_key_var = tk.StringVar(value="l")
        self.test_color_wheel_lock_status_var = tk.StringVar(value="Wheel lock: off")
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
        self.test_letter_total_var = tk.StringVar(value="Characters typed: 0")
        self.test_letter_last_var = tk.StringVar(value="Last character: none")
        self.test_letter_breakdown_var = tk.StringVar(value="Breakdown: none")
        self.test_obstacle_counter_var = tk.StringVar(value="Obstacle interactions: 0")
        self.test_obstacle_last_var = tk.StringVar(value="Last obstacle action: none")

        self._build_ui()
        self._sync_action_controls()
        self._sync_hold_controls()
        self._sync_timing_controls()
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
        rules_tab = ttk.Frame(notebook, padding=10)
        safety_tab = ttk.Frame(notebook, padding=10)
        macro_tab = ttk.Frame(notebook, padding=10)
        hotkey_profile_tab = ttk.Frame(notebook, padding=10)

        notebook.add(click_tab, text="Click")
        notebook.add(color_tab, text="Color Trigger")
        notebook.add(rules_tab, text="Rules")
        notebook.add(safety_tab, text="Safety")
        notebook.add(macro_tab, text="Macros")
        notebook.add(hotkey_profile_tab, text="Hotkeys & Profiles")

        self._build_click_tab(click_tab)
        self._build_color_tab(color_tab)
        self._build_rules_tab(rules_tab)
        self._build_safety_tab(safety_tab)
        self._build_macro_tab(macro_tab)
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
        build_click_tab_ui(self, tab)

    def _build_color_tab(self, tab: ttk.Frame) -> None:
        build_color_tab_ui(self, tab)

    def _build_rules_tab(self, tab: ttk.Frame) -> None:
        build_rules_tab_ui(self, tab)

    def _build_safety_tab(self, tab: ttk.Frame) -> None:
        build_safety_tab_ui(self, tab)

    def _build_macro_tab(self, tab: ttk.Frame) -> None:
        build_macro_tab_ui(self, tab)

    def _build_testing_tab(self, tab: ttk.Frame) -> None:
        build_testing_tab_ui(self, tab)

    def _build_hotkeys_profiles_tab(self, tab: ttk.Frame) -> None:
        build_hotkeys_profiles_tab_ui(self, tab)

    def _open_test_window(self, initial_tab: str = "overview") -> None:
        open_test_window_ui(self, initial_tab)

    def _build_test_overview_tab(self, tab: ttk.Frame) -> None:
        build_test_overview_tab_ui(self, tab)

    def _build_test_click_tab(self, tab: ttk.Frame) -> None:
        build_test_click_tab_ui(self, tab)

    def _build_test_color_tab(self, tab: ttk.Frame) -> None:
        build_test_color_tab_ui(self, tab)

    def _build_test_letter_tab(self, tab: ttk.Frame) -> None:
        build_test_letter_tab_ui(self, tab)

    def _build_test_obstacle_tab(self, tab: ttk.Frame) -> None:
        build_test_obstacle_tab_ui(self, tab)

    def _close_test_window(self) -> None:
        window = self.test_window
        self._cancel_all_test_click_target_hold_jobs()
        self.test_window = None
        self.test_notebook = None
        self.test_tab_frames = {}
        self.test_center_button = None
        self.test_center_auto_toggle_button = None
        self.test_color_wheel_image = None
        self.test_click_buttons_container = None
        self.test_color_wheel_canvas = None
        self.test_color_wheel_size = 0
        self._stop_test_color_wheel_lock()
        self._cancel_test_center_auto_job()
        self.test_center_auto_color_enabled = False

        if window is None:
            return

        try:
            window.destroy()
        except tk.TclError:
            pass

    def _reset_test_window_state(self) -> None:
        self._cancel_all_test_click_target_hold_jobs()
        self.test_button_one_count = 0
        self.test_button_two_count = 0
        self.test_click_targets = {}
        self.test_click_target_next_id = 1
        self.test_click_new_button_name_var.set("")
        self.test_center_click_count = 0
        self.test_center_current_color = "#1f7a8c"
        self.test_center_auto_color_enabled = False
        self.test_color_wheel_pick_enabled = False
        self._cancel_test_color_wheel_pick_job()
        self.test_color_wheel_lock_key_var.set("l")
        self.test_color_wheel_lock_status_var.set("Wheel lock: off")
        self._cancel_test_center_auto_job()
        self.test_letter_total_count = 0
        self.test_letter_counts.clear()
        self.test_obstacle_count = 0
        self.test_obstacle_toggle_var.set(False)

        self.test_button_one_var.set("Button 1 clicks: 0")
        self.test_button_two_var.set("Button 2 clicks: 0")
        self.test_center_counter_var.set("Center button presses: 0")
        self.test_center_color_var.set("Current center color: #1F7A8C")
        self.test_center_random_interval_var.set("0.75")
        self.test_center_auto_status_var.set("Auto random color: off")
        self.test_letter_total_var.set("Characters typed: 0")
        self.test_letter_last_var.set("Last character: none")
        self.test_letter_breakdown_var.set("Breakdown: none")
        self.test_obstacle_counter_var.set("Obstacle interactions: 0")
        self.test_obstacle_last_var.set("Last obstacle action: none")

    def _increment_test_button_counter(self, button_index: int) -> None:
        target = self.test_click_targets.get(button_index)
        if target is None:
            return
        count = int(target.get("count", 0)) + 1
        target["count"] = count
        counter_var = target.get("counter_var")
        if isinstance(counter_var, tk.StringVar):
            counter_var.set(f"Clicks: {count}")

    @staticmethod
    def _parse_target_hold_seconds(target: dict[str, object]) -> float | None:
        hold_var = target.get("hold_seconds_var")
        if not isinstance(hold_var, tk.StringVar):
            return None
        try:
            seconds = float(hold_var.get().strip())
        except ValueError:
            return None
        if seconds < 0:
            return None
        return seconds

    def _refresh_test_click_targets_ui(self) -> None:
        if self.test_click_buttons_container is None:
            return

        for child in self.test_click_buttons_container.winfo_children():
            child.destroy()

        for row, target_id in enumerate(sorted(self.test_click_targets.keys())):
            target = self.test_click_targets[target_id]
            label = str(target.get("label", f"Test Button {target_id}"))
            button = tk.Button(
                self.test_click_buttons_container,
                text=label,
                relief="raised",
                font=("Segoe UI", 9),
                bd=1,
                padx=10,
            )
            button.grid(row=row, column=0, sticky="w", pady=4)
            button.bind(
                "<ButtonPress-1>",
                lambda _event, tid=target_id: self._on_test_click_target_press(tid),
                add="+",
            )
            button.bind(
                "<ButtonRelease-1>",
                lambda _event, tid=target_id: self._on_test_click_target_release(tid),
                add="+",
            )
            counter_var = target.get("counter_var")
            if isinstance(counter_var, tk.StringVar):
                ttk.Label(self.test_click_buttons_container, textvariable=counter_var).grid(
                    row=row, column=1, sticky="w", padx=(8, 0), pady=4
                )

            options = ttk.Frame(self.test_click_buttons_container)
            options.grid(row=row, column=2, sticky="w", padx=(12, 0), pady=4)
            ttk.Label(options, text="Mode:").grid(row=0, column=0, sticky="w")
            mode_var = target.get("mode_var")
            if not isinstance(mode_var, tk.StringVar):
                mode_var = tk.StringVar(value="tap_to_increment")
                target["mode_var"] = mode_var
            mode_combo = ttk.Combobox(
                options,
                textvariable=mode_var,
                values=["tap_to_increment", "hold_to_increment"],
                state="readonly",
                width=18,
            )
            mode_combo.grid(row=0, column=1, sticky="w", padx=(4, 8))
            mode_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, tid=target_id: self._on_test_click_target_mode_changed(tid),
                add="+",
            )

            hold_label = ttk.Label(options, text="Hold threshold (s):")
            hold_entry_var = target.get("hold_seconds_var")
            if not isinstance(hold_entry_var, tk.StringVar):
                hold_entry_var = tk.StringVar(value="0.60")
                target["hold_seconds_var"] = hold_entry_var
            hold_entry = ttk.Entry(options, textvariable=hold_entry_var, width=8)
            target["hold_label_widget"] = hold_label
            target["hold_entry_widget"] = hold_entry
            self._sync_test_click_target_mode_widgets(target_id)

    def _add_test_click_target(self, label: str | None = None) -> None:
        target_id = self.test_click_target_next_id
        self.test_click_target_next_id += 1
        target_label = (label or f"Test Button {target_id}").strip()
        if not target_label:
            target_label = f"Test Button {target_id}"
        self.test_click_targets[target_id] = {
            "label": target_label,
            "count": 0,
            "pressed_at": 0.0,
            "pressed": False,
            "hold_after_id": None,
            "mode_var": tk.StringVar(value="tap_to_increment"),
            "hold_seconds_var": tk.StringVar(value="0.60"),
            "counter_var": tk.StringVar(value="Clicks: 0"),
        }
        self._refresh_test_click_targets_ui()

    def _add_test_click_target_from_ui(self) -> None:
        label = self.test_click_new_button_name_var.get().strip()
        self._add_test_click_target(label if label else None)
        self.test_click_new_button_name_var.set("")

    def _on_test_click_target_press(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        target["pressed_at"] = time.monotonic()
        target["pressed"] = True
        mode_var = target.get("mode_var")
        mode = mode_var.get().strip().lower() if isinstance(mode_var, tk.StringVar) else "tap_to_increment"
        if mode == "hold_to_increment":
            self._start_test_click_target_hold_cycle(target_id)

    def _on_test_click_target_release(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return

        target["pressed"] = False
        self._cancel_test_click_target_hold_job(target_id)
        mode_var = target.get("mode_var")
        mode = mode_var.get().strip().lower() if isinstance(mode_var, tk.StringVar) else "tap_to_increment"
        if mode == "tap_to_increment":
            self._increment_test_button_counter(target_id)

    def _on_test_click_target_mode_changed(self, target_id: int) -> None:
        self._sync_test_click_target_mode_widgets(target_id)
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        mode_var = target.get("mode_var")
        mode = mode_var.get().strip().lower() if isinstance(mode_var, tk.StringVar) else "tap_to_increment"
        if mode != "hold_to_increment":
            self._cancel_test_click_target_hold_job(target_id)

    def _sync_test_click_target_mode_widgets(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        hold_label = target.get("hold_label_widget")
        hold_entry = target.get("hold_entry_widget")
        mode_var = target.get("mode_var")
        if not isinstance(hold_label, ttk.Label) or not isinstance(hold_entry, ttk.Entry):
            return
        mode = mode_var.get().strip().lower() if isinstance(mode_var, tk.StringVar) else "tap_to_increment"
        if mode == "hold_to_increment":
            hold_label.grid(row=0, column=2, sticky="w")
            hold_entry.grid(row=0, column=3, sticky="w", padx=(4, 0))
        else:
            hold_label.grid_remove()
            hold_entry.grid_remove()

    def _start_test_click_target_hold_cycle(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        hold_seconds = self._parse_target_hold_seconds(target)
        if hold_seconds is None:
            self._set_status("Hold threshold must be a valid non-negative number.")
            return
        self._cancel_test_click_target_hold_job(target_id)
        delay_ms = max(1, int(hold_seconds * 1000))
        target["hold_after_id"] = self.root.after(
            delay_ms,
            lambda tid=target_id: self._on_test_click_target_hold_tick(tid),
        )

    def _on_test_click_target_hold_tick(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        target["hold_after_id"] = None
        if not bool(target.get("pressed", False)):
            return
        mode_var = target.get("mode_var")
        mode = mode_var.get().strip().lower() if isinstance(mode_var, tk.StringVar) else "tap_to_increment"
        if mode != "hold_to_increment":
            return
        self._increment_test_button_counter(target_id)
        self._start_test_click_target_hold_cycle(target_id)

    def _cancel_test_click_target_hold_job(self, target_id: int) -> None:
        target = self.test_click_targets.get(target_id)
        if target is None:
            return
        after_id = target.get("hold_after_id")
        if isinstance(after_id, str):
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        target["hold_after_id"] = None

    def _cancel_all_test_click_target_hold_jobs(self) -> None:
        for target_id in list(self.test_click_targets.keys()):
            self._cancel_test_click_target_hold_job(target_id)

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
        self._set_status("Center target pressed")
        self._apply_test_center_color()

    def _apply_test_center_color(self) -> None:
        color = self.test_center_current_color
        luminance = (0.299 * int(color[1:3], 16)) + (0.587 * int(color[3:5], 16)) + (0.114 * int(color[5:7], 16))
        text_color = "black" if luminance > 150 else "white"
        if self.test_center_button is not None:
            self.test_center_button.configure(
                text=f"Center Target\n{self.test_center_click_count} presses",
                bg=color,
                activebackground=color,
                fg=text_color,
                activeforeground=text_color,
            )

        self.test_center_counter_var.set(f"Center button presses: {self.test_center_click_count}")
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

    def _toggle_test_color_wheel_lock(self) -> None:
        if self.test_color_wheel_pick_enabled:
            self._stop_test_color_wheel_lock()
            return
        self._start_test_color_wheel_lock()

    def _start_test_color_wheel_lock(self) -> None:
        hotkey = self.test_color_wheel_lock_key_var.get().strip().lower()
        if len(hotkey) != 1:
            self._set_status("Wheel lock hotkey must be a single key.")
            return
        self.test_color_wheel_pick_enabled = True
        self.test_color_wheel_lock_status_var.set(f"Wheel lock: on (press {hotkey} to lock/stop)")
        self._set_status("Wheel lock enabled")
        self._run_test_color_wheel_pick()

    def _stop_test_color_wheel_lock(self) -> None:
        self.test_color_wheel_pick_enabled = False
        self._cancel_test_color_wheel_pick_job()
        self.test_color_wheel_lock_status_var.set("Wheel lock: off")

    def _cancel_test_color_wheel_pick_job(self) -> None:
        if self.test_color_wheel_pick_after_id is None:
            return
        try:
            self.root.after_cancel(self.test_color_wheel_pick_after_id)
        except tk.TclError:
            pass
        self.test_color_wheel_pick_after_id = None

    def _run_test_color_wheel_pick(self) -> None:
        self.test_color_wheel_pick_after_id = None
        if not self.test_color_wheel_pick_enabled:
            return
        picked = self._pick_color_from_test_wheel_under_cursor()
        if picked is not None:
            self.test_center_current_color = picked
            self._apply_test_center_color()
        try:
            self.test_color_wheel_pick_after_id = self.root.after(60, self._run_test_color_wheel_pick)
        except tk.TclError:
            self.test_color_wheel_pick_after_id = None

    def _pick_color_from_test_wheel_under_cursor(self) -> str | None:
        canvas = self.test_color_wheel_canvas
        if canvas is None or self.test_color_wheel_size <= 0:
            return None
        try:
            if not canvas.winfo_exists():
                return None
        except tk.TclError:
            return None

        x_root = self.root.winfo_pointerx()
        y_root = self.root.winfo_pointery()
        local_x = x_root - canvas.winfo_rootx()
        local_y = y_root - canvas.winfo_rooty()
        size = self.test_color_wheel_size
        if local_x < 0 or local_y < 0 or local_x >= size or local_y >= size:
            return None

        rgb = self._test_color_wheel_rgb_at(local_x, local_y, size)
        if rgb is None:
            return None
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    @staticmethod
    def _test_color_wheel_rgb_at(x: int, y: int, size: int) -> tuple[int, int, int] | None:
        center = (size - 1) / 2.0
        dx = x - center
        dy = y - center
        distance = math.hypot(dx, dy)
        outer_radius = center - 1
        inner_radius = outer_radius * 0.33
        if distance > outer_radius or distance < inner_radius:
            return None

        hue = ((math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0) / 360.0
        saturation = min(1.0, max(0.0, distance / outer_radius))
        red, green, blue = colorsys.hsv_to_rgb(hue, saturation, 1.0)
        return int(red * 255), int(green * 255), int(blue * 255)

    @staticmethod
    def _display_typed_char(char: str) -> str:
        if char == " ":
            return "<space>"
        if char == "\t":
            return "<tab>"
        if char == "\n":
            return "<newline>"
        if char == "\r":
            return "<return>"
        return char

    def _update_test_character_breakdown(self) -> None:
        if not self.test_letter_counts:
            self.test_letter_breakdown_var.set("Breakdown: none")
            return

        breakdown = ", ".join(
            f"{self._display_typed_char(token)}:{count}"
            for token, count in sorted(self.test_letter_counts.items(), key=lambda item: item[0])
        )
        self.test_letter_breakdown_var.set(f"Breakdown: {breakdown}")

    def _on_test_window_key_press(self, event: tk.Event) -> str | None:
        char = event.char
        if not char or len(char) != 1:
            return
        current_tab_name = ""
        if self.test_notebook is not None:
            try:
                selected_id = self.test_notebook.select()
                for name, frame in self.test_tab_frames.items():
                    if str(frame) == str(selected_id):
                        current_tab_name = name
                        break
            except tk.TclError:
                current_tab_name = ""

        if (
            current_tab_name == "color"
            and char.lower() == self.test_color_wheel_lock_key_var.get().strip().lower()
        ):
            self._toggle_test_color_wheel_lock()
            return "break"
        if current_tab_name == "letters" and char.isprintable():
            self.test_letter_total_count += 1
            self.test_letter_counts[char] = self.test_letter_counts.get(char, 0) + 1
            self.test_letter_total_var.set(f"Characters typed: {self.test_letter_total_count}")
            self.test_letter_last_var.set(f"Last character: {self._display_typed_char(char)}")
            self._update_test_character_breakdown()
            return "break"
        return None

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

    def _show_section_info(self, title: str, text: str) -> None:
        try:
            messagebox.showinfo(title, text, parent=self.root)
        except tk.TclError:
            self._set_status(text)

    def _attach_info_button(self, frame: ttk.LabelFrame, title: str, text: str) -> None:
        frame.columnconfigure(998, weight=1)
        button = ttk.Button(
            frame,
            text="Info",
            command=lambda t=title, body=text: self._show_section_info(t, body),
        )
        button.grid(row=0, column=999, sticky="e", padx=(8, 4), pady=(0, 4))
        try:
            button.configure(takefocus=False)
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

    @staticmethod
    def _foreground_window_info() -> tuple[str, Rect | None]:
        if sys.platform != "win32":
            return "", None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "", None

            title_length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if title_length > 0:
                buffer = ctypes.create_unicode_buffer(title_length + 1)
                user32.GetWindowTextW(hwnd, buffer, title_length + 1)
                title = buffer.value.strip()

            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return title, None

            window_rect = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            if window_rect[2] <= window_rect[0] or window_rect[3] <= window_rect[1]:
                return title, None
            return title, window_rect
        except Exception:
            return "", None

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
    def _default_recording_meta() -> dict[str, object]:
        return {
            "coordinate_mode": "absolute",
            "anchor_title": "",
            "anchor_rect": None,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

    @staticmethod
    def _normalize_anchor_rect(raw_rect: object) -> Rect | None:
        if not isinstance(raw_rect, (list, tuple)) or len(raw_rect) != 4:
            return None
        try:
            x1, y1, x2, y2 = (int(raw_rect[0]), int(raw_rect[1]), int(raw_rect[2]), int(raw_rect[3]))
        except (TypeError, ValueError):
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def _normalize_recording_meta(self, raw_meta: object) -> dict[str, object]:
        meta = self._default_recording_meta()
        if not isinstance(raw_meta, dict):
            return meta

        coordinate_mode = str(raw_meta.get("coordinate_mode", "")).strip().lower()
        if coordinate_mode in {"absolute", "window_relative"}:
            meta["coordinate_mode"] = coordinate_mode

        anchor_title = raw_meta.get("anchor_title")
        if isinstance(anchor_title, str):
            meta["anchor_title"] = anchor_title

        normalized_rect = self._normalize_anchor_rect(raw_meta.get("anchor_rect"))
        if normalized_rect is not None:
            meta["anchor_rect"] = list(normalized_rect)

        created_at = raw_meta.get("created_at")
        if isinstance(created_at, str) and created_at:
            meta["created_at"] = created_at

        return meta

    def _normalize_recording_package(self, raw: object) -> dict[str, object] | None:
        if isinstance(raw, list):
            return {
                "events": self._normalize_recording_events(raw),
                "meta": self._default_recording_meta(),
            }

        if not isinstance(raw, dict):
            return None

        raw_events = raw.get("events")
        if not isinstance(raw_events, list):
            return None

        return {
            "events": self._normalize_recording_events(raw_events),
            "meta": self._normalize_recording_meta(raw.get("meta")),
        }

    @staticmethod
    def _recording_events(package: dict[str, object] | None) -> list[dict[str, object]]:
        if not isinstance(package, dict):
            return []
        events = package.get("events")
        if isinstance(events, list):
            return events
        return []

    @staticmethod
    def _recording_meta(package: dict[str, object] | None) -> dict[str, object]:
        if not isinstance(package, dict):
            return {}
        meta = package.get("meta")
        if isinstance(meta, dict):
            return meta
        return {}

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
            return key.char

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
                tokens.add(token.lower())
        return tokens

    def _on_recording_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        token = self._key_to_token(key)
        if token is None:
            return

        if token.lower() in self._control_hotkey_tokens():
            return

        self._record_event("key_press", {"key": token})

    def _on_recording_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        token = self._key_to_token(key)
        if token is None:
            return

        if token.lower() in self._control_hotkey_tokens():
            return

        self._record_event("key_release", {"key": token})

    def _recording_coordinate_mode(self) -> str:
        mode = self.recording_coordinate_mode_var.get().strip().lower()
        if mode in {"absolute", "window_relative"}:
            return mode
        return "absolute"

    def _recorded_point_payload(self, x: int, y: int, extra: dict[str, object] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {"x": int(x), "y": int(y)}
        if extra:
            payload.update(extra)

        if self._recording_coordinate_mode() == "window_relative" and self.recording_anchor_rect is not None:
            payload["rx"] = int(x - self.recording_anchor_rect[0])
            payload["ry"] = int(y - self.recording_anchor_rect[1])
        return payload

    def _on_recording_mouse_move(self, x: float, y: float) -> None:
        now = time.monotonic()
        point = (int(x), int(y))
        if self.recording_last_move_pos == point and (now - self.recording_last_move_time) < 0.05:
            return

        self.recording_last_move_pos = point
        self.recording_last_move_time = now
        self._record_event("mouse_move", self._recorded_point_payload(point[0], point[1]))

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
            self._recorded_point_payload(
                int(x),
                int(y),
                {"button": token, "pressed": bool(pressed)},
            ),
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
            self._recorded_point_payload(
                int(x),
                int(y),
                {"dx": float(dx), "dy": float(dy)},
            ),
        )

    def _start_recording_capture(self) -> bool:
        if self.recording_active:
            return True

        self.recording_events = []
        self.recording_started_at = time.monotonic()
        self.recording_last_move_time = 0.0
        self.recording_last_move_pos = None
        self.recording_anchor_title, self.recording_anchor_rect = self._foreground_window_info()

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
            mode = self._recording_coordinate_mode()
            if mode == "window_relative" and self.recording_anchor_rect is not None:
                self._set_status(
                    "Recording started (window-relative). Press record hotkey again to stop/save temporary."
                )
            elif mode == "window_relative":
                self._set_status(
                    "Recording started (window-relative requested, no window anchor available)."
                )
            else:
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

    def _current_recording_package(self) -> dict[str, object]:
        meta = self._default_recording_meta()
        meta["coordinate_mode"] = self._recording_coordinate_mode()
        meta["anchor_title"] = self.recording_anchor_title
        if self.recording_anchor_rect is not None:
            meta["anchor_rect"] = list(self.recording_anchor_rect)
        return {
            "events": self._serialize_recording_events(),
            "meta": meta,
        }

    def _toggle_recording_hotkey(self) -> None:
        if self.recording_active:
            self._stop_recording_capture()
            package = self._current_recording_package()
            serialized = self._recording_events(package)
            self.recordings[TEMP_RECORDING_NAME] = package
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
        if temp is None:
            self._set_status("No temporary recording available")
            return
        temp_events = self._recording_events(temp)
        if not temp_events:
            self._set_status("No temporary recording available")
            return

        self.recordings[name] = copy.deepcopy(temp)
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

        cleaned: dict[str, dict[str, object]] = {}
        if isinstance(data, dict):
            for name, raw_package in data.items():
                if not isinstance(name, str):
                    continue
                normalized = self._normalize_recording_package(raw_package)
                if normalized is not None:
                    cleaned[name] = normalized

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
        if not current and names:
            self.selected_recording_var.set(names[0])
            current = names[0]
        if current and current not in self.recordings:
            self.selected_recording_var.set(names[0] if names else "")
        self._refresh_macro_editor()

    def _on_recording_selected(self, _event: tk.Event | None = None) -> None:
        self._refresh_macro_editor()

    @staticmethod
    def _macro_event_summary(event_type: str, payload: dict[str, object]) -> str:
        if event_type in {"mouse_move", "mouse_click", "mouse_scroll"}:
            x = payload.get("x", "")
            y = payload.get("y", "")
            if "rx" in payload and "ry" in payload:
                return f"x={x}, y={y}, rx={payload.get('rx')}, ry={payload.get('ry')}"
            return f"x={x}, y={y}"
        if event_type in {"key_press", "key_release"}:
            return f"key={payload.get('key', '')}"
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _event_delays(events: list[dict[str, object]]) -> list[float]:
        delays: list[float] = []
        prev_t = 0.0
        for index, event in enumerate(events):
            t_val = float(event.get("t", 0.0))
            if index == 0:
                delays.append(max(0.0, t_val))
            else:
                delays.append(max(0.0, t_val - prev_t))
            prev_t = t_val
        return delays

    @staticmethod
    def _apply_event_delays(events: list[dict[str, object]], delays: list[float]) -> None:
        t_val = 0.0
        for index, event in enumerate(events):
            delay = delays[index] if index < len(delays) else 0.0
            if index == 0:
                t_val = max(0.0, delay)
            else:
                t_val += max(0.0, delay)
            event["t"] = round(t_val, 6)

    def _selected_recording_package(self) -> dict[str, object] | None:
        name = self.selected_recording_var.get().strip()
        package = self.recordings.get(name)
        if package is None:
            return None
        return package

    def _refresh_macro_editor(self) -> None:
        if self.macro_step_tree is None:
            return

        current_selection = self._selected_macro_step_index()
        self.macro_step_tree.delete(*self.macro_step_tree.get_children())

        package = self._selected_recording_package()
        events = self._recording_events(package)
        if not events:
            self.macro_selected_step_var.set("No step selected")
            self.macro_step_delay_var.set("0.000")
            self.macro_step_type_var.set("")
            self.macro_step_payload_var.set("")
            return

        delays = self._event_delays(events)
        for index, event in enumerate(events):
            event_type = str(event.get("type", ""))
            payload = event.get("payload")
            payload_dict = payload if isinstance(payload, dict) else {}
            summary = self._macro_event_summary(event_type, payload_dict)
            self.macro_step_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(index + 1, f"{delays[index]:.3f}", event_type, summary),
            )

        target_index = current_selection if current_selection is not None else 0
        target_index = max(0, min(target_index, len(events) - 1))
        self.macro_step_tree.selection_set(str(target_index))
        self.macro_step_tree.focus(str(target_index))
        self.macro_step_tree.see(str(target_index))
        self._load_macro_step_fields(target_index)

    def _selected_macro_step_index(self) -> int | None:
        if self.macro_step_tree is None:
            return None
        selected = self.macro_step_tree.selection()
        if not selected:
            return None
        try:
            return int(selected[0])
        except (TypeError, ValueError):
            return None

    def _load_macro_step_fields(self, index: int) -> None:
        package = self._selected_recording_package()
        events = self._recording_events(package)
        if not (0 <= index < len(events)):
            return

        delays = self._event_delays(events)
        event = events[index]
        payload = event.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        self.macro_selected_step_var.set(f"Selected step #{index + 1}")
        self.macro_step_delay_var.set(f"{delays[index]:.3f}")
        self.macro_step_type_var.set(str(event.get("type", "")))
        self.macro_step_payload_var.set(json.dumps(payload_dict, ensure_ascii=True, separators=(",", ":")))

    def _on_macro_step_selected(self, _event: tk.Event | None = None) -> None:
        index = self._selected_macro_step_index()
        if index is None:
            return
        self._load_macro_step_fields(index)

    def _save_recordings_after_editor_change(self) -> bool:
        if not self._save_recordings_to_disk():
            return False
        self._refresh_macro_editor()
        return True

    def _apply_macro_step_edit(self) -> None:
        package = self._selected_recording_package()
        events = self._recording_events(package)
        index = self._selected_macro_step_index()
        if package is None or index is None or not (0 <= index < len(events)):
            self._set_status("Select a recording step first")
            return

        try:
            delay_seconds = float(self.macro_step_delay_var.get().strip())
            if delay_seconds < 0:
                raise ValueError
        except ValueError:
            self._set_status("Delay must be a non-negative number")
            return

        step_type = self.macro_step_type_var.get().strip()
        if step_type not in {"key_press", "key_release", "mouse_move", "mouse_click", "mouse_scroll"}:
            self._set_status("Invalid step type")
            return

        payload_raw = self.macro_step_payload_var.get().strip()
        if not payload_raw:
            payload_raw = "{}"
        try:
            payload_obj = json.loads(payload_raw)
        except json.JSONDecodeError:
            self._set_status("Payload JSON is invalid")
            return
        if not isinstance(payload_obj, dict):
            self._set_status("Payload JSON must decode to an object")
            return

        delays = self._event_delays(events)
        delays[index] = delay_seconds
        events[index]["type"] = step_type
        events[index]["payload"] = payload_obj
        self._apply_event_delays(events, delays)
        if self._save_recordings_after_editor_change():
            self._set_status(f"Updated step #{index + 1}")

    def _move_macro_step_up(self) -> None:
        package = self._selected_recording_package()
        events = self._recording_events(package)
        index = self._selected_macro_step_index()
        if package is None or index is None or index <= 0 or index >= len(events):
            return

        delays = self._event_delays(events)
        events[index - 1], events[index] = events[index], events[index - 1]
        delays[index - 1], delays[index] = delays[index], delays[index - 1]
        self._apply_event_delays(events, delays)
        if self._save_recordings_after_editor_change():
            if self.macro_step_tree is not None:
                self.macro_step_tree.selection_set(str(index - 1))
            self._set_status(f"Moved step #{index + 1} up")

    def _move_macro_step_down(self) -> None:
        package = self._selected_recording_package()
        events = self._recording_events(package)
        index = self._selected_macro_step_index()
        if package is None or index is None or not (0 <= index < len(events) - 1):
            return

        delays = self._event_delays(events)
        events[index], events[index + 1] = events[index + 1], events[index]
        delays[index], delays[index + 1] = delays[index + 1], delays[index]
        self._apply_event_delays(events, delays)
        if self._save_recordings_after_editor_change():
            if self.macro_step_tree is not None:
                self.macro_step_tree.selection_set(str(index + 1))
            self._set_status(f"Moved step #{index + 1} down")

    def _delete_macro_step(self) -> None:
        package = self._selected_recording_package()
        events = self._recording_events(package)
        index = self._selected_macro_step_index()
        if package is None or index is None or not (0 <= index < len(events)):
            return

        del events[index]
        if events:
            delays = self._event_delays(events)
            delays[0] = 0.0
            self._apply_event_delays(events, delays)

        if self._save_recordings_after_editor_change():
            self._set_status(f"Deleted step #{index + 1}")

    def _play_recording_hotkey(self) -> None:
        self._play_selected_recording_once()

    def _play_selected_recording_once(self) -> None:
        name = self.selected_recording_var.get().strip()
        if not name:
            self._set_status("No recording selected")
            return

        package = self.recordings.get(name)
        events = self._recording_events(package)
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
        played = self._play_recording_events(
            package,
            speed,
            local_stop,
            dry_run=self.macro_dry_run_var.get(),
            reanchor_window=self.macro_reanchor_window_var.get(),
        )
        if played:
            self._set_status(f"Played recording '{name}'")

    def _parse_recorded_key_token(self, token: str) -> keyboard.Key | keyboard.KeyCode | None:
        if len(token) == 1:
            return keyboard.KeyCode.from_char(token)
        return self._parse_keyboard_key(token)

    def _build_recording_playback_context(
        self,
        package: dict[str, object] | None,
        reanchor_window: bool,
    ) -> dict[str, object]:
        meta = self._recording_meta(package)
        coordinate_mode = str(meta.get("coordinate_mode", "absolute")).strip().lower()
        if coordinate_mode not in {"absolute", "window_relative"}:
            coordinate_mode = "absolute"

        anchor_rect = self._normalize_anchor_rect(meta.get("anchor_rect"))
        _, current_rect = self._foreground_window_info()

        offset_x = 0
        offset_y = 0
        if reanchor_window and anchor_rect is not None and current_rect is not None:
            offset_x = int(current_rect[0] - anchor_rect[0])
            offset_y = int(current_rect[1] - anchor_rect[1])

        target_rect = anchor_rect
        if reanchor_window and current_rect is not None:
            target_rect = current_rect

        return {
            "coordinate_mode": coordinate_mode,
            "anchor_rect": anchor_rect,
            "target_rect": target_rect,
            "offset_x": offset_x,
            "offset_y": offset_y,
        }

    def _resolve_playback_point(
        self,
        payload: dict[str, object],
        playback_context: dict[str, object],
    ) -> tuple[int, int]:
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))

        coordinate_mode = str(playback_context.get("coordinate_mode", "absolute"))
        target_rect = playback_context.get("target_rect")
        if coordinate_mode == "window_relative" and isinstance(target_rect, tuple):
            if "rx" in payload and "ry" in payload:
                try:
                    rel_x = int(float(payload.get("rx", 0)))
                    rel_y = int(float(payload.get("ry", 0)))
                    return int(target_rect[0] + rel_x), int(target_rect[1] + rel_y)
                except (TypeError, ValueError):
                    pass

        offset_x = int(playback_context.get("offset_x", 0))
        offset_y = int(playback_context.get("offset_y", 0))
        return x + offset_x, y + offset_y

    def _play_recording_events(
        self,
        package: dict[str, object] | None,
        speed: float,
        stop_event: threading.Event,
        dry_run: bool,
        reanchor_window: bool,
    ) -> bool:
        normalized = self._normalize_recording_events(self._recording_events(package))
        if not normalized:
            return False

        playback_context = self._build_recording_playback_context(package, reanchor_window)
        if dry_run:
            self._schedule_dry_run_overlay_clear()

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
            if dry_run:
                self._visualize_recording_event(event_type, payload, playback_context)
            else:
                self._execute_recording_event(event_type, payload, playback_context)

        if dry_run:
            self._schedule_dry_run_overlay_clear()
        return True

    def _execute_recording_event(
        self,
        event_type: str,
        payload: dict[str, object],
        playback_context: dict[str, object],
    ) -> None:
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
                x, y = self._resolve_playback_point(payload, playback_context)
                self.mouse_controller.position = (x, y)
                return

            if event_type == "mouse_click":
                x, y = self._resolve_playback_point(payload, playback_context)
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
                x, y = self._resolve_playback_point(payload, playback_context)
                dx = int(float(payload.get("dx", 0.0)))
                dy = int(float(payload.get("dy", 0.0)))
                self.mouse_controller.position = (x, y)
                self.mouse_controller.scroll(dx, dy)
        except Exception:
            return

    def _visualize_recording_event(
        self,
        event_type: str,
        payload: dict[str, object],
        playback_context: dict[str, object],
    ) -> None:
        if event_type not in {"mouse_move", "mouse_click", "mouse_scroll"}:
            return
        x, y = self._resolve_playback_point(payload, playback_context)
        try:
            self.root.after(0, lambda px=x, py=y, et=event_type: self._draw_dry_run_marker(px, py, et))
        except tk.TclError:
            return

    def _schedule_dry_run_overlay_clear(self) -> None:
        try:
            self.root.after(0, self._schedule_dry_run_overlay_clear_on_ui)
        except tk.TclError:
            pass

    def _schedule_dry_run_overlay_clear_on_ui(self) -> None:
        if self.dry_run_clear_after_id is not None:
            try:
                self.root.after_cancel(self.dry_run_clear_after_id)
            except tk.TclError:
                pass
            self.dry_run_clear_after_id = None
        try:
            self.dry_run_clear_after_id = self.root.after(1200, self._destroy_dry_run_overlay)
        except tk.TclError:
            self.dry_run_clear_after_id = None

    def _ensure_dry_run_overlay(self) -> bool:
        if self.dry_run_overlay is not None and self.dry_run_canvas is not None:
            try:
                if self.dry_run_overlay.winfo_exists():
                    return True
            except tk.TclError:
                pass

        x1, y1, x2, y2 = self._virtual_screen_bounds()
        if x1 == x2 and y1 == y2:
            x1, y1 = 0, 0
            x2 = self.root.winfo_screenwidth()
            y2 = self.root.winfo_screenheight()

        width = max(1, x2 - x1)
        height = max(1, y2 - y1)

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{width}x{height}+{x1}+{y1}")

        transparent_bg = "#113355"
        overlay.configure(bg=transparent_bg)
        try:
            overlay.wm_attributes("-transparentcolor", transparent_bg)
        except tk.TclError:
            overlay.attributes("-alpha", 0.2)

        canvas = tk.Canvas(overlay, bg=transparent_bg, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        self._make_overlay_click_through(overlay)

        self.dry_run_overlay = overlay
        self.dry_run_canvas = canvas
        self.dry_run_overlay_origin = (x1, y1)
        self.dry_run_last_point = None
        return True

    def _draw_dry_run_marker(self, x: int, y: int, event_type: str) -> None:
        if not self._ensure_dry_run_overlay():
            return
        if self.dry_run_canvas is None:
            return

        canvas = self.dry_run_canvas
        origin_x, origin_y = self.dry_run_overlay_origin
        px = x - origin_x
        py = y - origin_y

        if self.dry_run_last_point is not None and event_type in {"mouse_move", "mouse_click", "mouse_scroll"}:
            lx, ly = self.dry_run_last_point
            canvas.create_line(lx, ly, px, py, fill="#60a5fa", width=2, tags="dry-run")

        if event_type == "mouse_click":
            canvas.create_oval(px - 8, py - 8, px + 8, py + 8, outline="#ef4444", width=2, tags="dry-run")
        elif event_type == "mouse_scroll":
            canvas.create_rectangle(px - 7, py - 7, px + 7, py + 7, outline="#f59e0b", width=2, tags="dry-run")
        else:
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#22c55e", outline="", tags="dry-run")

        self.dry_run_last_point = (px, py)
        self._schedule_dry_run_overlay_clear_on_ui()

    def _destroy_dry_run_overlay(self) -> None:
        self.dry_run_last_point = None
        if self.dry_run_clear_after_id is not None:
            try:
                self.root.after_cancel(self.dry_run_clear_after_id)
            except tk.TclError:
                pass
            self.dry_run_clear_after_id = None

        if self.dry_run_overlay is not None:
            try:
                self.dry_run_overlay.destroy()
            except tk.TclError:
                pass
        self.dry_run_overlay = None
        self.dry_run_canvas = None

    @staticmethod
    def _make_overlay_click_through(window: tk.Toplevel) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(window.winfo_id())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
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
        self._make_overlay_click_through(overlay)

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

        condition_logic_mode = "and"

        color_trigger_mode = self.color_trigger_mode_var.get().strip().lower()
        if color_trigger_mode not in {"continuous", "single"}:
            self._set_status("Color trigger mode must be continuous or single")
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
            recording_package = self.recordings.get(selected_recording_name)
            recording_events = self._recording_events(recording_package)
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
            edge_trigger_enabled=(color_trigger_mode == "single"),
            anti_detection_enabled=self.anti_detection_enabled_var.get(),
            anti_detection_jitter_pct=anti_detection_jitter_pct,
            anti_detection_pause_chance=anti_detection_pause_chance,
            anti_detection_max_pause=anti_detection_max_pause,
            use_macro_recording=use_macro_recording,
            selected_recording_name=selected_recording_name,
            macro_speed=macro_speed,
            macro_reanchor_window=self.macro_reanchor_window_var.get(),
            macro_dry_run=self.macro_dry_run_var.get(),
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

    def _append_run_log(self, entry: dict[str, object]) -> None:
        try:
            with open(self.run_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception as exc:
            self._set_status(f"Failed writing run log: {exc}")

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _click_loop(self, settings: ClickSettings) -> None:
        run_started_at = datetime.utcnow()
        run_id = run_started_at.strftime("%Y%m%dT%H%M%S.%fZ")

        if self._countdown_start_delay(settings.start_delay):
            self.running = False
            self._set_status("Stopped")
            return

        click_count = 0
        run_start = time.monotonic()
        stop_reason: str | None = None
        fire_count = 0
        macro_playback_count = 0
        condition_counts: dict[str, int] = {
            "iterations": 0,
            "color_pass": 0,
            "color_fail": 0,
            "window_pass": 0,
            "window_fail": 0,
            "time_pass": 0,
            "time_fail": 0,
            "combined_true": 0,
            "combined_false": 0,
        }

        self._set_status("Running")
        self._set_session_info(click_count, 0.0)

        while not self.stop_event.is_set():
            if self.paused:
                time.sleep(0.05)
                continue

            condition_counts["iterations"] += 1
            elapsed = time.monotonic() - run_start
            if settings.stop_after_seconds is not None and elapsed >= settings.stop_after_seconds:
                stop_reason = f"Stopped: reached {settings.stop_after_seconds:.2f}s limit"
                break

            enabled_condition_results: list[bool] = []
            if settings.use_color:
                color_match = self._sample_matches_color(settings)
                enabled_condition_results.append(color_match)
                if color_match:
                    condition_counts["color_pass"] += 1
                else:
                    condition_counts["color_fail"] += 1

            if settings.window_binding_enabled:
                current_title = self._current_window_title().lower()
                window_match = settings.window_title_rule.lower() in current_title
                enabled_condition_results.append(window_match)
                if window_match:
                    condition_counts["window_pass"] += 1
                else:
                    condition_counts["window_fail"] += 1

            if settings.time_window_enabled:
                time_match = self._time_window_allows(settings.allowed_start_time, settings.allowed_end_time)
                enabled_condition_results.append(time_match)
                if time_match:
                    condition_counts["time_pass"] += 1
                else:
                    condition_counts["time_fail"] += 1

            should_fire = evaluate_rule_conditions(enabled_condition_results, settings.condition_logic_mode)
            if should_fire:
                condition_counts["combined_true"] += 1
            else:
                condition_counts["combined_false"] += 1

            if should_fire:
                fire_count += 1
                if settings.use_macro_recording:
                    if settings.stop_after_clicks is not None and click_count >= settings.stop_after_clicks:
                        stop_reason = f"Stopped: reached {settings.stop_after_clicks} action limit"
                        break

                    package = self.recordings.get(settings.selected_recording_name)
                    played = self._play_recording_events(
                        package,
                        settings.macro_speed,
                        self.stop_event,
                        dry_run=settings.macro_dry_run,
                        reanchor_window=settings.macro_reanchor_window,
                    )
                    if played:
                        click_count += 1
                        macro_playback_count += 1
                else:
                    burst_count = settings.burst_count
                    if settings.use_color and settings.edge_trigger_enabled:
                        burst_count = 1
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
        if stop_reason is None:
            stop_reason = "Stopped by user" if self.stop_event.is_set() else "Stopped"
        self._set_status(stop_reason)

        run_ended_at = datetime.utcnow()
        elapsed = max(0.0, time.monotonic() - run_start)
        iterations = condition_counts["iterations"]
        run_log_entry: dict[str, object] = {
            "run_id": run_id,
            "started_at": run_started_at.isoformat(timespec="seconds") + "Z",
            "ended_at": run_ended_at.isoformat(timespec="seconds") + "Z",
            "duration_s": round(elapsed, 3),
            "stop_reason": stop_reason,
            "mode": "macro" if settings.use_macro_recording else "action",
            "selected_recording": settings.selected_recording_name if settings.use_macro_recording else "",
            "macro_speed": settings.macro_speed,
            "macro_reanchor_window": settings.macro_reanchor_window,
            "macro_dry_run": settings.macro_dry_run,
            "action_count": click_count,
            "fires": fire_count,
            "macro_playbacks": macro_playback_count,
            "condition_checks": {
                "iterations": iterations,
                "logic_mode": settings.condition_logic_mode,
                "color": {
                    "enabled": settings.use_color,
                    "pass": condition_counts["color_pass"],
                    "fail": condition_counts["color_fail"],
                    "pass_rate": self._safe_ratio(
                        condition_counts["color_pass"],
                        condition_counts["color_pass"] + condition_counts["color_fail"],
                    ),
                },
                "window": {
                    "enabled": settings.window_binding_enabled,
                    "pass": condition_counts["window_pass"],
                    "fail": condition_counts["window_fail"],
                    "pass_rate": self._safe_ratio(
                        condition_counts["window_pass"],
                        condition_counts["window_pass"] + condition_counts["window_fail"],
                    ),
                },
                "time": {
                    "enabled": settings.time_window_enabled,
                    "pass": condition_counts["time_pass"],
                    "fail": condition_counts["time_fail"],
                    "pass_rate": self._safe_ratio(
                        condition_counts["time_pass"],
                        condition_counts["time_pass"] + condition_counts["time_fail"],
                    ),
                },
                "combined": {
                    "true": condition_counts["combined_true"],
                    "false": condition_counts["combined_false"],
                    "true_rate": self._safe_ratio(condition_counts["combined_true"], iterations),
                },
            },
        }
        self._append_run_log(run_log_entry)

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
            "color_trigger_mode_var",
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
            "recording_coordinate_mode_var",
            "macro_reanchor_window_var",
            "macro_dry_run_var",
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

        if "color_trigger_mode_var" not in payload:
            self.color_trigger_mode_var.set("single" if self.edge_trigger_var.get() else "continuous")
        self.condition_logic_mode_var.set("and")

        if self.monitor_var.get() not in self.monitor_options:
            self.monitor_var.set(next(iter(self.monitor_options.keys()), "All monitors"))

        self._sync_action_controls()
        self._sync_hold_controls()
        self._sync_timing_controls()
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
        self._destroy_dry_run_overlay()
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
