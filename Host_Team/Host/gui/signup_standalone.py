"""
signup_standalone.py  –  PyQt6 rewrite
---------------------------------------
Matches the glass-panel aesthetic of signin.py.
Exports SignUpWindow (QMainWindow) and the original
create_signup_window() shim for backward compatibility.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QBrush,
)
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QVBoxLayout, QWidget,
    QMessageBox, QSizePolicy,
)

# ── re-use helpers from signin ────────────────────────────────────────────────
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

try:
    from signin import (                                                # type: ignore
        _font, _app_icon, _get_app_data_dir, _assets_dir,
        GlassPanel, PillLineEdit, SignButton, _section_label,
        PANEL_W, PANEL_H, BTN_W, BTN_H, BTN_R,
        BTN_FILL, BTN_FILL_HOV, BTN_FILL_PRE, BRAND_BG, PILL_W, PILL_H,
    )
    _signin_available = True
except ImportError:
    _signin_available = False
    # Minimal fallbacks so the module can still import
    def _font(size, weight=None):
        f = QFont("Segoe UI", size)
        return f
    def _app_icon(): return QIcon()
    def _get_app_data_dir(): return Path.home(), Path.home()
    BRAND_BG = QColor("#1D2BA1")
    PANEL_W, PANEL_H = 520, 640
    PILL_W, PILL_H   = 420, 52
    BTN_W, BTN_H     = 178, 48
    BTN_R            = 24.0
    BTN_FILL         = QColor("#051140")
    BTN_FILL_HOV     = QColor("#0D1E70")
    BTN_FILL_PRE     = QColor("#030A28")


# ── password policy (unchanged from original) ─────────────────────────────────
PASSWORD_MIN_LEN      = 12
PASSWORD_MAX_LEN      = 128
PASSWORD_MIN_UPPERCASE = 1
PASSWORD_MIN_LOWERCASE = 1
PASSWORD_MIN_DIGITS    = 1
PASSWORD_MIN_SPECIAL   = 1
PASSWORD_SPECIAL_ALLOWED = set(r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~""")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(email: str) -> tuple[bool, str]:
    email = email.strip()
    if not email:
        return False, "Please enter your email."
    if not EMAIL_PATTERN.match(email):
        return False, "Email must be in the format: name@example.com"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < PASSWORD_MIN_LEN:
        return False, f"Password must be at least {PASSWORD_MIN_LEN} characters."
    if len(password) > PASSWORD_MAX_LEN:
        return False, f"Password must be no more than {PASSWORD_MAX_LEN} characters."
    if sum(1 for c in password if c.isupper()) < PASSWORD_MIN_UPPERCASE:
        return False, f"Password must contain at least {PASSWORD_MIN_UPPERCASE} uppercase letter(s)."
    if sum(1 for c in password if c.islower()) < PASSWORD_MIN_LOWERCASE:
        return False, f"Password must contain at least {PASSWORD_MIN_LOWERCASE} lowercase letter(s)."
    if sum(1 for c in password if c.isdigit()) < PASSWORD_MIN_DIGITS:
        return False, f"Password must contain at least {PASSWORD_MIN_DIGITS} digit(s)."
    special = [c for c in password if not c.isalnum()]
    if len(special) < PASSWORD_MIN_SPECIAL:
        return False, f"Password must contain at least {PASSWORD_MIN_SPECIAL} special character(s)."
    disallowed = [c for c in special if c not in PASSWORD_SPECIAL_ALLOWED]
    if disallowed:
        return False, ("Password contains disallowed characters. Use only letters, digits, and: "
                       + "".join(sorted(PASSWORD_SPECIAL_ALLOWED)))
    return True, ""


def get_password_rule_results(password: str) -> list[tuple[bool, str]]:
    special = [c for c in password if not c.isalnum()]
    return [
        (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN,
         f"{PASSWORD_MIN_LEN}–{PASSWORD_MAX_LEN} characters"),
        (sum(1 for c in password if c.isupper()) >= PASSWORD_MIN_UPPERCASE,
         f"At least {PASSWORD_MIN_UPPERCASE} uppercase letter(s)"),
        (sum(1 for c in password if c.islower()) >= PASSWORD_MIN_LOWERCASE,
         f"At least {PASSWORD_MIN_LOWERCASE} lowercase letter(s)"),
        (sum(1 for c in password if c.isdigit()) >= PASSWORD_MIN_DIGITS,
         f"At least {PASSWORD_MIN_DIGITS} digit(s)"),
        (len(special) >= PASSWORD_MIN_SPECIAL,
         f"At least {PASSWORD_MIN_SPECIAL} special character(s)"),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Wider glass panel for sign-up (has more fields + rule list)
# ══════════════════════════════════════════════════════════════════════════════
SU_PANEL_W = 520
SU_PANEL_H = 640
SU_WIN_W   = 640
SU_WIN_H   = 760


class SignUpGlassPanel(QWidget):
    """Wider/taller glass panel variant for the sign-up form."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SU_PANEL_W, SU_PANEL_H)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r      = QRectF(0, 0, SU_PANEL_W, SU_PANEL_H)
        radius = 44.0
        path   = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        # Background logo watermark
        logo_p = _script_dir / "assets" / "logo.png"
        if logo_p.exists():
            px = QPixmap(str(logo_p)).scaled(
                int(SU_PANEL_W * 0.86), int(SU_PANEL_H * 0.86),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.save()
            p.setClipPath(path)
            p.setOpacity(0.20)
            p.drawPixmap((SU_PANEL_W - px.width()) // 2, (SU_PANEL_H - px.height()) // 2, px)
            p.setOpacity(1.0)
            p.restore()

        # Blue gradient
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QColor(0x0D, 0x1B, 0x4A, int(255 * 0.92)))
        grad.setColorAt(0.5, QColor(0x1D, 0x2B, 0xA1, int(255 * 0.88)))
        grad.setColorAt(1.0, QColor(0x39, 0x49, 0xAB, int(255 * 0.85)))
        p.fillPath(path, grad)

        # Inner shadow ring
        p.save()
        p.setClipPath(path)
        p.setPen(QPen(QColor(0x3D, 0x4A, 0xB5, 110), 8.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(4, 4, SU_PANEL_W - 8, SU_PANEL_H - 8), radius - 4, radius - 4)
        p.restore()

        # Top highlight
        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + SU_PANEL_H * 0.28))
        thl.setColorAt(0.0, QColor(255, 255, 255, 52)); thl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl); p.restore()

        # Border
        p.setPen(QPen(QColor(255, 255, 255, 55), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)


# ── wider pill for sign-up form ───────────────────────────────────────────────
SU_PILL_W = 420
SU_PILL_H = 50
SU_PILL_R = 25


class WiderPillLineEdit(QWidget):
    """Same as PillLineEdit but 420 px wide for the sign-up form."""

    returnPressed = pyqtSignal()

    def __init__(self, placeholder: str, password: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SU_PILL_W, SU_PILL_H)
        self._password = password

        self._edit = QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setFont(_font(14))
        self._has_placeholder = True
        self._placeholder = placeholder
        self._edit.setText(placeholder)
        self._edit.setStyleSheet(
            "background: transparent; border: none;"
            "color: rgba(230,230,230,0.8);"
        )
        self._edit.setFixedSize(SU_PILL_W - 56, SU_PILL_H - 14)
        self._edit.move(28, 7)
        self._edit.focusInEvent  = self._on_focus_in   # type: ignore[method-assign]
        self._edit.focusOutEvent = self._on_focus_out  # type: ignore[method-assign]
        self._edit.returnPressed.connect(self.returnPressed)
        self._edit.textChanged.connect(self._on_text_changed)

    textChanged = pyqtSignal(str)

    def _on_text_changed(self, t: str):
        if not self._has_placeholder:
            self.textChanged.emit(t)

    def text(self) -> str:
        return "" if self._has_placeholder else self._edit.text()

    def setFocus(self) -> None:  # type: ignore[override]
        self._edit.setFocus()

    def _on_focus_in(self, event):
        if self._has_placeholder:
            self._has_placeholder = False
            self._edit.setText("")
            self._edit.setStyleSheet("background: transparent; border: none; color: white;")
            if self._password:
                self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        QLineEdit.focusInEvent(self._edit, event)

    def _on_focus_out(self, event):
        if not self._edit.text():
            self._has_placeholder = True
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._edit.setText(self._placeholder)
            self._edit.setStyleSheet(
                "background: transparent; border: none; color: rgba(230,230,230,0.8);")
        QLineEdit.focusOutEvent(self._edit, event)

    def paintEvent(self, _event):  # noqa: N802
        p    = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, SU_PILL_W, SU_PILL_H)
        path = QPainterPath(); path.addRoundedRect(rect, SU_PILL_R, SU_PILL_R)

        p.save()
        sp = QPainterPath(); sp.addRoundedRect(rect.translated(1, 3), SU_PILL_R, SU_PILL_R)
        sg = QRadialGradient(rect.center(), SU_PILL_W * 0.7)
        sg.setColorAt(0.0, QColor(0,0,0,0)); sg.setColorAt(0.8, QColor(8,12,45,90))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(sg); p.drawPath(sp); p.restore()

        p.fillPath(path, QColor("#A7ADC6"))

        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + SU_PILL_H * 0.4))
        thl.setColorAt(0.0, QColor(255,255,255,38)); thl.setColorAt(1.0, QColor(255,255,255,0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl); p.restore()

        p.setPen(QPen(QColor(0x1D,0x2B,0xA1,140), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)


# ── back/create button (same style as SignButton but wider) ───────────────────
class SignUpButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedSize(178, 48)
        self.setFont(_font(14, QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._hov = False

    def enterEvent(self, e): self._hov = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hov = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h  = self.width(), self.height()
        rect  = QRectF(0, 0, w, h)
        path  = QPainterPath(); path.addRoundedRect(rect.adjusted(0,0,0,-3), 24.0, 24.0)
        color = BTN_FILL_PRE if self.isDown() else (BTN_FILL_HOV if self._hov else BTN_FILL)

        p.save()
        sp = QPainterPath(); sp.addRoundedRect(rect.adjusted(0,3,0,0), 24.0, 24.0)
        sg = QRadialGradient(rect.center(), w*0.7)
        sg.setColorAt(0.0, QColor(0,0,0,0)); sg.setColorAt(0.7, QColor(0,0,0,80))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(sg); p.drawPath(sp); p.restore()

        p.fillPath(path, color)
        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(rect.topLeft(), QPointF(0, h*0.45))
        thl.setColorAt(0.0, QColor(255,255,255,60 if self._hov else 45))
        thl.setColorAt(1.0, QColor(255,255,255,0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.fillPath(path, thl); p.restore()

        p.setPen(QPen(QColor(255,255,255,50), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)

        txt_grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        txt_grad.setColorAt(0.0, QColor("#FFF3DD")); txt_grad.setColorAt(1.0, QColor("#FFFFFF"))
        p.setPen(QPen(QBrush(txt_grad), 1))
        p.setFont(self.font())
        p.drawText(rect.adjusted(0,0,0,-3), Qt.AlignmentFlag.AlignCenter, self.text())


# ══════════════════════════════════════════════════════════════════════════════
# SignUpWindow
# ══════════════════════════════════════════════════════════════════════════════
class SignUpWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign Up – Sentinel Nexus")
        self.setWindowIcon(_app_icon())
        self.setFixedSize(SU_WIN_W, SU_WIN_H)

        root = QWidget()
        root.setStyleSheet(f"background-color: #{BRAND_BG.name()[1:]};")
        self.setCentralWidget(root)

        # Glass panel – centred
        panel = SignUpGlassPanel(root)
        panel.move((SU_WIN_W - SU_PANEL_W) // 2, (SU_WIN_H - SU_PANEL_H) // 2)

        form = QWidget(panel)
        form.setGeometry(0, 0, SU_PANEL_W, SU_PANEL_H)
        form.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        vbox = QVBoxLayout(form)
        vbox.setContentsMargins(30, 22, 30, 22)
        vbox.setSpacing(0)

        # Title
        title = QLabel("Sign up")
        title.setFont(_font(20, QFont.Weight.Light))
        title.setStyleSheet("color: #FFFFFF; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(title)
        vbox.addSpacing(14)

        # Email
        vbox.addWidget(_section_label("Email"))
        vbox.addSpacing(6)
        self._email = WiderPillLineEdit("Enter email")
        vbox.addWidget(self._email, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addSpacing(14)

        # Password
        vbox.addWidget(_section_label("Password"))
        vbox.addSpacing(6)
        self._password = WiderPillLineEdit("Enter password", password=True)
        vbox.addWidget(self._password, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._password.textChanged.connect(self._update_rules)
        vbox.addSpacing(10)

        # Password rules
        rules_widget = QWidget()
        rules_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(8, 0, 8, 0)
        rules_layout.setSpacing(2)
        rule_font = _font(11)
        self._rule_labels: list[QLabel] = []
        for _, desc in get_password_rule_results(""):
            lbl = QLabel(f"✗  {desc}")
            lbl.setFont(rule_font)
            lbl.setStyleSheet("color: rgba(156,162,188,0.9); background: transparent;")
            rules_layout.addWidget(lbl)
            self._rule_labels.append(lbl)
        vbox.addWidget(rules_widget)
        vbox.addSpacing(12)

        # Confirm password
        vbox.addWidget(_section_label("Confirm password"))
        vbox.addSpacing(6)
        self._confirm = WiderPillLineEdit("Re-enter password", password=True)
        vbox.addWidget(self._confirm, alignment=Qt.AlignmentFlag.AlignHCenter)
        vbox.addStretch(1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._btn_create = SignUpButton("Create")
        self._btn_back   = SignUpButton("Back")
        self._btn_create.clicked.connect(self._on_create)
        self._btn_back.clicked.connect(self.close)
        btn_row.addWidget(self._btn_create)
        btn_row.addWidget(self._btn_back)
        vbox.addLayout(btn_row)
        vbox.addSpacing(10)

        # Initial rule state
        self._update_rules("")

    # ── slots ─────────────────────────────────────────────────────────────────
    def _update_rules(self, text: str = "") -> None:
        pw = self._password.text()
        for lbl, (met, desc) in zip(self._rule_labels, get_password_rule_results(pw)):
            lbl.setText(("✓" if met else "✗") + f"  {desc}")
            lbl.setStyleSheet(
                f"color: {'#7ED07E' if met else 'rgba(156,162,188,0.9)'}; background: transparent;"
            )

    def _on_create(self) -> None:
        email    = self._email.text().strip()
        password = self._password.text()
        confirm  = self._confirm.text()

        valid_email, email_err = validate_email(email)
        if not valid_email:
            QMessageBox.critical(self, "Invalid email", email_err); return
        if not password:
            QMessageBox.critical(self, "Error", "Please enter a password."); return
        valid, err = validate_password(password)
        if not valid:
            QMessageBox.critical(self, "Password requirements", err); return
        if password != confirm:
            QMessageBox.critical(self, "Error",
                                  "Passwords do not match. Re-enter your password in Confirm password.")
            return

        try:
            from auth_client import signup  # type: ignore

            signup(email=email, password=password)
            QMessageBox.information(self, "Success", "Account created. You can sign in now.")
            self.close()
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Could not create account: {ex}")


# ── backward-compat shim ──────────────────────────────────────────────────────
def create_signup_window(parent=None) -> SignUpWindow:
    """Matches the original API so s2_signin / other callers work unchanged."""
    win = SignUpWindow(parent=None)
    win.show()
    return win


# ── standalone entry ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w   = SignUpWindow()
    w.show()
    sys.exit(app.exec())
