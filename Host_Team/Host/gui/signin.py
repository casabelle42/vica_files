"""
signin.py  –  PyQt6 rewrite
---------------------------
Preserves all visual behaviour from the tkinter original:
  • Deep-blue #1D2BA1 background
  • Glassmorphism panel (QPainter gradient + rounded rect)
  • Faint background logo watermark
  • Pill-shaped input fields with placeholder behaviour
  • Styled Sign-in / Sign-up buttons with hover + press states
  • Splash overlay that fades the logo out, then reveals the app
  • Database auth via models.py / werkzeug (unchanged logic)
  • On success → launches s3_availableDevices MainWindow
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QRectF, QPointF,
    QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QBrush,
)
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QVBoxLayout, QWidget,
    QMessageBox,
)

# ── path bootstrap (same logic as original) ───────────────────────────────────
_script_dir   = Path(__file__).resolve().parent
_home         = Path.home()


def _find_host_root() -> Path:
    for d in [_script_dir] + list(_script_dir.parents)[:8]:
        if (d / "Host" / "gui").exists():
            return d
    for base in [_home / "Documents", _home, _script_dir]:
        candidate = base / "LAS-VICA-main" / "Host_Team"
        if (candidate / "Host" / "gui").exists():
            return candidate
    return _script_dir


def _find_app_data_dir() -> Path:
    for d in [_script_dir] + list(_script_dir.parents)[:8]:
        if (d / "models.py").exists():
            return d
    if (_home / "models.py").exists():
        return _home
    return _home


_host_root    = _find_host_root()
_app_data_dir = _find_app_data_dir()
for _p in [str(_host_root), str(_app_data_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _get_app_data_dir() -> tuple[Path, Path]:
    return _app_data_dir, _app_data_dir


# ── assets ────────────────────────────────────────────────────────────────────
def _assets_dir() -> Path:
    return _script_dir / "assets"


def _logo_path() -> Path:
    return _assets_dir() / "logo.png"


def _app_icon() -> QIcon:
    p = _logo_path()
    return QIcon(str(p)) if p.exists() else QIcon()


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return Duru Sans if available, else Segoe UI."""
    duru = _assets_dir() / "fonts" / "DuruSans-Regular.ttf"
    family = "Duru Sans" if duru.exists() else "Segoe UI"
    f = QFont(family, size)
    f.setWeight(weight)
    return f


# ── constants ─────────────────────────────────────────────────────────────────
WIN_W, WIN_H    = 600, 500
PANEL_W, PANEL_H = 400, 450
BRAND_BG        = QColor("#1D2BA1")
PILL_W, PILL_H  = 350, 50
PILL_R          = 25
BTN_W, BTN_H    = 158, 46
BTN_R           = 23.0
BTN_FILL        = QColor("#051140")
BTN_FILL_HOV    = QColor("#0D1E70")
BTN_FILL_PRE    = QColor("#030A28")
PILL_BG         = QColor("#A7ADC6")


# ══════════════════════════════════════════════════════════════════════════════
# Glass panel widget
# ══════════════════════════════════════════════════════════════════════════════
class GlassPanel(QWidget):
    """Renders the rounded glassmorphism card that contains the form."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(PANEL_W, PANEL_H)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, PANEL_W, PANEL_H)
        radius = 40.0

        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        # Blue gradient fill  #0D1B4A → #1D2BA1 → #3949AB
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0,  QColor(0x0D, 0x1B, 0x4A, int(255 * 0.92)))
        grad.setColorAt(0.5,  QColor(0x1D, 0x2B, 0xA1, int(255 * 0.88)))
        grad.setColorAt(1.0,  QColor(0x39, 0x49, 0xAB, int(255 * 0.85)))
        p.fillPath(path, grad)

        # Faint logo watermark drawn over gradient, clipped to panel
        logo = _logo_path()
        if logo.exists():
            lx_px = QPixmap(str(logo)).scaled(
                int(PANEL_W * 0.82), int(PANEL_H * 0.82),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.save()
            p.setClipPath(path)
            p.setOpacity(0.18)
            lx = (PANEL_W - lx_px.width()) // 2
            ly = (PANEL_H - lx_px.height()) // 2
            p.drawPixmap(lx, ly, lx_px)
            p.restore()

        # Inner shadow ring
        p.save()
        p.setClipPath(path)
        ring_pen = QPen(QColor(0x3D, 0x4A, 0xB5, 110), 8.0)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        inner = QRectF(4, 4, PANEL_W - 8, PANEL_H - 8)
        p.drawRoundedRect(inner, radius - 4, radius - 4)
        p.restore()

        # Top highlight
        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + PANEL_H * 0.3))
        thl.setColorAt(0.0, QColor(255, 255, 255, 55))
        thl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl)
        p.restore()

        # Border
        p.setPen(QPen(QColor(255, 255, 255, 55), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# ══════════════════════════════════════════════════════════════════════════════
# Pill input field
# ══════════════════════════════════════════════════════════════════════════════
class PillLineEdit(QWidget):
    """A rounded-pill styled QLineEdit with placeholder behaviour."""

    returnPressed = pyqtSignal()

    def __init__(self, placeholder: str, password: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(PILL_W, PILL_H)
        self._password = password

        self._edit = QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setFont(_font(14))
        self._edit.setStyleSheet(
            "background: transparent;"
            "border: none;"
            "color: white;"
            "selection-background-color: rgba(255,255,255,0.3);"
        )
        self._edit.setFixedSize(PILL_W - 56, PILL_H - 14)
        self._edit.move(28, 7)

        # Placeholder
        self._placeholder = placeholder
        self._has_placeholder = True
        self._edit.setText(placeholder)
        self._edit.setStyleSheet(
            "background: transparent; border: none;"
            "color: rgba(230,230,230,0.8);"
        )
        self._edit.focusInEvent  = self._on_focus_in   # type: ignore[method-assign]
        self._edit.focusOutEvent = self._on_focus_out  # type: ignore[method-assign]
        self._edit.returnPressed.connect(self.returnPressed)

    # ── public ────────────────────────────────────────────────────────────────
    def text(self) -> str:
        return "" if self._has_placeholder else self._edit.text()

    def setText(self, t: str) -> None:
        self._has_placeholder = False
        self._edit.setText(t)
        self._edit.setStyleSheet(
            "background: transparent; border: none; color: white;"
        )
        if self._password:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)

    def setFocus(self) -> None:  # type: ignore[override]
        self._edit.setFocus()

    # ── events ────────────────────────────────────────────────────────────────
    def _on_focus_in(self, event):
        if self._has_placeholder:
            self._has_placeholder = False
            self._edit.setText("")
            self._edit.setStyleSheet(
                "background: transparent; border: none; color: white;"
            )
            if self._password:
                self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        QLineEdit.focusInEvent(self._edit, event)

    def _on_focus_out(self, event):
        if not self._edit.text():
            self._has_placeholder = True
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._edit.setText(self._placeholder)
            self._edit.setStyleSheet(
                "background: transparent; border: none;"
                "color: rgba(230,230,230,0.8);"
            )
        QLineEdit.focusOutEvent(self._edit, event)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = QRectF(0, 0, PILL_W, PILL_H)
        path   = QPainterPath()
        path.addRoundedRect(rect, PILL_R, PILL_R)

        # Drop shadow
        p.save()
        sp = QPainterPath()
        sp.addRoundedRect(rect.translated(1, 3), PILL_R, PILL_R)
        sg = QRadialGradient(rect.center(), PILL_W * 0.7)
        sg.setColorAt(0.0, QColor(0, 0, 0, 0))
        sg.setColorAt(0.8, QColor(8, 12, 45, 90))
        sg.setColorAt(1.0, QColor(8, 12, 45, 60))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(sg)
        p.drawPath(sp)
        p.restore()

        # Fill
        p.fillPath(path, PILL_BG)

        # Subtle top highlight
        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + PILL_H * 0.4))
        thl.setColorAt(0.0, QColor(255, 255, 255, 38))
        thl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl)
        p.restore()

        # Border
        p.setPen(QPen(QColor(0x1D, 0x2B, 0xA1, 140), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# ══════════════════════════════════════════════════════════════════════════════
# Styled button
# ══════════════════════════════════════════════════════════════════════════════
class SignButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedSize(BTN_W, BTN_H)
        self.setFont(_font(14, QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._hov = False

    def enterEvent(self, e): self._hov = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hov = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect  = QRectF(0, 0, BTN_W, BTN_H)
        path  = QPainterPath()
        path.addRoundedRect(rect.adjusted(0, 0, 0, -3), BTN_R, BTN_R)
        color = BTN_FILL_PRE if self.isDown() else (BTN_FILL_HOV if self._hov else BTN_FILL)

        # Drop shadow
        p.save()
        sp = QPainterPath(); sp.addRoundedRect(rect.adjusted(0, 3, 0, 0), BTN_R, BTN_R)
        sg = QRadialGradient(rect.center(), BTN_W * 0.7)
        sg.setColorAt(0.0, QColor(0, 0, 0, 0)); sg.setColorAt(0.7, QColor(0, 0, 0, 80))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(sg); p.drawPath(sp)
        p.restore()

        p.fillPath(path, color)

        # Top highlight
        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + BTN_H * 0.45))
        thl.setColorAt(0.0, QColor(255, 255, 255, 60 if self._hov else 45))
        thl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl)
        p.restore()

        # Border
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)

        # Gradient text: #FFF3DD → #FFFFFF
        txt_grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        txt_grad.setColorAt(0.0, QColor("#FFF3DD"))
        txt_grad.setColorAt(1.0, QColor("#FFFFFF"))
        p.setPen(QPen(QBrush(txt_grad), 1))
        p.setFont(self.font())
        p.drawText(rect.adjusted(0, 0, 0, -3), Qt.AlignmentFlag.AlignCenter, self.text())


# ══════════════════════════════════════════════════════════════════════════════
# Splash overlay
# ══════════════════════════════════════════════════════════════════════════════
class SplashOverlay(QWidget):
    """
    Full-window opaque overlay: logo fades out, then the overlay itself fades
    out to reveal the sign-in form.

    Design notes
    ────────────
    • We do NOT put a QGraphicsOpacityEffect on `self` — that causes the
      "paint device can only be painted by one painter at a time" / "Unbalanced
      save/restore" console spam because Qt's effect compositor tries to create
      a second QPainter over the widget while paintEvent already owns one.
    • Instead we store _logo_alpha and _bg_alpha as plain floats and read them
      directly in paintEvent, then call update() from a QTimer to drive the
      animation manually.  This is entirely single-painter and error-free.
    • The two phases overlap: the background starts fading at 70 % through the
      logo fade, eliminating the blank blue gap between phases.
    """

    finished = pyqtSignal()

    # Animation timing (ms)
    _LOGO_DURATION = 600
    _BG_DURATION   = 550
    _OVERLAP_PCT   = 0.70   # bg fade starts when logo is this far through
    _TICK_MS       = 16     # ~60 fps

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setGeometry(parent.rect())
        self.raise_()

        self._logo_alpha: float = 1.0
        self._bg_alpha:   float = 1.0
        self._done_flag:  bool  = False

        # Pre-scale logo pixmap once
        self._logo_px: QPixmap | None = None
        logo = _logo_path()
        if logo.exists():
            self._logo_px = QPixmap(str(logo)).scaled(
                int(WIN_W * 0.52), int(WIN_H * 0.52),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self._timer = QTimer(self)
        self._timer.setInterval(self._TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._elapsed: float = 0.0   # ms since animation start
        self._started: bool  = False

    # ── public ────────────────────────────────────────────────────────────────
    def start(self, start_delay_ms: int = 900) -> None:
        QTimer.singleShot(start_delay_ms, self._begin)

    # ── private ───────────────────────────────────────────────────────────────
    def _begin(self) -> None:
        self._elapsed = 0.0
        self._started = True
        self._timer.start()

    def _tick(self) -> None:
        self._elapsed += self._TICK_MS

        # Logo alpha: 1 → 0 over _LOGO_DURATION
        logo_t = min(1.0, self._elapsed / self._LOGO_DURATION)
        self._logo_alpha = 1.0 - _ease(logo_t)

        # Background alpha: starts fading once logo is _OVERLAP_PCT done
        bg_start_ms = self._LOGO_DURATION * self._OVERLAP_PCT
        bg_t = max(0.0, min(1.0, (self._elapsed - bg_start_ms) / self._BG_DURATION))
        self._bg_alpha = 1.0 - _ease(bg_t)

        self.update()   # triggers paintEvent

        # Done when bg has fully faded
        if self._bg_alpha <= 0.0 and not self._done_flag:
            self._timer.stop()
            self._done_flag = True
            self.hide()
            self.finished.emit()

    def paintEvent(self, _event):  # noqa: N802
        if self._bg_alpha <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background — solid brand blue, faded by _bg_alpha
        bg = QColor(BRAND_BG)
        bg.setAlphaF(self._bg_alpha)
        p.fillRect(self.rect(), bg)

        # Logo — drawn on top, with its own alpha
        if self._logo_px and self._logo_alpha > 0.0:
            p.setOpacity(self._logo_alpha * self._bg_alpha)
            lx = (self.width()  - self._logo_px.width())  // 2
            ly = (self.height() - self._logo_px.height()) // 2
            p.drawPixmap(lx, ly, self._logo_px)

    def mousePressEvent(self, _event):
        self._timer.stop()
        self._done_flag = True
        self.hide()
        self.finished.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.mousePressEvent(None)  # type: ignore[arg-type]


def _ease(t: float) -> float:
    """Smooth-step easing (same feel as InOutSine)."""
    return t * t * (3.0 - 2.0 * t)


# ══════════════════════════════════════════════════════════════════════════════
# Section label (e.g. "Email", "Password")
# ══════════════════════════════════════════════════════════════════════════════
def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_font(13))
    lbl.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent;")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


# ══════════════════════════════════════════════════════════════════════════════
# SignInWindow
# ══════════════════════════════════════════════════════════════════════════════
class SignInWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sentinel Nexus")
        self.setWindowIcon(_app_icon())
        self.setFixedSize(WIN_W, WIN_H)

        # Root
        root = QWidget()
        root.setStyleSheet(f"background-color: #{BRAND_BG.name()[1:]};")
        self.setCentralWidget(root)

        # Glass panel – centred
        # (The panel's own paintEvent draws the faint logo watermark inside it;
        #  no second logo label is needed at the window level.)
        self._panel = GlassPanel(root)
        px_off = (WIN_W - PANEL_W) // 2
        py_off = (WIN_H - PANEL_H) // 2
        self._panel.move(px_off, py_off)

        # Form widget overlaid on the panel
        form = QWidget(self._panel)
        form.setGeometry(0, 0, PANEL_W, PANEL_H)
        form.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        vbox = QVBoxLayout(form)
        vbox.setContentsMargins(24, 28, 24, 24)
        vbox.setSpacing(0)

        # Title
        title = QLabel("Sentinel Nexus")
        title.setFont(_font(20, QFont.Weight.Light))
        title.setStyleSheet("color: #FFFFFF; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(title)

        vbox.addStretch(2)

        # Email
        vbox.addWidget(_section_label("Email"))
        vbox.addSpacing(6)
        self._email = PillLineEdit("Enter email", password=False)
        vbox.addWidget(self._email, alignment=Qt.AlignmentFlag.AlignHCenter)

        vbox.addStretch(1)

        # Password
        vbox.addWidget(_section_label("Password"))
        vbox.addSpacing(6)
        self._password = PillLineEdit("Enter password", password=True)
        vbox.addWidget(self._password, alignment=Qt.AlignmentFlag.AlignHCenter)

        vbox.addStretch(3)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._btn_signin = SignButton("Sign in")
        self._btn_signup = SignButton("Sign up")
        self._btn_signin.clicked.connect(self._on_signin)
        self._btn_signup.clicked.connect(self._on_signup)
        btn_row.addWidget(self._btn_signin)
        btn_row.addWidget(self._btn_signup)
        vbox.addLayout(btn_row)

        vbox.addSpacing(20)

        # Enter key flow
        self._email._edit.returnPressed.connect(lambda: self._password.setFocus())
        self._password._edit.returnPressed.connect(self._on_signin)

        # Splash overlay (must be created last so it sits on top)
        self._splash = SplashOverlay(root)
        self._splash.start(start_delay_ms=900)

    # ── auth handlers ─────────────────────────────────────────────────────────
    def _on_signin(self) -> None:
        email    = self._email.text().strip()
        password = self._password.text()

        if not email or not password:
            QMessageBox.warning(self, "Sign in", "Please enter your email and password.")
            return

        try:
            from auth_client import login, save_session  # type: ignore

            auth_result = login(email=email, password=password)
            token = auth_result.get("token", "")
            user = auth_result.get("user", {}) or {}
            if not token:
                QMessageBox.critical(self, "Sign in Failed", "No token returned by Auth API.")
                return

            save_session(token=token, user=user)
            print(f"[SignIn] '{email}' authenticated via Auth API")

            # Hide first so Qt always has >=1 visible window during the transition.
            self.hide()
            _launch_main(email, on_ready=self.close)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Authentication error: {e}")

    def _on_signup(self) -> None:
        try:
            from signup_standalone import SignUpWindow                  # type: ignore
            win = SignUpWindow(parent=None)
            win.show()
            self._signup_win = win   # keep reference
        except ImportError:
            QMessageBox.critical(
                self, "Sign up unavailable",
                "signup_standalone.py must be in the same folder as signin.py.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open sign-up window: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Launch helpers
# ══════════════════════════════════════════════════════════════════════════════
def _launch_main(username: str = "", on_ready=None) -> None:
    """
    Open the Available Devices window after successful sign-in.

    Two critical details:
      1. The window is stored on the QApplication instance (_main_window) so
         Python's garbage collector cannot destroy it when this function returns.
         Without this the window appears for a single frame then vanishes.
      2. on_ready (typically signin_window.close) is called via a zero-delay
         QTimer *after* the event loop has processed the show() call, so Qt
         never sees a moment with zero visible windows (which would quit the app
         on some platforms / Qt builds).
    """
    # Preferred path: launch s1_start_app.py (handles MQTT wiring + callbacks).
    # This runs in a separate process to avoid conflicting Qt app lifecycle.
    s1_path = _script_dir / "s1_start_app.py"
    if s1_path.exists():
        try:
            env = os.environ.copy()
            if username:
                env["VICA_AUTH_USER_EMAIL"] = username
            subprocess.Popen([sys.executable, str(s1_path)], env=env)
            if on_ready:
                QTimer.singleShot(0, on_ready)
            return
        except Exception as e:
            print(f"[SignIn] Warning: could not launch s1_start_app.py: {e}")

    # Fallback: open available devices window directly in-process.
    from s3_availableDevices import MainWindow                          # type: ignore
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.setWindowTitle(
        f"Available Devices – {username}" if username else "Available Devices – Sentinel Nexus"
    )
    app._main_window = win                                              # type: ignore[attr-defined]
    win.show()
    if on_ready:
        QTimer.singleShot(0, on_ready)


@dataclass
class SplashConfig:
    """Kept for API compatibility with s1_start_app.py / s2_signin.py."""
    enabled: bool             = True
    start_delay_ms: int       = 900
    duration_ms: int          = 1200
    steps: int                = 30
    logo_opacity: float       = 0.9
    logo_max_width_ratio: float  = 0.55
    logo_max_height_ratio: float = 0.55


def create_signin_window(config: Optional[SplashConfig] = None) -> SignInWindow:
    """Factory used by s2_signin.py.  Returns the window (caller must call show())."""
    win = SignInWindow()
    if config and not config.enabled:
        if hasattr(win, "_splash"):
            win._splash.hide()
    return win


# ── standalone entry ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w   = create_signin_window()
    w.show()
    sys.exit(app.exec())
