# Custom Auto Clicker (Python)

Desktop auto clicker with mouse/keyboard actions, color/rule triggers, macro recording, and profile management.

## Features

- Action type:
  - Mouse (`left`/`right`/`middle`)
  - Keyboard key (case-insensitive)
- Action behavior:
  - Tap mode
  - Hold mode (press and hold duration)
  - Burst mode (N actions per cycle + configurable gap)
- Timing:
  - Fixed interval
  - Randomized interval range
  - Anti-detection timing model (jitter + random micro-pauses)
- Color trigger:
  - Cursor, fixed point, or region sample
  - Optional monitor filter
  - Edge-trigger mode (fire only on non-match -> match transition)
  - Inkdropper lock key capture
  - Pixel history panel
- Rule engine:
  - Combine enabled conditions with `AND` or `OR`
  - Conditions include color match, window title binding, and time window
- Window binding:
  - Active window title contains rule
  - One-click capture from current foreground window
- Macro / recording:
  - Record global keyboard/mouse input with coordinates + timing
  - Start/stop recording via hotkey (or button)
  - Temporary recording storage plus named recording save
  - Recording dropdown selection and playback
  - Optional mode to use selected macro as the action cycle
- Safety:
  - Start delay with countdown
  - Stop after N actions and/or N seconds
- Profiles:
  - Save/load/delete profiles to `profiles.json`
  - Per-profile hotkeys (optional auto-apply on profile load)

## Requirements

- Python 3.10+
- OS permissions for global input/screen capture if required by your platform

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python autoclicker.py
```

## Hotkeys

Default hotkeys:

- Start/Stop: `<f8>`
- Pause/Resume: `<f9>`
- Record toggle: `<f6>`
- Play selected recording: `<f7>`

Inkdrop lock key defaults to `s` (single key, case-insensitive).

## Recording Workflow

1. Press the record hotkey to start recording.
2. Perform mouse/keyboard actions across windows.
3. Press the record hotkey again to stop; recording is saved as `(temporary)`.
4. Optionally save `(temporary)` as a named recording.
5. Select a recording in dropdown and play once, or enable “Use selected recording”.

## Files

- `profiles.json`: saved profiles
- `recordings.json`: saved macro recordings

## Tests

Run logic tests:

```bash
python -m unittest -v
```
