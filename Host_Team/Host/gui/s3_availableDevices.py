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
        self._query_window                 = None

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

        # Title label inside the card, above the white panel
        lbl = QLabel("Available Devices")
        tf  = QFont("Segoe UI", 14)
        tf.setWeight(QFont.Weight.DemiBold)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        lbl.setFont(tf)
        lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        mid.content_layout().addWidget(lbl)

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
        self._panel_layout.invalidate()
        self.devices_panel.adjustSize()
        self.devices_panel.update()

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
            self._query_window.show()
        else:
            if self._on_query_callback and hasattr(self._query_window, "set_query_callback"):
                self._query_window.set_query_callback(self._on_query_callback)
            self._query_window.raise_()
            self._query_window.activateWindow()

    def _exit_application(self):
        QApplication.instance().quit()

    def _create_device_row(self, device: dict, layout: QVBoxLayout):
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

        thumb = QLabel()
        thumb.setFixedSize(72, 72)
        thumb.setStyleSheet("background: transparent; border: none;")
        thumb.setPixmap(create_camera_pixmap(72))
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(thumb)

        info = QVBoxLayout(); info.setSpacing(2)
        nlbl = QLabel(device.get("name", "Unknown"))
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

        layout.addWidget(row)
        self.device_widgets[device["name"]] = {
            "row": row, "name_label": nlbl, "location_label": lloc,
            "status_label": slbl, "connection_label": clbl, "metadata_label": mlbl,
        }


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
