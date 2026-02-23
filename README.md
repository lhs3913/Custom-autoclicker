# Custom Auto Clicker (Python)

Desktop auto clicker with mouse/keyboard actions, rule-based triggers, macro recording, and profile management.

## Features

- Action targets:
  - Mouse (`left` / `right` / `middle`)
  - Keyboard keys (letters and supported special keys)
- Action behavior:
  - Tap
  - Hold (press duration)
  - Burst (N actions per cycle with configurable gap)
- Timing:
  - Fixed interval
  - Randomized min/max interval
  - Anti-detection model (jitter + random micro-pauses)
- Rule engine:
  - Combine enabled conditions with `AND` or `OR`
  - Conditions include color match, window title binding, and local time window
- Color trigger tools:
  - Cursor, fixed point, or region sampling
  - Optional monitor filter
  - Edge-trigger mode (non-match -> match)
  - Inkdropper with lock key capture
  - Pixel history panel
  - Optional crosshair overlay
- Window binding:
  - Active window title contains rule text
  - One-click capture from the current foreground window (Windows)
- Macro recording:
  - Record global keyboard/mouse input with timing
  - Start/stop recording via hotkey or button
  - Temporary recording storage plus named saves
  - Play selected recording once or use it as the action cycle
  - Playback speed control
- Safety:
  - Start delay with countdown
  - Stop after N actions and/or N seconds
- Profiles:
  - Save/load/delete profiles in `profiles.json`
  - Optional profile-specific hotkey apply on load
- Built-in testing playground:
  - Dedicated test window for click targets, color wheel checks, key counting, and recording scenarios

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`
- OS permissions for global input and screen capture (as needed by your platform)

## Install

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Then install dependencies:

```bash
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

Inkdrop lock key default: `s` (single key).

## Recording Workflow

1. Press the record hotkey to start recording.
2. Perform mouse/keyboard actions.
3. Press the record hotkey again to stop and save as `(temporary)`.
4. Optionally save `(temporary)` as a named recording.
5. Select a recording and play once, or enable `Use selected recording instead of single click action`.

## Files

- `profiles.json`: saved profiles
- `recordings.json`: saved macro recordings

## Testing

- No automated unit/integration tests are currently included in this repository.
- Use the in-app `Open test window` playground for manual validation.
