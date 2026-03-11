# KDE Teleprompter

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux%20%2F%20KDE%20Plasma-1d99f3?logo=kde&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-cba6f7)

A lightweight, frameless teleprompter for **Linux / KDE Plasma**, inspired by NotchPrompter.
Built with **PyQt6** — no Electron, no browser, no bloat.

```
┌──────────────────────────────────────┐
│                                      │
│      The text scrolls upward         │
│    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │  ← fade out
│   ████  smoothly, centred,  ████     │  ← full opacity (centre)
│    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    │  ← fade out
│                                      │
│ [ ⏸ ][ ⏮ ][ ✏ ]  Speed ──●──  Font ──●──  [ ✕ ] ⠿ │  ← control bar (on hover)
└──────────────────────────────────────┘
```

---

## Features

- **Always-on-top, frameless window** — sits above your video software
- **Smooth 60 fps scroll** driven by a 16 ms QTimer
- **Quadratic alpha fade** — lines near the centre are fully opaque; edges fade out gracefully
- **Hover to pause** — moving the pointer over the window pauses scrolling and reveals controls
- **Drag to reposition** anywhere on screen; **grip to resize**
- **Script editor** with file-load support (plain `.txt`)
- **Speed & font-size sliders** in the control bar
- **Mouse wheel** and **keyboard shortcuts** for quick adjustments
- **Catppuccin Mocha** colour scheme

---

## Requirements

| Dependency | Version |
|------------|---------|
| Python     | ≥ 3.10  |
| PyQt6      | ≥ 6.4.0 |

---

## Installation

```bash
# Clone or download the project
cd teleprompter/

# Install the only dependency
pip install -r requirements.txt

# Run
python kdeteleprompter.py
```

> **Tip (KDE):** Right-click the title bar → *More Actions → Keep Above Others* is not needed — the window sets this flag automatically.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `R` | Reset to beginning |
| `+` / `=` | Increase speed |
| `-` | Decrease speed |
| `Ctrl+E` | Open script editor |
| `Escape` | Close |

---

## Mouse controls

| Action | Effect |
|--------|--------|
| Scroll wheel | Adjust speed ±1 step |
| Left-click drag | Move window |
| Drag the grip (bottom-right) | Resize window |
| Hover | Pause scroll, show controls |
| Leave | Resume scroll, hide controls |

---

## Control bar

Appears automatically when the pointer enters the window.

| Control | Range | Default | Description |
|---------|-------|---------|-------------|
| ⏸ / ▶ button | — | Playing | Toggle pause |
| ⏮ button | — | — | Reset scroll to top |
| ✏ button | — | — | Open script editor |
| Speed slider | 1 – 30 | 5 | Scroll speed (× 0.1 px/frame = 0.1 – 3.0 px/frame) |
| Font slider | 10 – 72 pt | 28 pt | Display font size |
| ✕ button | — | — | Close the application |

---

## Project structure

```
teleprompter/
├── kdeteleprompter.py   # Single-file application (~320 lines)
└── requirements.txt     # PyQt6>=6.4.0
```

### Class overview

```
TeleprompterWindow (QMainWindow)
├── ScrollDisplay (QWidget)   — QPainter-based animated canvas
├── ControlBar    (QWidget)   — hover-revealed control strip
└── EditorDialog  (QDialog)   — script editor (modal)
```

---

## Colour scheme

All colours follow the **Catppuccin Mocha** palette:

| Role | Colour |
|------|--------|
| Background | `rgb(11, 11, 17)` |
| Text | `#cdd6f4` |
| Accent / UI | `#cba6f7` (mauve) |
| Bar background | `rgba(30, 30, 46, 210)` |

---

## Attribution

This project is a port of [NotchPrompter](https://github.com/jpomykala/NotchPrompter)
by Jan Pomykala to **KDE Plasma**, rewritten from scratch in **PyQt6** for Linux.

Original project licensed under MIT.

---

## License

MIT License — see [LICENSE](LICENSE) for the full text.

Copyright (c) 2024 Jan Pomykala
Copyright (c) 2026 Eduardo Collado
