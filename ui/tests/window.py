from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def open_test_window(app, initial_tab: str = "overview") -> None:
    if app.test_window is not None:
        try:
            if app.test_window.winfo_exists():
                if app.test_notebook is not None and initial_tab in app.test_tab_frames:
                    app.test_notebook.select(app.test_tab_frames[initial_tab])
                app.test_window.deiconify()
                app.test_window.lift()
                app.test_window.focus_force()
                return
        except tk.TclError:
            app.test_window = None
            app.test_notebook = None
            app.test_tab_frames = {}

    window = tk.Toplevel(app.root)
    window.title("Autoclicker Testing Window")
    window.geometry("980x760")
    window.minsize(780, 560)
    window.transient(app.root)
    window.protocol("WM_DELETE_WINDOW", app._close_test_window)
    window.bind("<KeyPress>", app._on_test_window_key_press, add="+")
    app.test_window = window

    app._reset_test_window_state()

    container = ttk.Frame(window, padding=12)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

    ttk.Label(
        container,
        text="Testing Playground",
        font=("Segoe UI", 13, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        container,
        text="Each test has its own tab so you can extend them independently.",
        foreground="#4b5563",
    ).grid(row=1, column=0, sticky="w", pady=(2, 10))

    notebook = ttk.Notebook(container)
    notebook.grid(row=2, column=0, sticky="nsew")
    app.test_notebook = notebook

    overview_tab = ttk.Frame(notebook, padding=10)
    click_tab = ttk.Frame(notebook, padding=10)
    color_tab = ttk.Frame(notebook, padding=10)
    letters_tab = ttk.Frame(notebook, padding=10)
    obstacle_tab = ttk.Frame(notebook, padding=10)
    notebook.add(overview_tab, text="Overview")
    notebook.add(click_tab, text="Click Targets")
    notebook.add(color_tab, text="Inkdrop Colors")
    notebook.add(letters_tab, text="Letter Counter")
    notebook.add(obstacle_tab, text="Recording Obstacles")
    app.test_tab_frames = {
        "overview": overview_tab,
        "click": click_tab,
        "color": color_tab,
        "letters": letters_tab,
        "obstacle": obstacle_tab,
    }

    app._build_test_overview_tab(overview_tab)
    app._build_test_click_tab(click_tab)
    app._build_test_color_tab(color_tab)
    app._build_test_letter_tab(letters_tab)
    app._build_test_obstacle_tab(obstacle_tab)

    if initial_tab in app.test_tab_frames:
        notebook.select(app.test_tab_frames[initial_tab])

    app._set_status("Testing window opened")


