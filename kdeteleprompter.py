#!/usr/bin/env python3
"""KDE Teleprompter — NotchPrompter-style for Linux/KDE Plasma."""

import sys
import signal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QSizeGrip, QDialog, QTextEdit,
    QFileDialog, QDialogButtonBox, QListWidget,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QLinearGradient,
    QPalette, QKeySequence, QShortcut,
)

try:
    import pyaudio
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

# ── Colour palette (Catppuccin Mocha) ────────────────────────────────────────
BG        = QColor(11, 11, 17)           # near-black background
ACCENT    = QColor(0xcb, 0xa6, 0xf7)    # mauve/purple accent
TEXT_CLR  = QColor(205, 214, 244)       # main text colour
BAR_BG    = QColor(30, 30, 46, 210)     # surface0, semi-transparent (unused; kept for reference)
FADE_CLR  = QColor(0, 0, 0, 0)         # fully transparent — used as gradient endpoint

SAMPLE_TEXT = """\
Welcome to KDE Teleprompter!

Edit this text with the ✏ button or load a file.

The text scrolls upward automatically.
Hover over the window to pause scrolling
and reveal the control bar.

Use the scroll wheel or +/- keys
to adjust the scrolling speed.

Drag the window to reposition it.
Use the grip in the corner to resize.

Space  — Play / Pause
R      — Reset to beginning
M      — Activar / desactivar scroll por voz
Ctrl+E — Open text editor
Escape — Close
"""


# ── Word-wrap helper ─────────────────────────────────────────────────────────

def wrap_text(text: str, fm: QFontMetrics, max_w: int) -> list[str]:
    """Break *text* into display lines that fit within *max_w* pixels.

    Blank paragraphs are preserved as empty strings so spacing is kept.
    """
    result: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            # Preserve blank lines between paragraphs
            result.append("")
            continue
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = (line + " " + word).strip()
            if fm.horizontalAdvance(candidate) <= max_w:
                # Word still fits on the current line
                line = candidate
            else:
                # Word would overflow — flush current line and start a new one
                if line:
                    result.append(line)
                line = word
        if line:
            result.append(line)
    return result


# ── Scroll display ────────────────────────────────────────────────────────────

class ScrollDisplay(QWidget):
    """Full-widget canvas that paints the scrolling teleprompter text.

    Text is centred horizontally and fades out toward the top and bottom edges
    using a quadratic alpha falloff, so only the lines near the centre are
    fully opaque.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # WA_OpaquePaintEvent tells Qt we always paint the whole widget,
        # avoiding unnecessary background erasing before paintEvent.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(200, 100)

        self._text: str = SAMPLE_TEXT
        self._font_size: int = 28
        self._scroll: float = 0.0     # total pixels scrolled upward so far
        self._lines: list[str] = []   # word-wrapped display lines
        self._line_h: int = 0         # pixel height of one line (font height + leading)
        self._total_h: int = 0        # total pixel height of all lines combined

        self._rebuild_font()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_text(self, text: str):
        """Replace the script text and recompute line wrapping."""
        self._text = text
        self._prepare_lines()
        self.update()

    def set_font_size(self, pt: int):
        """Change the display font size (points) and rebuild all metrics."""
        self._font_size = pt
        self._rebuild_font()
        self._prepare_lines()
        self.update()

    def advance(self, px: float):
        """Scroll upward by *px* pixels.

        When the scroll position reaches the end of all text plus one full
        widget height, it wraps back to the top for continuous looping.
        """
        self._scroll += px
        loop_at = self._total_h + self.height()
        if loop_at > 0 and self._scroll >= loop_at:
            self._scroll = 0.0    # loop back to the beginning
        self.update()

    def reset(self):
        """Jump back to the very start of the script."""
        self._scroll = 0.0
        self.update()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _rebuild_font(self):
        """Create a new QFont/QFontMetrics pair for the current font size."""
        self._font = QFont("Sans Serif", self._font_size)
        self._font.setWeight(QFont.Weight.Medium)
        self._fm = QFontMetrics(self._font)
        # Add 6 px of leading between lines for readability
        self._line_h = self._fm.height() + 6

    def _prepare_lines(self):
        """Re-wrap the raw text to fit the current widget width."""
        # Leave 40 px of padding on each side; never go below 100 px
        max_w = max(self.width() - 80, 100)
        self._lines = wrap_text(self._text, self._fm, max_w)
        self._total_h = len(self._lines) * self._line_h

    def resizeEvent(self, event):
        # Widget dimensions changed — word-wrap must be recalculated
        self._prepare_lines()
        super().resizeEvent(event)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Fill background first (widget is marked opaque)
        painter.fillRect(0, 0, w, h, BG)

        painter.setFont(self._font)

        center_y = h / 2
        # The fade zone covers 90 % of the widget height (45 % on each side).
        # Lines outside this radius will be completely transparent.
        fade_zone = h * 0.45

        for i, line in enumerate(self._lines):
            # Baseline Y: start at the bottom of the viewport and travel up
            # as _scroll increases, so text appears to move upward over time.
            y = h - self._scroll + i * self._line_h + self._fm.ascent()

            # Skip lines that are entirely above or below the visible area
            if y < -self._line_h or y > h + self._line_h:
                continue

            # Distance from this line's midpoint to the widget centre
            dist = abs((y - self._fm.ascent() / 2) - center_y)

            # Quadratic falloff: alpha = 1 at centre, 0 at fade_zone radius
            ratio = max(0.0, 1.0 - (dist / fade_zone) ** 2)
            alpha = int(255 * ratio)
            if alpha <= 0:
                continue   # fully transparent — nothing to draw

            color = QColor(TEXT_CLR)
            color.setAlpha(alpha)
            painter.setPen(color)

            # Centre the line horizontally
            text_w = self._fm.horizontalAdvance(line)
            x = (w - text_w) // 2
            painter.drawText(x, int(y), line)

        # Paint gradient overlays last so they sit on top of the text
        self._draw_gradient(painter, w, h)
        painter.end()

    def _draw_gradient(self, painter: QPainter, w: int, h: int):
        """Draw top and bottom gradient bands that fade text into the background.

        Each band covers the outer 25 % of the widget height, creating a
        smooth transition from solid background colour to transparency.
        """
        fade_h = int(h * 0.25)

        # Top band: opaque BG at the very top fading to transparent
        grad_top = QLinearGradient(0, 0, 0, fade_h)
        grad_top.setColorAt(0.0, BG)
        grad_top.setColorAt(1.0, FADE_CLR)
        painter.fillRect(0, 0, w, fade_h, grad_top)

        # Bottom band: transparent fading to opaque BG at the very bottom
        grad_bot = QLinearGradient(0, h - fade_h, 0, h)
        grad_bot.setColorAt(0.0, FADE_CLR)
        grad_bot.setColorAt(1.0, BG)
        painter.fillRect(0, h - fade_h, w, fade_h, grad_bot)


# ── Control bar ───────────────────────────────────────────────────────────────

class ControlBar(QWidget):
    """Semi-transparent control bar that appears when the user hovers the window.

    Contains play/pause, reset, edit, mic and close buttons, sliders for scroll
    speed and font size, and a QSizeGrip for window resizing.
    """

    BAR_H = 54   # fixed height in pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.BAR_H)
        # WA_StyledBackground is required for the background colour set in the
        # stylesheet to actually be painted on a plain QWidget.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ControlBar {{
                background: rgba(30, 30, 46, 210);
                border-top: 1px solid rgba(203,166,247,60);
            }}
            QPushButton {{
                background: rgba(203,166,247,30);
                color: #cba6f7;
                border: 1px solid rgba(203,166,247,80);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: rgba(203,166,247,70);
            }}
            QPushButton:pressed {{
                background: rgba(203,166,247,120);
            }}
            QPushButton:disabled {{
                color: rgba(203,166,247,40);
                border-color: rgba(203,166,247,20);
            }}
            QLabel {{
                color: #a6adc8;
                font-size: 11px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(203,166,247,40);
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #cba6f7;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: rgba(203,166,247,150);
                border-radius: 2px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(8)

        # Action buttons (left side)
        self.btn_play  = self._btn("⏸", "Play / Pause  (Space)")
        self.btn_reset = self._btn("⏮", "Reset  (R)")
        self.btn_edit  = self._btn("✏", "Edit text  (Ctrl+E)")
        self.btn_mic   = self._btn("🎤", "Activar scroll por voz  (M)")
        self.btn_close = self._btn("✕", "Close  (Escape)")

        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_edit)
        layout.addWidget(self.btn_mic)

        layout.addSpacing(8)

        # Scroll-speed slider — value 1–30 maps to 0.1–3.0 px/frame in _tick()
        layout.addWidget(QLabel("Speed"))
        self.sld_speed = QSlider(Qt.Orientation.Horizontal)
        self.sld_speed.setRange(1, 30)
        self.sld_speed.setValue(5)       # default: 0.5 px/frame
        self.sld_speed.setFixedWidth(90)
        self.sld_speed.setToolTip("Scroll speed")
        layout.addWidget(self.sld_speed)

        layout.addSpacing(8)

        # Font-size slider — directly controls ScrollDisplay point size
        layout.addWidget(QLabel("Font"))
        self.sld_font = QSlider(Qt.Orientation.Horizontal)
        self.sld_font.setRange(10, 72)
        self.sld_font.setValue(28)       # default: 28 pt
        self.sld_font.setFixedWidth(90)
        self.sld_font.setToolTip("Font size (pt)")
        layout.addWidget(self.sld_font)

        layout.addStretch()

        # Close button stays on the far right
        layout.addWidget(self.btn_close)

        # Size grip — lets the user drag-resize the frameless window
        grip = QSizeGrip(self)
        grip.setFixedSize(18, 18)
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom)

    @staticmethod
    def _btn(text: str, tip: str) -> QPushButton:
        """Create a small square icon button with a tooltip."""
        b = QPushButton(text)
        b.setToolTip(tip)
        b.setFixedSize(36, 36)
        return b


# ── Editor dialog ─────────────────────────────────────────────────────────────

class EditorDialog(QDialog):
    """Modal dialog for editing the teleprompter script.

    The user can type directly in the text area or click "Load file…" to
    replace the contents with a plain-text file from disk.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Script")
        self.resize(600, 420)
        self.setStyleSheet("""
            QDialog { background: #1e1e2e; color: #cdd6f4; }
            QTextEdit {
                background: #181825;
                color: #cdd6f4;
                border: 1px solid rgba(203,166,247,60);
                border-radius: 6px;
                font-family: monospace;
                font-size: 13px;
                padding: 6px;
            }
            QPushButton {
                background: rgba(203,166,247,30);
                color: #cba6f7;
                border: 1px solid rgba(203,166,247,80);
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover { background: rgba(203,166,247,70); }
        """)

        layout = QVBoxLayout(self)

        # Main editing area
        self._editor = QTextEdit()
        self._editor.setPlainText(text)
        layout.addWidget(self._editor)

        # Bottom row: file loader on the left, OK/Cancel on the right
        btn_load = QPushButton("Load file…")
        btn_load.clicked.connect(self._load_file)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(btn_load)
        row.addStretch()
        row.addWidget(buttons)
        layout.addLayout(row)

    def get_text(self) -> str:
        """Return the current contents of the editor."""
        return self._editor.toPlainText()

    def _load_file(self):
        """Open a file-chooser and replace the editor content with the file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open script", "", "Text files (*.txt);;All files (*)"
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._editor.setPlainText(f.read())


# ── Microphone selection dialog ───────────────────────────────────────────────

class MicDialog(QDialog):
    """Diálogo para seleccionar el dispositivo de entrada de audio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar micrófono")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background: #1e1e2e; color: #cdd6f4; }
            QListWidget {
                background: #181825;
                color: #cdd6f4;
                border: 1px solid rgba(203,166,247,60);
                border-radius: 6px;
                font-size: 13px;
                padding: 4px;
            }
            QListWidget::item { padding: 6px 4px; }
            QListWidget::item:selected {
                background: rgba(203,166,247,60);
                color: #cdd6f4;
            }
            QLabel { color: #a6adc8; font-size: 12px; padding: 2px 0; }
            QPushButton {
                background: rgba(203,166,247,30);
                color: #cba6f7;
                border: 1px solid rgba(203,166,247,80);
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover { background: rgba(203,166,247,70); }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Elige el micrófono para el scroll por voz:"))

        self._list = QListWidget()
        layout.addWidget(self._list)

        layout.addWidget(QLabel(
            "Al confirmar se calibrará el ruido ambiente durante 2 segundos.\n"
            "Mantén silencio durante la calibración."
        ))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._devices: list[tuple[int, str]] = []  # (pyaudio_index, name)
        self._populate()

    def _populate(self):
        pa = VoiceListener._open_pa_quiet()
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                self._devices.append((i, info["name"]))
                self._list.addItem(info["name"])
        pa.terminate()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def get_device_index(self) -> int | None:
        """Índice pyaudio del dispositivo seleccionado, o None."""
        row = self._list.currentRow()
        if 0 <= row < len(self._devices):
            return self._devices[row][0]
        return None


# ── Voice activity detection thread ──────────────────────────────────────────

class VoiceListener(QThread):
    """Hilo que captura audio del micrófono y emite señales de actividad vocal.

    Fases:
      1. Calibración (~2 s): mide el ruido ambiente para fijar el umbral.
      2. Escucha: emite speaking_changed(True/False) con histéresis para evitar
         cambios erráticos por sonidos breves o silencios momentáneos.
    """

    speed_hint       = pyqtSignal(float)  # 0.0 = silencio, >0 = multiplicador de velocidad
    calibration_done = pyqtSignal()       # emitida al finalizar la calibración
    error_occurred   = pyqtSignal(str)    # emitida si el stream falla

    CHUNK         = 1024   # frames por buffer de audio
    CAL_SECS      = 2      # segundos de calibración de ruido ambiente
    NOISE_FACTOR  = 2.0    # umbral = ruido_base × NOISE_FACTOR
    SMOOTH_ALPHA  = 0.4    # suavizado exponencial de la energía (0=lento, 1=instantáneo)
    SILENCE_HOLD  = 6      # chunks de silencio antes de frenar (≈140 ms a 44100 Hz)

    def __init__(self, device_index: int | None, parent=None):
        super().__init__(parent)
        self._device_index = device_index
        self._running = False

    def run(self):
        try:
            self._run_loop()
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    @staticmethod
    def _open_pa_quiet() -> "pyaudio.PyAudio":
        """Abre PyAudio suprimiendo el spam de ALSA/JACK en stderr."""
        import os
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_err = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            pa = pyaudio.PyAudio()
        finally:
            os.dup2(old_err, 2)
            os.close(old_err)
        return pa

    def _run_loop(self):
        pa = self._open_pa_quiet()

        # Detectar la sample rate nativa del dispositivo
        if self._device_index is not None:
            info = pa.get_device_info_by_index(self._device_index)
        else:
            info = pa.get_default_input_device_info()
        rate = int(info.get("defaultSampleRate", 44100))

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            input_device_index=self._device_index,
            frames_per_buffer=self.CHUNK,
        )

        # ── Fase 1: calibración ──────────────────────────────────────────────
        cal_chunks = max(1, int(rate / self.CHUNK * self.CAL_SECS))
        energies: list[float] = []
        for _ in range(cal_chunks):
            if not self._running:
                break
            raw = stream.read(self.CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            energies.append(float(np.sqrt(np.mean(audio ** 2))))

        threshold = (np.mean(energies) if energies else 300.0) * self.NOISE_FACTOR
        self.calibration_done.emit()

        # ── Fase 2: escucha con velocidad proporcional a la energía ─────────
        smooth_rms    = 0.0
        silence_count = 0

        while self._running:
            raw = stream.read(self.CHUNK, exception_on_overflow=False)
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(audio ** 2)))

            # Suavizado exponencial para evitar saltos bruscos
            smooth_rms = self.SMOOTH_ALPHA * rms + (1 - self.SMOOTH_ALPHA) * smooth_rms

            if smooth_rms > threshold:
                silence_count = 0
                # Multiplicador: 1.5 en el umbral, hasta 3.0 para voz fuerte
                multiplier = min(3.0, (smooth_rms / threshold) * 1.5)
                self.speed_hint.emit(multiplier)
            else:
                silence_count += 1
                if silence_count >= self.SILENCE_HOLD:
                    self.speed_hint.emit(0.0)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    def start_listening(self):
        """Arranca el hilo de captura."""
        self._running = True
        self.start()

    def stop_listening(self):
        """Detiene el hilo y espera a que termine (máx. 2 s)."""
        self._running = False
        self.wait(2000)


# ── Main window ───────────────────────────────────────────────────────────────

class TeleprompterWindow(QMainWindow):
    """Frameless, always-on-top teleprompter window.

    Layout (top to bottom):
        ScrollDisplay  — expands to fill available height
        ControlBar     — fixed 54 px, hidden unless the pointer is inside

    Scrolling is driven by a 16 ms QTimer (~60 fps).  The timer advances the
    display every tick unless the user has paused or is hovering.
    """

    def __init__(self):
        super().__init__()

        self._paused   = False             # True when the user manually paused
        self._hovering = False             # True while the pointer is inside the window
        self._drag_pos: QPoint | None = None  # last recorded mouse position during drag

        # Voice-control state
        self._voice_listener: VoiceListener | None = None
        self._voice_speed = 0.0   # multiplicador de velocidad recibido del hilo de audio

        # Remove the title bar and keep the window on top of everything.
        # Qt.WindowType.Tool hides the window from the taskbar.
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  |
            Qt.WindowType.Tool
        )
        # Allow the background to be transparent (needed for BG fill from QPainter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Place the window at the top-centre of the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = 700, 260
        x = (screen.width() - w) // 2
        y = screen.top() + 10
        self.setGeometry(x, y, w, h)

        # Build the widget hierarchy
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self._display = ScrollDisplay()
        vbox.addWidget(self._display, stretch=1)   # takes all remaining height

        self._bar = ControlBar()
        self._bar.setVisible(False)                # hidden until hover
        vbox.addWidget(self._bar, stretch=0)       # fixed height

        # Connect control-bar signals to window slots
        self._bar.btn_play.clicked.connect(self._toggle_pause)
        self._bar.btn_reset.clicked.connect(self._reset)
        self._bar.btn_edit.clicked.connect(self._open_editor)
        self._bar.btn_mic.clicked.connect(self._toggle_voice)
        self._bar.btn_close.clicked.connect(self.close)
        # Speed slider value is read each tick; no signal handler needed
        self._bar.sld_font.valueChanged.connect(self._display.set_font_size)

        # Disable mic button if audio libraries are missing
        if not AUDIO_AVAILABLE:
            self._bar.btn_mic.setEnabled(False)
            self._bar.btn_mic.setToolTip("Instala pyaudio y numpy para usar el micrófono")

        # 16 ms timer drives the scroll animation (~62.5 fps)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Global keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Space),  self).activated.connect(self._toggle_pause)
        QShortcut(QKeySequence(Qt.Key.Key_R),       self).activated.connect(self._reset)
        QShortcut(QKeySequence(Qt.Key.Key_M),       self).activated.connect(self._toggle_voice)
        QShortcut(QKeySequence(Qt.Key.Key_Plus),    self).activated.connect(lambda: self._adj_speed(+1))
        QShortcut(QKeySequence(Qt.Key.Key_Equal),   self).activated.connect(lambda: self._adj_speed(+1))
        QShortcut(QKeySequence(Qt.Key.Key_Minus),   self).activated.connect(lambda: self._adj_speed(-1))
        QShortcut(QKeySequence("Ctrl+E"),            self).activated.connect(self._open_editor)
        QShortcut(QKeySequence(Qt.Key.Key_Escape),  self).activated.connect(self.close)

        # Mouse tracking must be enabled on all child widgets so that
        # enterEvent/leaveEvent on the window fire correctly even when the
        # pointer moves over a child without pressing a button.
        self.setMouseTracking(True)
        central.setMouseTracking(True)
        self._display.setMouseTracking(True)
        self._bar.setMouseTracking(True)

    # ── Animation tick ────────────────────────────────────────────────────────

    def _tick(self):
        """Called ~60 times per second by the QTimer.

        Advances the scroll by speed px unless paused or the pointer is
        hovering (hover also acts as a temporary pause).

        When voice control is active, scrolling is additionally gated on
        whether speech is currently detected.
        """
        if self._paused or self._hovering:
            return
        base_speed = self._bar.sld_speed.value() * 0.1
        if self._voice_listener is not None:
            if self._voice_speed < 0.05:
                return  # silencio — no avanzar
            speed = base_speed * self._voice_speed
        else:
            speed = base_speed
        self._display.advance(speed)

    # ── Control-bar slots ─────────────────────────────────────────────────────

    def _toggle_pause(self):
        """Toggle the manual pause state and update the button icon."""
        self._paused = not self._paused
        self._bar.btn_play.setText("▶" if self._paused else "⏸")

    def _reset(self):
        """Reset scroll position to the top of the script."""
        self._display.reset()

    def _adj_speed(self, delta: int):
        """Increment or decrement the speed slider by *delta* steps."""
        sld = self._bar.sld_speed
        sld.setValue(sld.value() + delta)

    def _open_editor(self):
        """Open the script editor dialog; apply changes on OK."""
        dlg = EditorDialog(self._display._text, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._display.set_text(dlg.get_text())

    # ── Voice control ─────────────────────────────────────────────────────────

    def _toggle_voice(self):
        """Activa o desactiva el scroll controlado por voz."""
        if not AUDIO_AVAILABLE:
            return

        if self._voice_listener is not None:
            # Detener el control por voz
            self._voice_listener.stop_listening()
            self._voice_listener = None
            self._voice_speed = 0.0
            self._bar.btn_mic.setText("🎤")
            self._bar.btn_mic.setToolTip("Activar scroll por voz  (M)")
            return

        # Mostrar diálogo de selección de micrófono
        dlg = MicDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        device_index = dlg.get_device_index()

        listener = VoiceListener(device_index, self)
        listener.speed_hint.connect(self._on_speed_hint)
        listener.calibration_done.connect(self._on_calibration_done)
        listener.error_occurred.connect(self._on_voice_error)
        listener.start_listening()

        self._voice_listener = listener
        self._bar.btn_mic.setText("⏳")
        self._bar.btn_mic.setToolTip("Calibrando ruido ambiente…")

    def _on_speed_hint(self, multiplier: float):
        """Recibe el multiplicador de velocidad del hilo de audio."""
        self._voice_speed = multiplier

    def _on_calibration_done(self):
        """Actualiza el botón cuando la calibración ha finalizado."""
        self._bar.btn_mic.setText("🔊")
        self._bar.btn_mic.setToolTip("Scroll por voz activo — clic para desactivar  (M)")

    def _on_voice_error(self, msg: str):
        """Resetea el estado del micrófono si el stream falla."""
        self._voice_listener = None
        self._voice_speed = 0.0
        self._bar.btn_mic.setText("🎤")
        self._bar.btn_mic.setToolTip(f"Error de micrófono: {msg}\nClic para reintentar  (M)")

    # ── Hover detection ───────────────────────────────────────────────────────

    def enterEvent(self, event):
        """Pointer entered the window: pause scrolling and show the control bar."""
        self._hovering = True
        self._bar.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Pointer left the window: resume scrolling and hide the control bar."""
        self._hovering = False
        self._bar.setVisible(False)
        super().leaveEvent(event)

    # ── Drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        """Record the click position to allow window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Move the window by the delta since the last mouse position."""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Clear the stored drag position when the button is released."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── Scroll wheel ──────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        """Adjust scroll speed with the mouse wheel (+1 up, -1 down)."""
        delta = 1 if event.angleDelta().y() > 0 else -1
        self._adj_speed(delta)
        super().wheelEvent(event)

    def closeEvent(self, event):
        """Stop the timer, stop the voice listener, and quit cleanly."""
        self._timer.stop()
        if self._voice_listener is not None:
            self._voice_listener.stop_listening()
        event.accept()
        QApplication.quit()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    app.setApplicationName("KDE Teleprompter")
    app.setOrganizationName("NotchPrompter")

    # Apply a dark QPalette for widgets that are not covered by stylesheets
    # (e.g. QDialog title bar chrome on some platforms).
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          BG)
    palette.setColor(QPalette.ColorRole.WindowText,      TEXT_CLR)
    palette.setColor(QPalette.ColorRole.Base,            QColor(24, 24, 37))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(30, 30, 46))
    palette.setColor(QPalette.ColorRole.Text,            TEXT_CLR)
    palette.setColor(QPalette.ColorRole.Button,          QColor(30, 30, 46))
    palette.setColor(QPalette.ColorRole.ButtonText,      ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight,       ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, BG)
    app.setPalette(palette)

    win = TeleprompterWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
