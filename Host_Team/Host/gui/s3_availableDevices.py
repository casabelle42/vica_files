from typing import Optional
from pathlib import Path
import os
import sys

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor, QLinearGradient, QRadialGradient, QPainter, QPainterPath, QPen,
    QFont, QPixmap, QBrush, QIcon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QWidget,
    QVBoxLayout,
)

# ── path bootstrap ────────────────────────────────────────────────────────────
current_file = os.path.abspath(__file__)
current_dir  = os.path.dirname(current_file)
host_dir     = os.path.dirname(current_dir)
host_team_dir = os.path.dirname(host_dir)
project_root = os.path.dirname(host_team_dir)

for path in [current_dir, host_dir, host_team_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from s4_query import MainWindow as QueryWindow

# ── constants ─────────────────────────────────────────────────────────────────
WIN_W, WIN_H  = 1100, 720
CARD_MARGIN   = 14
CARD_SPACING  = 12
BRAND_BG      = "#1D2BA1"
_CARD_DARK    = (0x13, 0x1A, 0x5C)
_CARD_LIGHT   = (0xB8, 0xDD, 0xFF)


def _app_icon() -> QIcon:
    logo = Path(__file__).parent / "assets" / "logo.png"
    return QIcon(str(logo)) if logo.exists() else QIcon()


# ── CardWidget ────────────────────────────────────────────────────────────────
class CardWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._layout.setSpacing(0)

    def content_layout(self) -> QVBoxLayout:
        return self._layout

    def paintEvent(self, event):
        p      = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = min(rect.width(), rect.height()) * 0.06

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0,   QColor(0x0D, 0x14, 0x4A, int(255 * 0.52)))
        grad.setColorAt(0.3, QColor(*_CARD_DARK,  int(255 * 0.46)))
        grad.setColorAt(1,   QColor(*_CARD_LIGHT, int(255 * 0.40)))
        p.fillPath(path, grad)

        p.save()
        p.setClipPath(path)
        thl = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        thl.setColorAt(0.0, QColor(255, 255, 255, 55))
        thl.setColorAt(0.3, QColor(255, 255, 255, 18))
        thl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        p.setBrush(thl); p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.restore()

        bgrad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        bgrad.setColorAt(0.0, QColor(*_CARD_LIGHT, 140))
        bgrad.setColorAt(0.5, QColor(*_CARD_LIGHT, 70))
        bgrad.setColorAt(1.0, QColor(*_CARD_LIGHT, 0))
        p.setPen(QPen(QBrush(bgrad), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# ── PillButton ────────────────────────────────────────────────────────────────
class PillButton(QPushButton):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._base    = QColor("#051140")
        self._hov     = QColor("#0D1E70")
        self._pressed = QColor("#030A28")
        self._text    = QColor("#CCCCCC")
        self._is_hov  = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFixedHeight(52)
        self.setMinimumWidth(160)

    def enterEvent(self, e): self._is_hov = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._is_hov = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, e):
        p      = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = min(200.0, rect.height() / 2.0)
        color  = self._pressed if self.isDown() else (self._hov if self._is_hov else self._base)
        path   = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, color)
        p.setPen(self._text)
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


# ── camera thumbnail ──────────────────────────────────────────────────────────
def create_camera_pixmap(size: int = 60) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p  = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    body = QRectF(size * 0.18, size * 0.28, size * 0.64, size * 0.30)
    bg   = QLinearGradient(body.topLeft(), body.bottomRight())
    bg.setColorAt(0.0, QColor(32, 36, 58))
    bg.setColorAt(0.5, QColor(56, 61, 92))
    bg.setColorAt(1.0, QColor(20, 24, 42))
    p.setBrush(QBrush(bg))
    p.setPen(QPen(QColor(15, 15, 25), 1.2))
    p.drawRoundedRect(body, size * 0.08, size * 0.08)

    lc  = QPointF(body.left() + body.height() * 0.65, body.center().y())
    lr  = body.height() * 0.28
    lgr = QRadialGradient(lc, body.height() * 0.35)
    lgr.setColorAt(0.0, QColor(210, 50, 70))
    lgr.setColorAt(0.4, QColor(110, 20, 35))
    lgr.setColorAt(1.0, QColor(15, 17, 28))
    p.setBrush(QBrush(lgr))
    p.setPen(QPen(QColor(12, 14, 26), 1))
    p.drawEllipse(lc, lr, lr)

    p.end()
    return px


# ── MainWindow ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        # Native OS title bar – logo + descriptive title
        self.setWindowTitle("Available Devices – Sentinel Nexus")
        self.setWindowIcon(_app_icon())
        self.resize(WIN_W, WIN_H)
        self.setMinimumSize(800, 520)

        self.devices: list[dict]           = []
        self.device_widgets: dict[str, dict] = {}
        self._on_discover_callback         = None
        self._on_query_callback            = None
        self._on_auto_resend_changed       = None
        self._query_window                 = None
        # Names of devices the user has checked as targets for the next query.
        self._selected_devices: set[str]   = set()
        # Per-device model selection (placeholders until Jetsons report models).
        self._selected_model_by_device: dict[str, str] = {}

        # ── root ──────────────────────────────────────────────────────────────
        root = QWidget()
        root.setStyleSheet(f"background-color: {BRAND_BG};")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        rl.setSpacing(CARD_SPACING)

        # ── main card: title + device list ───────────────────────────────────
        mid = CardWidget()
        mid.content_layout().setContentsMargins(14, 14, 14, 10)
        mid.content_layout().setSpacing(10)

        # Title row: "Available Devices" on the left, selection summary on the right.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)

        lbl = QLabel("Available Devices")
        tf  = QFont("Segoe UI", 14)
        tf.setWeight(QFont.Weight.DemiBold)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        lbl.setFont(tf)
        lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_row.addWidget(lbl)
        title_row.addStretch(1)

        self.selection_summary_lbl = QLabel("Target: All devices (broadcast)")
        sf = QFont("Segoe UI", 10)
        sf.setWeight(QFont.Weight.Medium)
        self.selection_summary_lbl.setFont(sf)
        self.selection_summary_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.78); background: transparent;"
        )
        title_row.addWidget(self.selection_summary_lbl)

        self.clear_selection_btn = QPushButton("Clear")
        self.clear_selection_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_selection_btn.setFixedHeight(24)
        self.clear_selection_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(184,221,255,0.18);"
            "  color: rgba(255,255,255,0.85);"
            "  border: 1px solid rgba(184,221,255,0.30);"
            "  border-radius: 6px;"
            "  padding: 0 10px;"
            "}"
            "QPushButton:hover  { background-color: rgba(184,221,255,0.30); }"
            "QPushButton:pressed{ background-color: rgba(184,221,255,0.10); }"
            "QPushButton:disabled{ color: rgba(255,255,255,0.30);"
            "  border-color: rgba(255,255,255,0.10); }"
        )
        self.clear_selection_btn.clicked.connect(self._clear_selection)
        self.clear_selection_btn.setEnabled(False)
        title_row.addWidget(self.clear_selection_btn)

        mid.content_layout().addLayout(title_row)

        # White device list panel sits directly below the label
        self.devices_panel = QWidget()
        self.devices_panel.setStyleSheet(
            "background-color: rgba(255,255,255,0.94);"
            "border-radius: 20px;"
        )
        shadow = QGraphicsDropShadowEffect(self.devices_panel)
        shadow.setBlurRadius(22); shadow.setColor(QColor(0, 0, 0, 50)); shadow.setOffset(0, 7)
        self.devices_panel.setGraphicsEffect(shadow)

        self._panel_layout = QVBoxLayout(self.devices_panel)
        self._panel_layout.setContentsMargins(36, 24, 36, 24)
        self._panel_layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(self.devices_panel)

        mid.content_layout().addWidget(scroll)
        rl.addWidget(mid, stretch=1)

        # ── bottom card: action buttons ───────────────────────────────────────
        bot = CardWidget()
        bot.setFixedHeight(86)

        bf = QFont("Segoe UI", 13)
        bf.setWeight(QFont.Weight.DemiBold)
        bf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)

        self.discover_btn = PillButton("Discover"); self.discover_btn.setFont(bf)
        self.query_btn    = PillButton("Query");    self.query_btn.setFont(bf)
        self.exit_btn     = PillButton("Exit");     self.exit_btn.setFont(bf)

        self.discover_btn.clicked.connect(self._on_discover_clicked)
        self.query_btn.clicked.connect(self._open_query_window)
        self.exit_btn.clicked.connect(self._exit_application)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(20)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.addWidget(self.discover_btn)
        btn_row.addWidget(self.query_btn)
        btn_row.addWidget(self.exit_btn)

        bot.content_layout().addStretch(1)
        bot.content_layout().addLayout(btn_row)
        bot.content_layout().addStretch(1)
        rl.addWidget(bot)

        self.setCentralWidget(root)

    # ── public API ────────────────────────────────────────────────────────────
    def set_discover_callback(self, callback):
        self._on_discover_callback = callback

    def set_query_callback(self, callback):
        """Set callback invoked when Query window sends text."""
        self._on_query_callback = callback

    def set_auto_resend_changed_callback(self, callback):
        """Set callback invoked when Query window auto-resend settings change."""
        self._on_auto_resend_changed = callback

    def update_devices(self, devices: list):
        self.devices = devices
        for wd in self.device_widgets.values():
            wd["row"].setParent(None); wd["row"].deleteLater()
        self.device_widgets.clear()
        while self._panel_layout.count() > 1:
            item = self._panel_layout.takeAt(1)
            if item.widget(): item.widget().deleteLater()
        for d in devices:
            self._create_device_row(d, self._panel_layout)
        # Drop selections that no longer exist in the new device list.
        live_names = {d.get("name") for d in devices if d.get("name")}
        self._selected_devices &= live_names
        self._refresh_selection_summary()
        self._panel_layout.invalidate()
        self.devices_panel.adjustSize()
        self.devices_panel.update()

    def selected_devices(self) -> list[str]:
        """Return the current set of devices the user has marked as targets."""
        return [name for name in self._selected_devices]

    def get_selected_model_for_device(self, device_name: str) -> str:
        """Return the selected model for a device (placeholder-safe)."""
        device_name = str(device_name or "").strip()
        if not device_name:
            return "default"
        return str(self._selected_model_by_device.get(device_name) or "default")

    def set_selected_devices(self, names) -> None:
        """Programmatically replace the current selection (e.g. from QueryWindow chips)."""
        names = set(names or [])
        self._selected_devices = {n for n in names if n in self.device_widgets}
        for name, wd in self.device_widgets.items():
            cb = wd.get("checkbox")
            if isinstance(cb, QCheckBox):
                cb.blockSignals(True)
                cb.setChecked(name in self._selected_devices)
                cb.blockSignals(False)
        self._refresh_selection_summary()

    def add_device(self, device: dict):
        self.devices.append(device)
        self._create_device_row(device, self._panel_layout)

    def remove_device(self, name: str):
        if name in self.device_widgets:
            self.device_widgets[name]["row"].deleteLater()
            del self.device_widgets[name]
            self.devices = [d for d in self.devices if d["name"] != name]

    def update_device_status(self, name: str, status: dict):
        if name not in self.device_widgets: return
        wd = self.device_widgets[name]
        if "status"     in status: wd["status_label"].setText(f"Status: {status['status']}")
        if "connection" in status: wd["connection_label"].setText(f"Connection: {status['connection']}")
        if "metadata"   in status: wd["metadata_label"].setText(f"Metadata: {status['metadata']}")
        # Optional: if device reports model list, update the per-device dropdown.
        if "model_combo" in wd:
            if "models" in status:
                self._update_device_models(name, status.get("models"), wd["model_combo"])
            elif "available_models" in status:
                self._update_device_models(name, status.get("available_models"), wd["model_combo"])
        for d in self.devices:
            if d["name"] == name: d.update(status); break

    # ── private ───────────────────────────────────────────────────────────────
    def _on_discover_clicked(self):
        if self._on_discover_callback:
            self._on_discover_callback()
        else:
            print("[AvailableDevices] Discover clicked – no callback registered")

    def _open_query_window(self):
        if self._query_window is None or not self._query_window.isVisible():
            self._query_window = QueryWindow()
            if self._on_query_callback and hasattr(self._query_window, "set_query_callback"):
                self._query_window.set_query_callback(self._on_query_callback)
            if self._on_auto_resend_changed and hasattr(self._query_window, "set_auto_resend_changed_callback"):
                self._query_window.set_auto_resend_changed_callback(self._on_auto_resend_changed)
            # Seed the new window with whatever the user has selected.
            if hasattr(self._query_window, "set_target_devices"):
                self._query_window.set_target_devices(self.selected_devices())
            # Provide a list of all known device names so the chip "Add target" picker
            # can show the full inventory, not just the currently checked ones.
            if hasattr(self._query_window, "set_available_devices"):
                self._query_window.set_available_devices(list(self.device_widgets.keys()))
            # When the user removes a chip in the QueryWindow, mirror it back to
            # the checkboxes here so both views stay coherent.
            if hasattr(self._query_window, "set_targets_changed_callback"):
                self._query_window.set_targets_changed_callback(self.set_selected_devices)
            self._query_window.show()
        else:
            if self._on_query_callback and hasattr(self._query_window, "set_query_callback"):
                self._query_window.set_query_callback(self._on_query_callback)
            if self._on_auto_resend_changed and hasattr(self._query_window, "set_auto_resend_changed_callback"):
                self._query_window.set_auto_resend_changed_callback(self._on_auto_resend_changed)
            if hasattr(self._query_window, "set_target_devices"):
                self._query_window.set_target_devices(self.selected_devices())
            if hasattr(self._query_window, "set_available_devices"):
                self._query_window.set_available_devices(list(self.device_widgets.keys()))
            if hasattr(self._query_window, "set_targets_changed_callback"):
                self._query_window.set_targets_changed_callback(self.set_selected_devices)
            self._query_window.raise_()
            self._query_window.activateWindow()

    def _exit_application(self):
        QApplication.instance().quit()

    def _update_device_models(self, device_name: str, models, combo: QComboBox) -> None:
        """Replace dropdown items for a device, keeping selection when possible."""
        models_list: list[str] = []
        if isinstance(models, list):
            models_list = [str(m) for m in models if str(m).strip()]
        if not models_list:
            # Placeholder: show ONLY default until Jetson reports real list.
            models_list = ["default"]

        current = self.get_selected_model_for_device(device_name)
        if current not in models_list:
            current = models_list[0]
            self._selected_model_by_device[str(device_name)] = current

        combo.blockSignals(True)
        combo.clear()
        combo.addItems(models_list)
        combo.setCurrentText(current if current in models_list else models_list[0])
        combo.blockSignals(False)

    def _create_device_row(self, device: dict, layout: QVBoxLayout):
        device_name = device.get("name", "Unknown")
        row = QWidget()
        row.setFixedHeight(92)
        row.setStyleSheet(
            "background-color: rgba(255,255,255,1.0);"
            "border: 1px solid rgba(19,26,92,0.10);"
            "border-radius: 14px;"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 14, 8)
        rl.setSpacing(14)

        # Selection checkbox: lets user pick which device(s) the next query targets.
        checkbox = QCheckBox()
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        checkbox.setToolTip("Include this device when sending the next query")
        checkbox.setChecked(device_name in self._selected_devices)
        checkbox.setStyleSheet(
            "QCheckBox { background: transparent; }"
            "QCheckBox::indicator {"
            "  width: 18px; height: 18px;"
            "  border: 1.5px solid #131A5C;"
            "  border-radius: 4px;"
            "  background: rgba(255,255,255,0.95);"
            "}"
            "QCheckBox::indicator:hover { border-color: #1D2BA1; }"
            "QCheckBox::indicator:checked {"
            "  background: #1D2BA1; border-color: #1D2BA1;"
            "  image: none;"
            "}"
        )
        checkbox.toggled.connect(
            lambda checked, name=device_name: self._on_device_checked(name, checked)
        )
        rl.addWidget(checkbox)

        thumb = QLabel()
        thumb.setFixedSize(72, 72)
        thumb.setStyleSheet("background: transparent; border: none;")
        thumb.setPixmap(create_camera_pixmap(72))
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(thumb)

        info = QVBoxLayout(); info.setSpacing(2)
        nlbl = QLabel(device_name)
        nf = QFont("Segoe UI", 11); nf.setWeight(QFont.Weight.DemiBold)
        nf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        nlbl.setFont(nf)
        nlbl.setStyleSheet("color: #1E1E1E; background: transparent;")
        info.addWidget(nlbl)

        lloc = QLabel(device.get("location", ""))
        lf = QFont("Segoe UI", 9)
        lloc.setFont(lf)
        lloc.setStyleSheet("color: #555B76; background: transparent;")
        lloc.setWordWrap(False)
        info.addWidget(lloc)
        rl.addLayout(info, stretch=3)

        sc = QVBoxLayout(); sc.setSpacing(2)
        sf = QFont("Segoe UI", 9)
        def _qlbl(text):
            l = QLabel(text); l.setFont(sf)
            l.setStyleSheet("color: #131A5C; background: transparent;")
            return l
        slbl = _qlbl(f"Status: {device.get('status','Unknown')}")
        clbl = _qlbl(f"Connection: {device.get('connection','Unknown')}")
        mlbl = _qlbl(f"Metadata: {device.get('metadata','N/A')}")
        sc.addWidget(slbl); sc.addWidget(clbl); sc.addWidget(mlbl)
        rl.addLayout(sc, stretch=2)

        # Per-device model selection dropdown (placeholder list until Jetson provides models).
        model_combo = QComboBox()
        model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        model_combo.setMinimumWidth(170)
        model_combo.setFont(QFont("Segoe UI", 9))
        model_combo.setToolTip("Select model for this device")
        model_combo.setStyleSheet(
            "QComboBox {"
            "  background-color: rgba(19,26,92,0.06);"
            "  border: 1px solid rgba(19,26,92,0.14);"
            "  border-radius: 10px;"
            "  padding: 6px 10px;"
            "  color: #131A5C;"
            "}"
            "QComboBox QAbstractItemView {"
            "  background-color: #FFFFFF;"
            "  color: #131A5C;"
            "  selection-background-color: rgba(29,43,161,0.18);"
            "}"
        )
        self._update_device_models(
            device_name,
            device.get("models") or device.get("available_models"),
            model_combo,
        )

        def _on_model_changed(text, name=device_name):  # noqa: ANN001
            self._selected_model_by_device[str(name)] = str(text or "default")

        model_combo.currentTextChanged.connect(_on_model_changed)
        rl.addWidget(model_combo, stretch=0)

        layout.addWidget(row)
        self.device_widgets[device_name] = {
            "row": row, "checkbox": checkbox,
            "name_label": nlbl, "location_label": lloc,
            "status_label": slbl, "connection_label": clbl, "metadata_label": mlbl,
            "model_combo": model_combo,
        }

    # ── selection helpers ─────────────────────────────────────────────────────
    def _on_device_checked(self, name: str, checked: bool) -> None:
        if checked:
            self._selected_devices.add(name)
        else:
            self._selected_devices.discard(name)
        self._refresh_selection_summary()
        # Keep the linked QueryWindow chips bar in sync if it's open.
        if self._query_window is not None and hasattr(self._query_window, "set_target_devices"):
            try:
                self._query_window.set_target_devices(self.selected_devices())
            except Exception as exc:
                print(f"[AvailableDevices] Failed to sync targets to query window: {exc!r}")

    def _clear_selection(self) -> None:
        if not self._selected_devices:
            return
        self._selected_devices.clear()
        for wd in self.device_widgets.values():
            cb = wd.get("checkbox")
            if isinstance(cb, QCheckBox):
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        self._refresh_selection_summary()
        if self._query_window is not None and hasattr(self._query_window, "set_target_devices"):
            try:
                self._query_window.set_target_devices([])
            except Exception:
                pass

    def _refresh_selection_summary(self) -> None:
        count = len(self._selected_devices)
        if count == 0:
            self.selection_summary_lbl.setText("Target: All devices (broadcast)")
        elif count == 1:
            only = next(iter(self._selected_devices))
            self.selection_summary_lbl.setText(f"Target: {only}")
        else:
            self.selection_summary_lbl.setText(f"Target: {count} devices selected")
        self.clear_selection_btn.setEnabled(count > 0)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
