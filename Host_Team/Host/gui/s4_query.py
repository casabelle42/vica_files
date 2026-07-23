from typing import Callable, Optional, List, Dict, Tuple
from pathlib import Path
import os
import sys
import math
import time
import base64

from PyQt6.QtCore import Qt, QPoint, QRectF, QPointF, QTimer, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient, QFont, QPixmap, QBrush, QIcon, QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
    QVBoxLayout,
)

# ── constants ─────────────────────────────────────────────────────────────────
WIN_W, WIN_H  = 1100, 880
BRAND_BG      = "#1D2BA1"
# Vertical gap between major blocks inside the Query card (title, targets, chips, …).
_QUERY_SECTION_GAP = 6
_CARD_DARK    = (0x13, 0x1A, 0x5C)
_CARD_LIGHT   = (0xB8, 0xDD, 0xFF)


def _app_icon() -> QIcon:
    logo = Path(__file__).parent / "assets" / "logo.png"
    return QIcon(str(logo)) if logo.exists() else QIcon()


# ── CardWidget ────────────────────────────────────────────────────────────────
class CardWidget(QWidget):
    def __init__(self, width: int = 0, height: int = 0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if width and height:
            self.setFixedSize(width, height)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 18, 24, 18)
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

        # Glassmorphism gradient – same palette as s3
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0,   QColor(0x0D, 0x14, 0x4A, int(255 * 0.52)))
        grad.setColorAt(0.3, QColor(*_CARD_DARK,  int(255 * 0.46)))
        grad.setColorAt(1,   QColor(*_CARD_LIGHT, int(255 * 0.40)))
        p.fillPath(path, grad)

        # Subtle top highlight
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

        # Gradient border
        bgrad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        bgrad.setColorAt(0.0, QColor(*_CARD_LIGHT, 140))
        bgrad.setColorAt(0.5, QColor(*_CARD_LIGHT, 70))
        bgrad.setColorAt(1.0, QColor(*_CARD_LIGHT, 0))
        p.setPen(QPen(QBrush(bgrad), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# ── GlassButton ───────────────────────────────────────────────────────────────
class GlassButton(QPushButton):
    def __init__(self, text: str, bg_color: str = "#E0E0E0",
                 text_color: str = "#1E1E1E", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._bg   = QColor(bg_color)
        self._text = QColor(text_color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setMinimumHeight(38)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = QRectF(self.rect()).adjusted(0, 0, 0, -3)
        radius = 7.0

        # Drop shadow
        p.save()
        sr = QRectF(rect).translated(0, 3)
        sp = QPainterPath(); sp.addRoundedRect(sr, radius, radius)
        sg = QRadialGradient(sr.center(), max(sr.width(), sr.height()) * 0.7)
        sg.setColorAt(0.0, QColor(0, 0, 0, 0))
        sg.setColorAt(0.6, QColor(0, 0, 0, 60))
        sg.setColorAt(1.0, QColor(0, 0, 0, 100))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(sg)
        p.drawPath(sp)
        p.restore()

        path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, self._bg)

        p.setPen(self._text); p.setFont(self.font())
        p.drawText(QRectF(rect).adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignCenter, self.text())


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
        p.setPen(self._text); p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


# Placeholder entry for "no video file — use the live camera feed".
_LIVE_CAMERA_LABEL = "◉  Live camera (no video file)"

_VIDEO_COMBO_STYLE = (
    "QComboBox {"
    "  background-color: rgba(255,255,255,0.12);"
    "  border: 1px solid rgba(184,221,255,0.35);"
    "  border-radius: 8px;"
    "  padding: 5px 10px;"
    "  color: #FFFFFF;"
    "  min-height: 24px;"
    "}"
    "QComboBox:disabled { color: rgba(255,255,255,0.40); }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView {"
    "  background-color: #FFFFFF;"
    "  color: #131A5C;"
    "  selection-background-color: rgba(29,43,161,0.18);"
    "}"
)


_CHIP_COMBO_STYLE = (
    "QComboBox {"
    "  background-color: rgba(19,26,92,0.35);"
    "  border: 1px solid rgba(184,221,255,0.40);"
    "  border-radius: 8px;"
    "  padding: 2px 6px;"
    "  color: #FFFFFF;"
    "  min-height: 22px;"
    "}"
    "QComboBox::drop-down { border: none; width: 14px; }"
    "QComboBox QAbstractItemView {"
    "  background-color: #FFFFFF;"
    "  color: #131A5C;"
    "  selection-background-color: rgba(29,43,161,0.18);"
    "}"
)


# ── _TargetChip ───────────────────────────────────────────────────────────────
class _TargetChip(QFrame):
    """
    Target pill: device name, per-edge model dropdown, and remove control.
    """

    removed = pyqtSignal(str)
    model_changed = pyqtSignal(str, str)

    def __init__(
        self,
        name: str,
        *,
        model: str = "default",
        available_models: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self.setObjectName("TargetChip")
        self.setStyleSheet(
            "QFrame#TargetChip {"
            "  background-color: rgba(184,221,255,0.22);"
            "  border: 1px solid rgba(184,221,255,0.45);"
            "  border-radius: 12px;"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 4, 3)
        layout.setSpacing(6)

        lbl = QLabel(name)
        f = QFont("Segoe UI", 9)
        f.setWeight(QFont.Weight.Medium)
        lbl.setFont(f)
        lbl.setStyleSheet("color: #FFFFFF; background: transparent; border: none;")
        layout.addWidget(lbl)

        models_list = [str(m) for m in (available_models or []) if str(m).strip()]
        if not models_list:
            models_list = ["default"]
        current = str(model or "default").strip() or "default"
        if current not in models_list:
            models_list = [current] + models_list

        self.model_combo = QComboBox()
        self.model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_combo.setFont(QFont("Segoe UI", 8))
        self.model_combo.setMinimumWidth(120)
        self.model_combo.setMaximumWidth(200)
        self.model_combo.setToolTip(f"Model for {name}")
        self.model_combo.setStyleSheet(_CHIP_COMBO_STYLE)
        self.model_combo.addItems(models_list)
        self.model_combo.blockSignals(True)
        self.model_combo.setCurrentText(current if current in models_list else models_list[0])
        self.model_combo.blockSignals(False)
        self.model_combo.currentTextChanged.connect(
            lambda text, n=name: self.model_changed.emit(n, str(text or "default"))
        )
        layout.addWidget(self.model_combo)

        close_btn = QPushButton("×")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(
            "QPushButton {"
            "  color: rgba(255,255,255,0.85);"
            "  background: transparent; border: none;"
            "  font-size: 14px; font-weight: bold;"
            "}"
            "QPushButton:hover { color: #FFFFFF; }"
        )
        close_btn.setToolTip(f"Remove '{name}' from targets")
        close_btn.clicked.connect(lambda: self.removed.emit(self._name))
        layout.addWidget(close_btn)

    def set_model(self, model: str) -> None:
        model = str(model or "default").strip() or "default"
        if self.model_combo.currentText() == model:
            return
        self.model_combo.blockSignals(True)
        if self.model_combo.findText(model) < 0:
            self.model_combo.insertItem(0, model)
        self.model_combo.setCurrentText(model)
        self.model_combo.blockSignals(False)

    def set_available_models(self, models: Optional[List[str]], *, selected: Optional[str] = None) -> None:
        models_list = [str(m) for m in (models or []) if str(m).strip()]
        if not models_list:
            models_list = ["default"]
        current = str(selected or self.model_combo.currentText() or "default").strip() or "default"
        if current not in models_list:
            models_list = [current] + models_list
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models_list)
        self.model_combo.setCurrentText(current if current in models_list else models_list[0])
        self.model_combo.blockSignals(False)


# ── _HistoryLineEdit ──────────────────────────────────────────────────────────
class _HistoryLineEdit(QLineEdit):
    """
    QLineEdit with shell-style ↑ / ↓ history navigation. The owner provides a
    callable returning the current history list (oldest → newest).
    """

    def __init__(self, history_provider: Callable[[], List[str]],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._history_provider = history_provider
        self._cursor: Optional[int] = None
        self._draft: str = ""

    def reset_history_cursor(self) -> None:
        self._cursor = None
        self._draft = ""

    def keyPressEvent(self, event):
        key = event.key()
        history = self._history_provider() or []

        if key == Qt.Key.Key_Up and history:
            if self._cursor is None:
                self._draft = self.text()
                self._cursor = len(history) - 1
            else:
                self._cursor = max(0, self._cursor - 1)
            self.setText(history[self._cursor])
            return

        if key == Qt.Key.Key_Down and self._cursor is not None:
            if self._cursor >= len(history) - 1:
                self._cursor = None
                self.setText(self._draft)
            else:
                self._cursor += 1
                self.setText(history[self._cursor])
            return

        # Any other input invalidates the cursor — typing branches off.
        if key not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt,
                       Qt.Key.Key_Meta, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._cursor = None
        super().keyPressEvent(event)


# ── _ZoomScrollArea ───────────────────────────────────────────────────────────
class _ZoomScrollArea(QScrollArea):
    """Scroll area: mouse wheel zooms, hold M1 and drag to pan."""

    def __init__(self, viewer: "_ImageViewerDialog", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._viewer = viewer
        self._panning = False
        self._pan_anchor = QPoint()
        self._pan_h_start = 0
        self._pan_v_start = 0
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        self.viewport().installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.viewport():
            et = event.type()
            if et == QEvent.Type.MouseButtonPress:
                self.mousePressEvent(event)
                return True
            if et == QEvent.Type.MouseMove:
                self.mouseMoveEvent(event)
                return True
            if et == QEvent.Type.MouseButtonRelease:
                self.mouseReleaseEvent(event)
                return True
            if et == QEvent.Type.Wheel:
                self.wheelEvent(event)
                return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        steps = delta / 120.0
        factor = 1.25 ** steps
        pos = event.position().toPoint()
        self._viewer._adjust_zoom(factor, pos)
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._pan_anchor = event.position().toPoint()
            self._pan_h_start = self.horizontalScrollBar().value()
            self._pan_v_start = self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position().toPoint() - self._pan_anchor
            self.horizontalScrollBar().setValue(self._pan_h_start - delta.x())
            self.verticalScrollBar().setValue(self._pan_v_start - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ── _ImageViewerDialog ────────────────────────────────────────────────────────
class _ImageViewerDialog(QWidget):
    """Zoomable image viewer — upscales low-res frames for closer inspection."""

    _MIN_ZOOM = 0.25
    _MAX_ZOOM = 16.0

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._source = pixmap if isinstance(pixmap, QPixmap) else QPixmap()
        self._zoom = 1.0

        self.setWindowTitle("Image preview")
        self.setWindowIcon(_app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(f"background-color: {BRAND_BG};")

        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        max_w = int(avail.width() * 0.92) if avail else 1280
        max_h = int(avail.height() * 0.88) if avail else 900
        self.resize(max(640, max_w // 2), max(480, max_h // 2))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zf = QFont("Segoe UI", 10)
        zf.setWeight(QFont.Weight.Medium)

        _tool_style = (
            "QPushButton {"
            "  background-color: rgba(184,221,255,0.15);"
            "  color: rgba(255,255,255,0.90);"
            "  border: 1px solid rgba(184,221,255,0.30);"
            "  border-radius: 8px;"
            "  padding: 4px 10px;"
            "}"
            "QPushButton:hover  { background-color: rgba(184,221,255,0.28); }"
            "QPushButton:pressed{ background-color: rgba(184,221,255,0.10); }"
        )

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFont(zf)
        zoom_out_btn.setFixedSize(36, 32)
        zoom_out_btn.setStyleSheet(_tool_style)
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(lambda: self._adjust_zoom(1 / 1.25))
        zoom_row.addWidget(zoom_out_btn)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFont(zf)
        self._zoom_lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setMinimumWidth(64)
        zoom_row.addWidget(self._zoom_lbl)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFont(zf)
        zoom_in_btn.setFixedSize(36, 32)
        zoom_in_btn.setStyleSheet(_tool_style)
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(lambda: self._adjust_zoom(1.25))
        zoom_row.addWidget(zoom_in_btn)

        fit_btn = QPushButton("Fit")
        fit_btn.setFont(zf)
        fit_btn.setStyleSheet(_tool_style)
        fit_btn.setToolTip("Fit image to window")
        fit_btn.clicked.connect(self._zoom_fit)
        zoom_row.addWidget(fit_btn)

        reset_btn = QPushButton("100%")
        reset_btn.setFont(zf)
        reset_btn.setStyleSheet(_tool_style)
        reset_btn.setToolTip("Actual pixels (1:1)")
        reset_btn.clicked.connect(lambda: self._set_zoom(1.0))
        zoom_row.addWidget(reset_btn)

        hint = QLabel("Scroll wheel to zoom · hold M1 and drag to pan")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setStyleSheet("color: rgba(255,255,255,0.55); background: transparent;")
        zoom_row.addStretch(1)
        zoom_row.addWidget(hint)
        layout.addLayout(zoom_row)

        self._scroll = _ZoomScrollArea(self)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: rgba(255,255,255,0.05); border-radius: 8px;")

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Let the scroll area receive drag/wheel events over the pixmap.
        self._img_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._scroll.setWidget(self._img_lbl)
        layout.addWidget(self._scroll, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = GlassButton("Close", bg_color="#D8DEF0", text_color="#131A5C")
        cf = QFont("Segoe UI", 11); cf.setWeight(QFont.Weight.Medium)
        close_btn.setFont(cf)
        close_btn.setFixedWidth(110)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        QTimer.singleShot(0, self._apply_initial_zoom)

    def _apply_initial_zoom(self) -> None:
        self._set_zoom(self._default_zoom())

    def _default_zoom(self) -> float:
        if self._source.isNull():
            return 1.0
        iw = max(1, self._source.width())
        ih = max(1, self._source.height())
        vp = self._scroll.viewport()
        avail_w = max(320, vp.width() - 8)
        avail_h = max(240, vp.height() - 8)
        fit = min(avail_w / iw, avail_h / ih)
        # Low-res thumbnails benefit from starting above 1:1 when they are small.
        if max(iw, ih) <= 512:
            return min(self._MAX_ZOOM, max(2.0, fit))
        return min(self._MAX_ZOOM, max(1.0, fit))

    def _zoom_fit(self) -> None:
        if self._source.isNull():
            return
        iw = max(1, self._source.width())
        ih = max(1, self._source.height())
        vp = self._scroll.viewport()
        avail_w = max(1, vp.width() - 8)
        avail_h = max(1, vp.height() - 8)
        self._set_zoom(min(avail_w / iw, avail_h / ih))

    def _set_zoom(self, zoom: float) -> None:
        self._zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, zoom))
        self._refresh_image()
        self._zoom_lbl.setText(f"{int(round(self._zoom * 100))}%")

    def _adjust_zoom(self, factor: float, anchor: Optional[QPoint] = None) -> None:
        if self._source.isNull() or factor <= 0:
            return
        old_zoom = self._zoom
        new_zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        vp = self._scroll.viewport()
        if anchor is None:
            anchor = QPoint(vp.width() // 2, vp.height() // 2)

        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        content_x = (hbar.value() + anchor.x()) / old_zoom
        content_y = (vbar.value() + anchor.y()) / old_zoom

        self._zoom = new_zoom
        self._refresh_image()
        self._zoom_lbl.setText(f"{int(round(self._zoom * 100))}%")

        hbar.setValue(max(0, int(content_x * new_zoom - anchor.x())))
        vbar.setValue(max(0, int(content_y * new_zoom - anchor.y())))

    def _refresh_image(self) -> None:
        if self._source.isNull():
            self._img_lbl.clear()
            self._img_lbl.setFixedSize(1, 1)
            return
        w = max(1, int(self._source.width() * self._zoom))
        h = max(1, int(self._source.height() * self._zoom))
        scaled = self._source.scaled(
            w, h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_lbl.setPixmap(scaled)
        self._img_lbl.setFixedSize(scaled.size())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._adjust_zoom(1.25)
            return
        if event.key() == Qt.Key.Key_Minus:
            self._adjust_zoom(1 / 1.25)
            return
        if event.key() == Qt.Key.Key_0:
            self._set_zoom(1.0)
            return
        super().keyPressEvent(event)


# ── ScaledImageLabel ──────────────────────────────────────────────────────────
class _ScaledImageLabel(QLabel):
    """
    A QLabel that always scales its stored pixmap to fill the label's current
    size while strictly preserving the original aspect ratio.  Re-scales on
    every resizeEvent so it works correctly when the parent window is maximised
    or resized by the user.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._source: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._refresh()

    def source_pixmap(self) -> Optional[QPixmap]:
        return self._source

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._source and not self._source.isNull():
            scaled = self._source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            super().setPixmap(scaled)


# ── ResponsePopoutWindow ──────────────────────────────────────────────────────
class ResponsePopoutWindow(QWidget):
    """
    A standalone pop-out window that displays query responses in full detail
    and lets the user navigate through every response received so far.
    """

    def __init__(self, images: list, index: int = 0,
                 parent: Optional[QWidget] = None) -> None:
        """
        Parameters
        ----------
        images:
            Snapshot list of dicts, each with keys ``"metadata"`` (dict) and
            ``"pixmap"`` (QPixmap | None).  Must have at least one entry.
        index:
            Which entry to show first (0-based).
        """
        super().__init__(parent, Qt.WindowType.Window)
        self._images = images
        self._index  = max(0, min(index, len(images) - 1))

        self.setWindowIcon(_app_icon())
        self.resize(1080, 720)
        self.setMinimumSize(780, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(f"background-color: {BRAND_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Main content row ──────────────────────────────────────────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # Image card (always present; hidden when no pixmap)
        img_card = CardWidget()
        img_card_layout = img_card.content_layout()
        img_card_layout.setSpacing(12)
        img_card_layout.addWidget(_section_title("Image"))

        self._img_display = _ScaledImageLabel()
        self._img_display.setStyleSheet(
            "background: rgba(255,255,255,0.08); border-radius: 10px;"
        )
        self._img_display.mousePressEvent = self._on_image_clicked
        img_card_layout.addWidget(self._img_display, stretch=1)
        content_row.addWidget(img_card, stretch=1)

        # Detail card
        detail_card = CardWidget()
        detail_layout = detail_card.content_layout()
        detail_layout.setSpacing(10)
        detail_layout.addWidget(_section_title("Details"))
        detail_layout.addSpacing(4)

        mf = QFont("Segoe UI", 11)
        self._detail_labels: dict[str, QLabel] = {}
        for label_text, field in [
            ("Query",           "query"),
            ("Edge Device",     "edge_device"),
            ("Image",           "image"),
            ("Confidence Rate", "confidence_rate"),
            ("Time Processed",  "time_processed"),
        ]:
            lbl = QLabel()
            lbl.setFont(mf)
            lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
            lbl.setWordWrap(True)
            lbl.setProperty("label_prefix", label_text)
            detail_layout.addWidget(lbl)
            self._detail_labels[field] = lbl

        detail_layout.addSpacing(14)

        resp_title = QLabel("Response:")
        rtf = QFont("Segoe UI", 11)
        rtf.setWeight(QFont.Weight.DemiBold)
        resp_title.setFont(rtf)
        resp_title.setStyleSheet("color: rgba(255,255,255,0.90); background: transparent;")
        detail_layout.addWidget(resp_title)
        detail_layout.addSpacing(4)

        self._response_box = QTextEdit()
        self._response_box.setReadOnly(True)
        self._response_box.setFont(QFont("Segoe UI", 12))
        self._response_box.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._response_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._response_box.setStyleSheet(
            "color: rgba(255,255,255,0.92);"
            "background-color: rgba(255,255,255,0.14);"
            "border: none; border-radius: 10px; padding: 12px;"
        )
        detail_layout.addWidget(self._response_box, stretch=1)

        content_row.addWidget(detail_card, stretch=1)
        root.addLayout(content_row, stretch=1)

        # ── Bottom navigation bar ─────────────────────────────────────────────
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        _nav_style = (
            "QPushButton {"
            "  background-color: rgba(184,221,255,0.15);"
            "  color: rgba(255,255,255,0.85);"
            "  border: 1px solid rgba(184,221,255,0.30);"
            "  border-radius: 8px;"
            "  font-size: 16px;"
            "}"
            "QPushButton:hover  { background-color: rgba(184,221,255,0.28); }"
            "QPushButton:pressed{ background-color: rgba(184,221,255,0.10); }"
            "QPushButton:disabled{ color: rgba(255,255,255,0.25);"
            "  border-color: rgba(255,255,255,0.10); }"
        )

        self._prev_btn = QPushButton("←")
        self._prev_btn.setFixedSize(40, 36)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet(_nav_style)
        self._prev_btn.clicked.connect(lambda: self._navigate(self._index - 1))
        nav_row.addWidget(self._prev_btn)

        self._counter_lbl = QLabel()
        cf = QFont("Segoe UI", 11)
        cf.setWeight(QFont.Weight.Medium)
        self._counter_lbl.setFont(cf)
        self._counter_lbl.setStyleSheet("color: rgba(255,255,255,0.80); background: transparent;")
        self._counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._counter_lbl.setMinimumWidth(60)
        nav_row.addWidget(self._counter_lbl)

        self._next_btn = QPushButton("→")
        self._next_btn.setFixedSize(40, 36)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(_nav_style)
        self._next_btn.clicked.connect(lambda: self._navigate(self._index + 1))
        nav_row.addWidget(self._next_btn)

        nav_row.addStretch(1)

        close_btn = GlassButton("Close", bg_color="#D8DEF0", text_color="#131A5C")
        cbf = QFont("Segoe UI", 11)
        cbf.setWeight(QFont.Weight.Medium)
        close_btn.setFont(cbf)
        close_btn.setFixedWidth(110)
        close_btn.clicked.connect(self.close)
        nav_row.addWidget(close_btn)

        root.addLayout(nav_row)

        # Populate initial view
        self._navigate(self._index)

    def _on_image_clicked(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pixmap = self._img_display.source_pixmap()
        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            return
        viewer = _ImageViewerDialog(pixmap, parent=self)
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    # ── navigation ────────────────────────────────────────────────────────────
    def _navigate(self, index: int) -> None:
        self._index = max(0, min(index, len(self._images) - 1))
        item     = self._images[self._index]
        metadata = item.get("metadata") or {}
        pixmap   = item.get("pixmap")

        # Window title
        query_text = str(metadata.get("query") or "").strip()
        snippet = (query_text or "Query")[:80]
        self.setWindowTitle(f"Response – {snippet}")

        # Image
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self._img_display.set_source_pixmap(pixmap)
            self._img_display.setCursor(Qt.CursorShape.PointingHandCursor)
            self._img_display.setToolTip("Click to open zoomable viewer")
        else:
            self._img_display.set_source_pixmap(QPixmap())
            self._img_display.unsetCursor()
            self._img_display.setToolTip("")

        # Detail labels
        for field, lbl in self._detail_labels.items():
            prefix = lbl.property("label_prefix") or field
            lbl.setText(f"{prefix}:  {metadata.get(field, '—')}")

        # Response text
        self._response_box.setPlainText(metadata.get("response", ""))

        # Counter + button states
        total = len(self._images)
        self._counter_lbl.setText(f"{self._index + 1} / {total}")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < total - 1)


# ── camera thumbnail ──────────────────────────────────────────────────────────
def create_camera_pixmap(size: int = 60) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p  = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    body = QRectF(size * 0.18, size * 0.28, size * 0.64, size * 0.30)
    bg   = QLinearGradient(body.topLeft(), body.bottomRight())
    bg.setColorAt(0.0, QColor(32, 36, 58)); bg.setColorAt(0.5, QColor(56, 61, 92)); bg.setColorAt(1.0, QColor(20, 24, 42))
    p.setBrush(QBrush(bg)); p.setPen(QPen(QColor(15, 15, 25), 1.2))
    p.drawRoundedRect(body, size * 0.08, size * 0.08)
    lc  = QPointF(body.left() + body.height() * 0.65, body.center().y())
    lgr = QRadialGradient(lc, body.height() * 0.35)
    lgr.setColorAt(0.0, QColor(210, 50, 70)); lgr.setColorAt(0.4, QColor(110, 20, 35)); lgr.setColorAt(1.0, QColor(15, 17, 28))
    p.setBrush(QBrush(lgr)); p.setPen(QPen(QColor(12, 14, 26), 1))
    p.drawEllipse(lc, body.height() * 0.28, body.height() * 0.28)
    p.end()
    return px


# ── section title helper ──────────────────────────────────────────────────────
def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    f   = QFont("Segoe UI", 14)
    f.setWeight(QFont.Weight.DemiBold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
    lbl.setFont(f)
    lbl.setStyleSheet("color: #FFFFFF; background: transparent;")
    return lbl


# ── MainWindow ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    # Signals used to safely deliver data from any thread to the main thread
    _image_ready    = pyqtSignal(str, dict)
    _metadata_ready = pyqtSignal(dict)
    _clear_ready    = pyqtSignal()
    _videos_ready   = pyqtSignal(dict, dict, dict)

    def __init__(self) -> None:
        super().__init__()
        self._image_ready.connect(self._add_image_on_main_thread)
        self._metadata_ready.connect(self._update_metadata_on_main_thread)
        self._clear_ready.connect(self._clear_on_main_thread)
        self._videos_ready.connect(self._apply_video_catalog_on_main_thread)

        # Native OS title bar – logo + descriptive title
        self.setWindowTitle("Query – Sentinel Nexus")
        self.setWindowIcon(_app_icon())
        self.resize(WIN_W, WIN_H)
        self.setMinimumSize(880, 660)

        self._on_query_callback = None
        self._on_auto_resend_changed: Optional[Callable[[bool, int, int], None]] = None
        self._auto_resend_enabled: bool = False
        self._popout_windows: List[ResponsePopoutWindow] = []
        self._auto_separate: bool = False
        self._current_metadata: dict = {}
        self._current_pixmap: Optional[QPixmap] = None
        self._last_auto_popout_key: str = ""  # dedup guard — prevents double pop-out

        # ── multi-device targeting state ──────────────────────────────────────
        self._target_devices: list[str] = []
        self._available_devices: list[str] = []
        self._on_targets_changed_callback: Optional[Callable[[List[str]], None]] = None
        self._on_models_changed_callback: Optional[Callable[[str, str], None]] = None
        self._target_chip_widgets: dict[str, _TargetChip] = {}
        self._model_by_device: dict[str, str] = {}
        self._available_models_by_device: dict[str, list[str]] = {}

        # ── video source state ────────────────────────────────────────────────
        # Populated from device_status packets: what each edge has in its video
        # directory, where that directory is, and whether the edge created it.
        self._videos_by_device: dict[str, list[str]] = {}
        self._video_dir_by_device: dict[str, str] = {}
        self._video_dir_created: dict[str, bool] = {}
        # Devices we have already announced a "directory created" prompt for, so
        # the message is not re-shown on every 1.5s status packet.
        self._announced_video_dirs: set[str] = set()
        self._selected_video: str = ""
        self._on_videos_refresh_callback: Optional[Callable[[], None]] = None

        # ── QoL state ─────────────────────────────────────────────────────────
        # #11 Query history (oldest → newest).
        self._query_history: list[str] = []
        self._last_sent_query: str = ""
        self._max_history = 50
        # #15 Animated pending spinner.
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(120)
        self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0
        self._pending_message_base = "Pending response..."
        self._pending_active = False
        self._session_deadline_ts: Optional[float] = None
        self._session_deadline_timer = QTimer(self)
        self._session_deadline_timer.setInterval(250)
        self._session_deadline_timer.timeout.connect(self._tick_session_deadline)
        # #16 Query timeout warning (VLM on Jetson often needs >20s).
        try:
            self._query_timeout_ms = max(20_000, int(os.getenv("VICA_QUERY_TIMEOUT_MS", "120000")))
        except (TypeError, ValueError):
            self._query_timeout_ms = 120_000
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_query_timeout)
        # #17 Last query_id (set by the host after send via set_last_query_id).
        self._last_query_id: str = ""

        # ── root ──────────────────────────────────────────────────────────────
        root = QWidget()
        root.setStyleSheet(f"background-color: {BRAND_BG};")
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # ════════════════════════════════════════════════════════════════
        # LEFT COLUMN
        # ════════════════════════════════════════════════════════════════
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.setContentsMargins(0, 0, 0, 0)

        # ── Query card ────────────────────────────────────────────────────────
        query_card = CardWidget()
        # Do not use setFixedHeight here — it plus a bottom stretch collapses spacing to 0.
        ql = query_card.content_layout()
        ql.setSpacing(0)
        ql.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        ql.addWidget(_section_title("Query"))
        ql.addSpacing(_QUERY_SECTION_GAP)

        # Targets row: header + Add picker + chips strip.
        targets_header_row = QHBoxLayout()
        targets_header_row.setSpacing(8)
        targets_lbl = QLabel("Target devices:")
        thf = QFont("Segoe UI", 10); thf.setWeight(QFont.Weight.Medium)
        targets_lbl.setFont(thf)
        targets_lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
        targets_header_row.addWidget(targets_lbl)

        self.add_target_btn = QToolButton()
        self.add_target_btn.setText("+ Add")
        self.add_target_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_target_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.add_target_btn.setStyleSheet(
            "QToolButton {"
            "  background-color: rgba(184,221,255,0.18);"
            "  color: rgba(255,255,255,0.90);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 6px;"
            "  padding: 2px 10px;"
            "}"
            "QToolButton:hover { background-color: rgba(184,221,255,0.30); }"
            "QToolButton::menu-indicator { image: none; }"
        )
        self.add_target_btn.setToolTip("Add an edge device to this query's target list")
        self.add_target_menu = QMenu(self)
        self.add_target_btn.setMenu(self.add_target_menu)
        self.add_target_menu.aboutToShow.connect(self._rebuild_add_target_menu)
        targets_header_row.addWidget(self.add_target_btn)
        targets_header_row.addStretch(1)

        self.targets_summary_lbl = QLabel("Broadcast — all devices")
        tslf = QFont("Segoe UI", 9)
        self.targets_summary_lbl.setFont(tslf)
        self.targets_summary_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.65); background: transparent;"
        )
        targets_header_row.addWidget(self.targets_summary_lbl)
        ql.addLayout(targets_header_row)
        ql.addSpacing(_QUERY_SECTION_GAP)

        # Scrollable chip strip (so 10+ chips don't blow up the layout).
        self._chips_container = QWidget()
        self._chips_container.setStyleSheet("background: transparent;")
        self._chips_layout = QHBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 2, 0, 2)
        self._chips_layout.setSpacing(6)
        self._chips_layout.addStretch(1)
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setFixedHeight(44)
        chips_scroll.setStyleSheet("background: transparent;")
        chips_scroll.setWidget(self._chips_container)
        ql.addWidget(chips_scroll)
        ql.addSpacing(_QUERY_SECTION_GAP)

        # ── Video source region ───────────────────────────────────────────────
        # Videos are recorded by the camera into the edge device's video
        # directory; the edge advertises what it has in its device_status
        # packets and the user picks one to query against here.
        video_header_row = QHBoxLayout()
        video_header_row.setSpacing(8)

        video_lbl = QLabel("Video source:")
        vhf = QFont("Segoe UI", 10); vhf.setWeight(QFont.Weight.Medium)
        video_lbl.setFont(vhf)
        video_lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
        video_header_row.addWidget(video_lbl)

        self.video_scope_lbl = QLabel("")
        self.video_scope_lbl.setFont(QFont("Segoe UI", 9))
        self.video_scope_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.65); background: transparent;"
        )
        video_header_row.addWidget(self.video_scope_lbl)
        video_header_row.addStretch(1)

        self.refresh_videos_btn = QToolButton()
        self.refresh_videos_btn.setText("⟳  Refresh")
        self.refresh_videos_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_videos_btn.setStyleSheet(
            "QToolButton {"
            "  background-color: rgba(184,221,255,0.18);"
            "  color: rgba(255,255,255,0.90);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 6px;"
            "  padding: 2px 10px;"
            "}"
            "QToolButton:hover { background-color: rgba(184,221,255,0.30); }"
        )
        self.refresh_videos_btn.setToolTip(
            "Ask the edge devices to re-report the contents of their video directory"
        )
        self.refresh_videos_btn.clicked.connect(self._on_refresh_videos_clicked)
        video_header_row.addWidget(self.refresh_videos_btn)

        ql.addLayout(video_header_row)
        ql.addSpacing(4)

        self.video_combo = QComboBox()
        self.video_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_combo.setFont(QFont("Segoe UI", 11))
        self.video_combo.setStyleSheet(_VIDEO_COMBO_STYLE)
        self.video_combo.setMinimumHeight(34)
        self.video_combo.setToolTip(
            "Pick a recorded video to build the query from, or keep the live camera feed"
        )
        self.video_combo.currentIndexChanged.connect(self._on_video_selection_changed)
        ql.addWidget(self.video_combo)
        ql.addSpacing(4)

        # Two prompts: one for the directory, one for its contents.
        pf_small = QFont("Segoe UI", 9)
        self.video_dir_lbl = QLabel("")
        self.video_dir_lbl.setFont(pf_small)
        self.video_dir_lbl.setWordWrap(True)
        self.video_dir_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.60); background: transparent;"
        )
        ql.addWidget(self.video_dir_lbl)

        self.video_found_lbl = QLabel("")
        self.video_found_lbl.setFont(pf_small)
        self.video_found_lbl.setWordWrap(True)
        self.video_found_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.60); background: transparent;"
        )
        ql.addWidget(self.video_found_lbl)
        ql.addSpacing(_QUERY_SECTION_GAP)

        self._rebuild_video_combo()

        self.query_input = _HistoryLineEdit(lambda: list(self._query_history))
        self.query_input.setPlaceholderText("Enter query…   (Enter to send · ↑/↓ history)")
        inf = QFont("Segoe UI", 12)
        self.query_input.setFont(inf)
        self.query_input.setStyleSheet(
            "QLineEdit {"
            "  background-color: rgba(255,255,255,0.12);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 8px;"
            "  padding: 7px 12px;"
            "  color: #FFFFFF;"
            "}"
        )
        self.query_input.setMinimumHeight(38)
        # #10 — Enter sends the query.
        self.query_input.returnPressed.connect(self._on_send_clicked)
        ql.addWidget(self.query_input)
        ql.addSpacing(_QUERY_SECTION_GAP)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.send_button = GlassButton("Send", bg_color="#D8DEF0", text_color="#131A5C")
        sbf = QFont("Segoe UI", 12); sbf.setWeight(QFont.Weight.Medium)
        self.send_button.setFont(sbf)
        self.send_button.setMinimumWidth(90)
        self.send_button.clicked.connect(self._on_send_clicked)
        btn_row.addWidget(self.send_button)

        # Visual-only Cancel button — mirrors Send's shape but in orange.
        # No backend behavior yet; the MQTT team will wire `cancel_query_request`
        # into `_on_cancel_clicked` below when their packet lands.
        self.cancel_button = GlassButton("Cancel", bg_color="#F4A261", text_color="#3D1F00")
        cbf = QFont("Segoe UI", 12); cbf.setWeight(QFont.Weight.Medium)
        self.cancel_button.setFont(cbf)
        self.cancel_button.setMinimumWidth(90)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.cancel_button)

        self.auto_separate_btn = QPushButton("⊞  Auto Pop-Out: OFF")
        self.auto_separate_btn.setCheckable(True)
        self.auto_separate_btn.setChecked(False)
        asf = QFont("Segoe UI", 11); asf.setWeight(QFont.Weight.Medium)
        self.auto_separate_btn.setFont(asf)
        self.auto_separate_btn.setMinimumHeight(38)
        self.auto_separate_btn.setMinimumWidth(180)
        self.auto_separate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_separate_btn.setStyleSheet(self._auto_sep_style(False))
        self.auto_separate_btn.toggled.connect(self._on_auto_separate_toggled)
        btn_row.addWidget(self.auto_separate_btn)
        btn_row.addStretch(1)

        ql.addLayout(btn_row)
        ql.addSpacing(_QUERY_SECTION_GAP)

        # Auto resend controls (host-driven; interval paces new sends after each response).
        auto_row = QHBoxLayout()
        auto_row.setSpacing(10)
        auto_row.setContentsMargins(0, 0, 0, 0)

        self.auto_resend_btn = QPushButton("↻  Auto Resend: OFF")
        self.auto_resend_btn.setCheckable(True)
        self.auto_resend_btn.setChecked(False)
        arf = QFont("Segoe UI", 11); arf.setWeight(QFont.Weight.Medium)
        self.auto_resend_btn.setFont(arf)
        self.auto_resend_btn.setMinimumHeight(34)
        self.auto_resend_btn.setMinimumWidth(180)
        self.auto_resend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_resend_btn.setStyleSheet(self._auto_sep_style(False))
        self.auto_resend_btn.toggled.connect(self._on_auto_resend_toggled)
        auto_row.addWidget(self.auto_resend_btn)

        every_lbl = QLabel("Every")
        every_lbl.setStyleSheet("color: rgba(255,255,255,0.72); background: transparent;")
        auto_row.addWidget(every_lbl)

        self.auto_resend_interval = QSpinBox()
        self.auto_resend_interval.setRange(1, 120)
        self.auto_resend_interval.setValue(5)
        self.auto_resend_interval.setSuffix(" s")
        self.auto_resend_interval.setFixedWidth(80)
        self.auto_resend_interval.setToolTip(
            "Time between automatic sends while Auto Resend is on. "
            "The host starts this timer after each successful send (not after each MQTT reply), "
            "so a fast edge cannot reset the cadence and starve a slower one. Overlapping work on edges is allowed."
        )
        self.auto_resend_interval.setStyleSheet(
            "QSpinBox {"
            "  background-color: rgba(255,255,255,0.12);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 8px;"
            "  padding: 5px 10px;"
            "  color: #FFFFFF;"
            "}"
        )
        self.auto_resend_interval.valueChanged.connect(lambda _v: self._emit_auto_resend_changed())
        auto_row.addWidget(self.auto_resend_interval)

        for_lbl = QLabel("Run for")
        for_lbl.setStyleSheet("color: rgba(255,255,255,0.72); background: transparent;")
        auto_row.addWidget(for_lbl)

        self.auto_resend_duration = QSpinBox()
        self.auto_resend_duration.setRange(0, 3600)
        self.auto_resend_duration.setValue(0)
        self.auto_resend_duration.setSuffix(" s")
        self.auto_resend_duration.setFixedWidth(100)
        self.auto_resend_duration.setToolTip(
            "Wall clock from when Auto Resend is turned on (or from Send if you send later). "
            "0 = keep sending until you turn Auto Resend off. "
            "Cadence: one timer per successful send, every 'Every' seconds."
        )
        self.auto_resend_duration.setStyleSheet(
            "QSpinBox {"
            "  background-color: rgba(255,255,255,0.12);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 8px;"
            "  padding: 5px 10px;"
            "  color: #FFFFFF;"
            "}"
        )
        self.auto_resend_duration.valueChanged.connect(lambda _v: self._emit_auto_resend_changed())
        auto_row.addWidget(self.auto_resend_duration)

        auto_row.addStretch(1)
        ql.addLayout(auto_row)
        ql.addSpacing(_QUERY_SECTION_GAP)

        self.auto_resend_session_lbl = QLabel("")
        srf = QFont("Segoe UI", 10)
        srf.setWeight(QFont.Weight.Medium)
        self.auto_resend_session_lbl.setFont(srf)
        self.auto_resend_session_lbl.setStyleSheet(
            "color: rgba(184,221,255,0.95); background: transparent;"
        )
        self.auto_resend_session_lbl.setVisible(False)
        ql.addWidget(self.auto_resend_session_lbl)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self.pending_label = QLabel("")
        pf = QFont("Segoe UI", 10)
        self.pending_label.setFont(pf)
        self.pending_label.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent;")
        self.pending_label.setVisible(False)
        status_row.addWidget(self.pending_label, alignment=Qt.AlignmentFlag.AlignLeft)

        # #17 — short query_id badge, helps correlate UI ↔ logs.
        self.query_id_label = QLabel("")
        qif = QFont("Consolas", 9)
        self.query_id_label.setFont(qif)
        self.query_id_label.setStyleSheet(
            "color: rgba(255,255,255,0.55); background: transparent;"
        )
        self.query_id_label.setVisible(False)
        status_row.addWidget(self.query_id_label, alignment=Qt.AlignmentFlag.AlignLeft)
        status_row.addStretch(1)
        ql.addLayout(status_row)

        query_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )

        left_col.addWidget(query_card)

        # ── Image / Metadata card ─────────────────────────────────────────────
        meta_card = CardWidget()
        ml = meta_card.content_layout()

        # Card title row — Pop Out button pinned to the right of the title
        card_title_row = QHBoxLayout()
        card_title_row.setSpacing(8)
        card_title_row.addWidget(_section_title("Image / Metadata"))
        card_title_row.addStretch(1)

        _icon_btn_style = (
            "QPushButton {"
            "  background-color: rgba(184,221,255,0.18);"
            "  color: rgba(184,221,255,0.95);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 6px;"
            "  padding: 2px 10px;"
            "}"
            "QPushButton:hover   { background-color: rgba(184,221,255,0.30); }"
            "QPushButton:pressed { background-color: rgba(184,221,255,0.12); }"
            "QPushButton:disabled{ color: rgba(255,255,255,0.30);"
            "  border-color: rgba(255,255,255,0.10); }"
        )
        popf = QFont("Segoe UI", 10); popf.setWeight(QFont.Weight.Medium)

        # #13 — Copy response text to clipboard
        self.copy_response_btn = QPushButton("⧉  Copy")
        self.copy_response_btn.setFont(popf)
        self.copy_response_btn.setFixedHeight(28)
        self.copy_response_btn.setMinimumWidth(80)
        self.copy_response_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_response_btn.setStyleSheet(_icon_btn_style)
        self.copy_response_btn.setToolTip("Copy the response text to the clipboard")
        self.copy_response_btn.clicked.connect(self._on_copy_response)
        card_title_row.addWidget(self.copy_response_btn)

        # #13 — Save the currently displayed image
        self.save_image_btn = QPushButton("⤓  Save")
        self.save_image_btn.setFont(popf)
        self.save_image_btn.setFixedHeight(28)
        self.save_image_btn.setMinimumWidth(80)
        self.save_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_image_btn.setStyleSheet(_icon_btn_style)
        self.save_image_btn.setToolTip("Save the currently displayed image to disk")
        self.save_image_btn.clicked.connect(self._on_save_image)
        card_title_row.addWidget(self.save_image_btn)

        self.popout_btn = QPushButton("⤢  Pop Out")
        self.popout_btn.setFont(popf)
        self.popout_btn.setFixedHeight(28)
        self.popout_btn.setMinimumWidth(90)
        self.popout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.popout_btn.setStyleSheet(_icon_btn_style)
        self.popout_btn.setToolTip("Open the navigable response window")
        self.popout_btn.clicked.connect(self._on_popout_clicked)
        card_title_row.addWidget(self.popout_btn)

        # Disable the action buttons until something is actually displayed.
        self.copy_response_btn.setEnabled(False)
        self.save_image_btn.setEnabled(False)

        ml.addLayout(card_title_row)
        ml.addSpacing(14)

        # Image preview
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: rgba(255,255,255,0.08);"
            "border-radius: 8px;"
        )
        # Keep aspect ratio via explicit scaled pixmaps in _add_image_on_main_thread.
        # Enabling QLabel scaledContents distorts images to fill the label bounds.
        self.image_label.setScaledContents(False)
        self.image_label.setMinimumHeight(180)
        self.image_label.clear()
        # #14 — Click the main image to open a full-size viewer.
        self.image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_label.setToolTip("Click to view full size")
        self.image_label.mousePressEvent = self._on_main_image_clicked
        ml.addWidget(self.image_label, stretch=5)

        ml.addSpacing(10)

        # Metadata fields (scrollable to prevent clipping on long responses)
        metadata_box = QWidget()
        metadata_box.setStyleSheet(
            "background-color: rgba(255,255,255,0.10);"
            "border-radius: 8px;"
        )
        mbl = QVBoxLayout(metadata_box)
        mbl.setContentsMargins(14, 12, 14, 12)
        mbl.setSpacing(5)
        mf = QFont("Segoe UI", 11)

        self.metadata_labels: dict[str, object] = {}
        for key in ["Image", "Edge Device", "Query", "Response", "Confidence Rate", "Time Processed"]:
            field_name = key.replace(" ", "_").lower()
            if field_name == "response":
                title_lbl = QLabel("Response:")
                title_lbl.setFont(mf)
                title_lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
                mbl.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignLeft)

                response_box = QTextEdit()
                response_box.setReadOnly(True)
                response_box.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                response_box.setMinimumHeight(90)
                response_box.setStyleSheet(
                    "color: rgba(255,255,255,0.92);"
                    "background-color: rgba(255,255,255,0.14);"
                    "border: none;"
                    "border-radius: 8px;"
                    "padding: 8px;"
                )
                mbl.addWidget(response_box)
                self.metadata_labels[field_name] = response_box
                continue

            lbl = QLabel(f"{key}:")
            lbl.setFont(mf)
            lbl.setStyleSheet("color: rgba(255,255,255,0.85); background: transparent;")
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            lbl.setMinimumHeight(max(24, lbl.sizeHint().height()))
            mbl.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignLeft)
            self.metadata_labels[field_name] = lbl
        mbl.addStretch(1)

        metadata_scroll = QScrollArea()
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setFrameShape(metadata_scroll.Shape.NoFrame)
        metadata_scroll.setStyleSheet("background: transparent;")
        metadata_scroll.setWidget(metadata_box)
        ml.addWidget(metadata_scroll, stretch=2)

        left_col.addWidget(meta_card, stretch=1)
        main_layout.addLayout(left_col, stretch=1)

        # ════════════════════════════════════════════════════════════════
        # RIGHT COLUMN – Images Returned
        # ════════════════════════════════════════════════════════════════
        self.images_card = CardWidget()
        il = self.images_card.content_layout()

        images_title_row = QHBoxLayout()
        images_title_row.setSpacing(8)
        images_title_row.addWidget(_section_title("Images Returned"))
        images_title_row.addStretch(1)

        # #12 — Clear all returned thumbnails / responses.
        self.clear_images_btn = QPushButton("⌫  Clear")
        clf = QFont("Segoe UI", 10); clf.setWeight(QFont.Weight.Medium)
        self.clear_images_btn.setFont(clf)
        self.clear_images_btn.setFixedHeight(28)
        self.clear_images_btn.setMinimumWidth(80)
        self.clear_images_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_images_btn.setToolTip("Remove every received image / response from this view")
        self.clear_images_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: rgba(184,221,255,0.18);"
            "  color: rgba(184,221,255,0.95);"
            "  border: 1px solid rgba(184,221,255,0.35);"
            "  border-radius: 6px;"
            "  padding: 2px 10px;"
            "}"
            "QPushButton:hover   { background-color: rgba(184,221,255,0.30); }"
            "QPushButton:pressed { background-color: rgba(184,221,255,0.12); }"
            "QPushButton:disabled{ color: rgba(255,255,255,0.30);"
            "  border-color: rgba(255,255,255,0.10); }"
        )
        self.clear_images_btn.clicked.connect(self._on_clear_results_clicked)
        self.clear_images_btn.setEnabled(False)
        images_title_row.addWidget(self.clear_images_btn)

        il.addLayout(images_title_row)
        il.addSpacing(10)

        self.returned_images_container = QWidget()
        self.returned_images_container.setStyleSheet("background: transparent;")
        self.returned_images_layout = QGridLayout(self.returned_images_container)
        self.returned_images_layout.setContentsMargins(0, 0, 0, 0)
        self.returned_images_layout.setHorizontalSpacing(10)
        self.returned_images_layout.setVerticalSpacing(10)
        self.returned_images_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(self.returned_images_container)
        il.addWidget(scroll)

        main_layout.addWidget(self.images_card, stretch=1)

        self.setCentralWidget(root)
        self.returned_images: list[dict] = []
        self._grid_columns = 2
        self._grid_count = 0
        self._selected_index = -1

    # ── public API ────────────────────────────────────────────────────────────
    def set_query_callback(self, callback):
        self._on_query_callback = callback

    def set_auto_resend_changed_callback(self, callback: Optional[Callable[[bool, int, int], None]]):
        """Owner registers a callback fired when auto-resend changes: (enabled, interval_sec, duration_sec)."""
        self._on_auto_resend_changed = callback

    def auto_resend_enabled(self) -> bool:
        return bool(self._auto_resend_enabled)

    def auto_resend_interval_sec(self) -> int:
        try:
            return max(1, int(self.auto_resend_interval.value()))
        except Exception:
            return 5

    def auto_resend_duration_sec(self) -> int:
        try:
            return int(self.auto_resend_duration.value())
        except Exception:
            return 0

    def set_auto_resend_session_deadline(self, unix_ts: Optional[float]) -> None:
        """Show countdown to session end (time.time() deadline), or hide when None."""
        self._session_deadline_ts = unix_ts
        self._session_deadline_timer.stop()
        if unix_ts is None or not isinstance(unix_ts, (int, float)):
            self.auto_resend_session_lbl.clear()
            self.auto_resend_session_lbl.setVisible(False)
            return
        self.auto_resend_session_lbl.setVisible(True)
        self._session_deadline_timer.start()
        self._tick_session_deadline()

    def _tick_session_deadline(self) -> None:
        ts = self._session_deadline_ts
        if ts is None or not isinstance(ts, (int, float)):
            self._session_deadline_timer.stop()
            return
        rem = float(ts) - time.time()
        if rem <= 0:
            self.auto_resend_session_lbl.setText("Session ended — no more auto-queries")
            self._session_deadline_timer.stop()
            return
        sec_left = max(0, int(math.ceil(rem - 1e-9)))
        self.auto_resend_session_lbl.setText(f"Last auto-query allowed in {sec_left}s")

    def set_targets_changed_callback(self, callback: Optional[Callable[[List[str]], None]]):
        """Owner registers a callback fired whenever the chip list changes.

        Used by AvailableDevicesWindow to keep its checkboxes in sync when the
        user removes/adds chips here.
        """
        self._on_targets_changed_callback = callback

    def set_models_changed_callback(
        self, callback: Optional[Callable[[str, str], None]]
    ) -> None:
        """Owner syncs per-device model picks back to Available Devices."""
        self._on_models_changed_callback = callback

    @staticmethod
    def mqtt_model_name(selected: str) -> Optional[str]:
        name = str(selected or "").strip()
        if not name or name.lower() == "default":
            return None
        return name

    def get_selected_model_for_device(self, device_name: str) -> str:
        device_name = str(device_name or "").strip()
        if not device_name:
            return "default"
        return str(self._model_by_device.get(device_name) or "default")

    def resolve_query_model_groups(
        self, target_devices: Optional[List[str]]
    ) -> List[Tuple[List[str], Optional[str]]]:
        """Group targets by model for MQTT (one send per distinct model)."""
        targets = [
            str(t).strip()
            for t in (target_devices or [])
            if isinstance(t, str) and t.strip()
        ]
        if not targets:
            return [([], None)]

        groups: dict[Optional[str], list[str]] = {}
        for name in targets:
            wire_model = self.mqtt_model_name(self.get_selected_model_for_device(name))
            groups.setdefault(wire_model, []).append(name)
        return [(device_names, model) for model, device_names in groups.items()]

    def set_device_model_catalog(
        self,
        models_by_device: Optional[Dict[str, str]] = None,
        available_by_device: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Seed or refresh model choices (e.g. from Available Devices)."""
        if models_by_device:
            for name, model in models_by_device.items():
                n = str(name or "").strip()
                if n:
                    self._model_by_device[n] = str(model or "default")
        if available_by_device:
            for name, models in available_by_device.items():
                n = str(name or "").strip()
                if not n:
                    continue
                if isinstance(models, list):
                    self._available_models_by_device[n] = [
                        str(m) for m in models if str(m).strip()
                    ]
        for name, chip in self._target_chip_widgets.items():
            chip.set_available_models(
                self._available_models_by_device.get(name),
                selected=self.get_selected_model_for_device(name),
            )

    def set_model_for_device(self, device_name: str, model: str) -> None:
        """Update one target's model without rebuilding chips (sync from Devices UI)."""
        device_name = str(device_name or "").strip()
        if not device_name:
            return
        self._model_by_device[device_name] = str(model or "default")
        chip = self._target_chip_widgets.get(device_name)
        if chip is not None:
            chip.set_model(self._model_by_device[device_name])

    def set_available_models_for_device(self, device_name: str, models: List[str]) -> None:
        device_name = str(device_name or "").strip()
        if not device_name:
            return
        self._available_models_by_device[device_name] = [
            str(m) for m in (models or []) if str(m).strip()
        ]
        chip = self._target_chip_widgets.get(device_name)
        if chip is not None:
            chip.set_available_models(
                self._available_models_by_device[device_name],
                selected=self.get_selected_model_for_device(device_name),
            )

    # ── video source ──────────────────────────────────────────────────────────
    def set_videos_refresh_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Owner registers what the ⟳ Refresh button should trigger (re-discovery)."""
        self._on_videos_refresh_callback = callback

    def set_device_video_catalog(
        self,
        videos_by_device: Optional[Dict[str, List[str]]] = None,
        video_dirs: Optional[Dict[str, str]] = None,
        created_flags: Optional[Dict[str, bool]] = None,
    ) -> None:
        """Thread-safe — feed in what each edge reports about its video directory."""
        self._videos_ready.emit(
            dict(videos_by_device or {}),
            dict(video_dirs or {}),
            dict(created_flags or {}),
        )

    def selected_video(self) -> Optional[str]:
        """Video file name the user picked, or None for the live camera feed."""
        return self._selected_video or None

    def _apply_video_catalog_on_main_thread(
        self, videos_by_device: dict, video_dirs: dict, created_flags: dict
    ) -> None:
        for name, videos in (videos_by_device or {}).items():
            n = str(name or "").strip()
            if n and isinstance(videos, list):
                self._videos_by_device[n] = [str(v) for v in videos if str(v).strip()]
        for name, path in (video_dirs or {}).items():
            n = str(name or "").strip()
            if n and str(path or "").strip():
                self._video_dir_by_device[n] = str(path).strip()
        for name, created in (created_flags or {}).items():
            n = str(name or "").strip()
            if n:
                self._video_dir_created[n] = bool(created)
        self._rebuild_video_combo()

    def _video_scope_devices(self) -> list[str]:
        """Devices whose videos are offered: the targets, or every known edge."""
        if self._target_devices:
            return list(self._target_devices)
        return sorted(self._videos_by_device.keys())

    def _rebuild_video_combo(self) -> None:
        """Refresh the picker + both prompts from the current catalog."""
        scope = self._video_scope_devices()

        # Union of video names across in-scope devices, remembering who has each
        # so the tooltip can disambiguate a name present on several edges.
        owners_by_video: dict[str, list[str]] = {}
        for device in scope:
            for video in self._videos_by_device.get(device, []):
                owners_by_video.setdefault(video, []).append(device)
        videos = sorted(owners_by_video.keys())

        previous = self._selected_video
        self.video_combo.blockSignals(True)
        self.video_combo.clear()
        self.video_combo.addItem(_LIVE_CAMERA_LABEL, "")
        for video in videos:
            self.video_combo.addItem(f"🎞  {video}", video)
            owners = owners_by_video[video]
            self.video_combo.setItemData(
                self.video_combo.count() - 1,
                "On: " + ", ".join(owners),
                Qt.ItemDataRole.ToolTipRole,
            )
        # Keep the previous pick when it survived the refresh.
        restored = self.video_combo.findData(previous) if previous else 0
        self.video_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self.video_combo.blockSignals(False)
        self._selected_video = str(self.video_combo.currentData() or "")

        self.video_combo.setEnabled(bool(videos))
        if scope and self._target_devices:
            n = len(self._target_devices)
            self.video_scope_lbl.setText(
                f"on {self._target_devices[0]}" if n == 1 else f"across {n} targeted devices"
            )
        elif scope:
            self.video_scope_lbl.setText("across all edge devices")
        else:
            self.video_scope_lbl.setText("")

        self._refresh_video_prompts(scope, videos)

    def _refresh_video_prompts(self, scope: list[str], videos: list[str]) -> None:
        """Update the directory / videos-found prompt lines."""
        _dim   = "color: rgba(255,255,255,0.55); background: transparent;"
        _ok    = "color: rgba(150,235,180,0.95); background: transparent;"
        _warn  = "color: rgba(255,200,140,0.95); background: transparent;"

        known = [d for d in scope if d in self._video_dir_by_device]
        if not known:
            self.video_dir_lbl.setStyleSheet(_dim)
            self.video_dir_lbl.setText(
                "Waiting for an edge device to report its video directory…"
            )
            self.video_found_lbl.setStyleSheet(_dim)
            self.video_found_lbl.setText("")
            return

        # Directory prompt — call out devices where this run created the folder.
        fresh = [d for d in known if self._video_dir_created.get(d)]
        self._announced_video_dirs.update(fresh)
        if fresh:
            paths = {self._video_dir_by_device[d] for d in fresh}
            where = ", ".join(fresh)
            self.video_dir_lbl.setStyleSheet(_ok)
            self.video_dir_lbl.setText(
                f"📁  Video directory created on {where} — {' / '.join(sorted(paths))}"
            )
        else:
            paths = {self._video_dir_by_device[d] for d in known}
            self.video_dir_lbl.setStyleSheet(_dim)
            self.video_dir_lbl.setText(
                f"📁  Video directory ready on {len(known)} device(s) — "
                f"{' / '.join(sorted(paths))}"
            )

        # Videos-found prompt.
        if videos:
            with_videos = [d for d in known if self._videos_by_device.get(d)]
            self.video_found_lbl.setStyleSheet(_ok)
            self.video_found_lbl.setText(
                f"🎞  {len(videos)} video(s) found on {', '.join(with_videos)}"
            )
        else:
            self.video_found_lbl.setStyleSheet(_warn)
            self.video_found_lbl.setText(
                "🎞  No videos in the directory yet — queries will use the live camera."
            )

    def _on_video_selection_changed(self, _index: int) -> None:
        self._selected_video = str(self.video_combo.currentData() or "")

    def _on_refresh_videos_clicked(self) -> None:
        cb = self._on_videos_refresh_callback
        if callable(cb):
            try:
                cb()
            except Exception as exc:
                print(f"[Query] videos refresh callback error: {exc!r}")
        else:
            print("[Query] Refresh clicked — no refresh callback registered")
        self._rebuild_video_combo()

    def set_target_devices(self, devices) -> None:
        """Replace the current target list (broadcast when empty/None)."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for name in devices or []:
            if not isinstance(name, str):
                continue
            name = name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append(name)
        if cleaned == self._target_devices:
            return
        self._target_devices = cleaned
        self._rebuild_chips()

    def set_available_devices(self, devices) -> None:
        """Tell the QueryWindow about every known device (drives the +Add menu)."""
        self._available_devices = [str(d) for d in (devices or []) if isinstance(d, str)]

    def target_devices(self) -> list[str]:
        return list(self._target_devices)

    def set_last_query_id(self, query_id: str) -> None:
        """Show a short query_id badge under the input — helps log correlation."""
        self._last_query_id = query_id or ""
        if self._last_query_id:
            short = self._last_query_id[:8]
            self.query_id_label.setText(f"qid: {short}")
            self.query_id_label.setVisible(True)
        else:
            self.query_id_label.clear()
            self.query_id_label.setVisible(False)

    def set_query_pending(self, pending: bool, message: str = "Pending response..."):
        """Toggle in-flight query UI state with an animated spinner (#15)."""
        self.send_button.setEnabled(not pending)
        self._pending_active = bool(pending)
        if pending:
            self._pending_message_base = message or "Pending response..."
            self._spinner_index = 0
            self.pending_label.setStyleSheet(
                "color: rgba(255,255,255,0.78); background: transparent;"
            )
            self.pending_label.setText(f"{self._spinner_frames[0]}  {self._pending_message_base}")
            self.pending_label.setVisible(True)
            if not self._spinner_timer.isActive():
                self._spinner_timer.start()
            # #16 — start (or restart) the query-timeout warning timer.
            self._timeout_timer.start(self._query_timeout_ms)
        else:
            self._spinner_timer.stop()
            self._timeout_timer.stop()
            self.pending_label.clear()
            self.pending_label.setVisible(False)

    def update_metadata(self, metadata: dict):
        """Thread-safe — emits signal so label updates happen on the main thread."""
        self._metadata_ready.emit(metadata)

    def _update_metadata_on_main_thread(self, metadata: dict):
        metadata = self._enrich_metadata(metadata)
        self._current_metadata = dict(metadata)

        for field, value in metadata.items():
            if field in self.metadata_labels:
                widget = self.metadata_labels[field]
                if isinstance(widget, QTextEdit):
                    widget.setPlainText("" if value is None else str(value))
                    continue
                if isinstance(widget, QLabel):
                    prefix = widget.text().split(":")[0]
                    widget.setText(f"{prefix}: {value}")
                    # Recompute wrapped height to prevent clipping/distortion.
                    widget.adjustSize()
                    widget.setMinimumHeight(max(24, widget.sizeHint().height() + 4))
                    widget.updateGeometry()

        # Receiving a populated response means the in-flight pending state ends.
        if self._pending_active and (
            metadata.get("response") or metadata.get("image") or metadata.get("edge_device")
        ):
            self.set_query_pending(False)
        # Refresh action-button enablement based on what we actually have to give.
        self._refresh_action_buttons()

        if self._auto_separate:
            # Build a key from fields that uniquely identify one response.
            # _update_metadata_on_main_thread can fire more than once per
            # response (e.g. once via add_returned_image → _set_selected_image
            # and once via the direct update_metadata call in s1_start_app).
            # Only open the pop-out the first time we see each unique response.
            key = (
                self._current_metadata.get("time_processed", "")
                + "|"
                + self._current_metadata.get("response", "")
            )
            if key and key != self._last_auto_popout_key:
                self._last_auto_popout_key = key
                self._open_popout()

    def clear_returned_images(self):
        """Thread-safe — emits signal so widget deletion happens on the main thread."""
        self._clear_ready.emit()

    def _clear_on_main_thread(self):
        while self.returned_images_layout.count():
            child = self.returned_images_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.returned_images.clear()
        self._grid_count = 0
        self._selected_index = -1
        self._refresh_action_buttons()

    def add_returned_image(self, image_path_or_data: str, metadata: dict = None):
        """Thread-safe entry point — emits a signal so widget work happens on the main thread."""
        self._image_ready.emit(image_path_or_data or "", metadata or {})

    def _add_image_on_main_thread(self, image_path_or_data: str, metadata: dict):
        """Always runs on the main thread via Qt signal. Safe to create/update widgets here."""
        metadata = self._enrich_metadata(metadata)
        px = self._load_pixmap(image_path_or_data)

        # ── Add thumbnail to right-panel grid ─────────────────────────────────
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet(
            "background-color: rgba(255,255,255,0.08);"
            "border-radius: 8px; padding: 6px;"
        )
        img_lbl.setScaledContents(False)
        img_lbl.setFixedSize(200, 140)
        img_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        if not px.isNull():
            img_lbl.setPixmap(px.scaled(
                200, 140,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            summary = str((metadata or {}).get("response", "") or "").strip()
            if len(summary) > 90:
                summary = summary[:87] + "..."
            img_lbl.setWordWrap(True)
            img_lbl.setText(summary or "No image")
        row = self._grid_count // self._grid_columns
        col = self._grid_count % self._grid_columns
        image_index = self._grid_count
        img_lbl.mousePressEvent = lambda event, idx=image_index: self._on_thumbnail_clicked(idx)
        self.returned_images_layout.addWidget(img_lbl, row, col)
        self._grid_count += 1
        self.returned_images.append({"label": img_lbl, "metadata": metadata or {}, "pixmap": px})
        if not px.isNull():
            self._current_pixmap = px
        # Select the latest image by default; users can click older thumbnails to inspect them.
        self._set_selected_image(image_index)
        self._refresh_action_buttons()

    def _on_thumbnail_clicked(self, index: int):
        self._set_selected_image(index)

    def _set_selected_image(self, index: int):
        if index < 0 or index >= len(self.returned_images):
            return

        self._selected_index = index
        base_style = (
            "background-color: rgba(255,255,255,0.08);"
            "border-radius: 8px; padding: 6px;"
        )
        selected_style = (
            "background-color: rgba(255,255,255,0.12);"
            "border: 2px solid rgba(184,221,255,0.85);"
            "border-radius: 8px; padding: 6px;"
        )

        for i, item in enumerate(self.returned_images):
            lbl = item.get("label")
            if isinstance(lbl, QLabel):
                lbl.setStyleSheet(selected_style if i == index else base_style)

        item = self.returned_images[index]
        px = item.get("pixmap")
        if isinstance(px, QPixmap) and not px.isNull():
            self._current_pixmap = px
            self.image_label.setText("")
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview = px.scaled(
                self.image_label.width() or 400,
                self.image_label.height() or 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(preview)
        else:
            self._current_pixmap = None
            self.image_label.setPixmap(QPixmap())
            response = str((item.get("metadata") or {}).get("response", "") or "").strip()
            if response:
                self.image_label.setWordWrap(True)
                self.image_label.setAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )
                self.image_label.setText(response)
            else:
                self.image_label.clear()

        metadata = item.get("metadata", {})
        if isinstance(metadata, dict):
            self.update_metadata(metadata)
        self._refresh_action_buttons()

    def _load_pixmap(self, image_path_or_data: str) -> QPixmap:
        """Load a QPixmap from a base64 string or a file path. Never raises."""
        from PyQt6.QtCore import QByteArray
        px = QPixmap()
        if not image_path_or_data:
            return px

        # Strip optional data-URI prefix: "data:image/jpeg;base64,<data>"
        raw = image_path_or_data.split(",", 1)[-1] if "," in image_path_or_data else image_path_or_data

        # Always try base64 first — if it decodes and Qt recognises the bytes, use it.
        # This handles raw base64, data-URI prefixed base64, and multi-line base64.
        try:
            decoded = base64.b64decode(raw, validate=False)
            if px.loadFromData(QByteArray(decoded)) and not px.isNull():
                return px
        except Exception:
            pass

        # Fall back to treating the original string as a file path.
        return QPixmap(image_path_or_data)

    # ── private ───────────────────────────────────────────────────────────────
    @staticmethod
    def _auto_sep_style(active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                "  background-color: rgba(100,200,140,0.25);"
                "  color: rgba(140,255,180,0.95);"
                "  border: 1px solid rgba(100,200,140,0.55);"
                "  border-radius: 8px;"
                "  padding: 4px 14px;"
                "}"
                "QPushButton:hover {"
                "  background-color: rgba(100,200,140,0.35);"
                "}"
            )
        return (
            "QPushButton {"
            "  background-color: rgba(255,255,255,0.10);"
            "  color: rgba(255,255,255,0.70);"
            "  border: 1px solid rgba(255,255,255,0.20);"
            "  border-radius: 8px;"
            "  padding: 4px 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: rgba(255,255,255,0.18);"
            "}"
        )

    def _on_auto_separate_toggled(self, checked: bool) -> None:
        self._auto_separate = checked
        label = "⊞  Auto Pop-Out: ON" if checked else "⊞  Auto Pop-Out: OFF"
        self.auto_separate_btn.setText(label)
        self.auto_separate_btn.setStyleSheet(self._auto_sep_style(checked))

    def _on_popout_clicked(self) -> None:
        self._open_popout()

    def _resolve_query_text(self, metadata: Optional[dict] = None) -> str:
        """Best-effort query string for pop-out / metadata enrichment."""
        md = metadata or {}
        q = str(md.get("query") or "").strip()
        if q:
            return q
        for candidate in (
            self._last_sent_query,
            self.query_input.text().strip(),
            (self._query_history[-1] if self._query_history else ""),
            str((self._current_metadata or {}).get("query") or "").strip(),
        ):
            if candidate:
                return candidate
        return ""

    def _enrich_metadata(self, metadata: Optional[dict]) -> dict:
        md = dict(metadata or {})
        if not str(md.get("query") or "").strip():
            resolved = self._resolve_query_text(md)
            if resolved:
                md["query"] = resolved
        return md

    def _open_popout(self, _metadata: dict = None, _pixmap: Optional[QPixmap] = None) -> None:
        """Open a navigable pop-out window showing all responses received so far."""
        if self.returned_images:
            # Snapshot — strip the thumbnail QLabel, only keep what the popout needs.
            images = [
                {
                    "metadata": self._enrich_metadata(item.get("metadata", {})),
                    "pixmap": item.get("pixmap"),
                }
                for item in self.returned_images
            ]
            index = max(0, self._selected_index) if self._selected_index >= 0 else len(images) - 1
        elif self._current_metadata:
            # No images yet (text-only response) — wrap current metadata.
            images = [{
                "metadata": self._enrich_metadata(self._current_metadata),
                "pixmap": self._current_pixmap,
            }]
            index = 0
        else:
            return

        win = ResponsePopoutWindow(images, index, parent=None)
        win.destroyed.connect(
            lambda obj=None, w=win: self._popout_windows.remove(w)
            if w in self._popout_windows else None
        )
        self._popout_windows.append(win)
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_cancel_clicked(self):
        # Stop any auto-resend loop immediately.
        try:
            if self.auto_resend_btn.isChecked():
                # This will also emit the auto-resend changed callback.
                self.auto_resend_btn.setChecked(False)
            else:
                # Still emit once so the host cancels any pending timer.
                self._emit_auto_resend_changed()
        except Exception:
            pass

        # Clear pending UI state so the user sees an immediate stop.
        try:
            self.set_query_pending(False)
        except Exception:
            pass

        # Note: MQTT cancel_query_request wiring lives in the host entrypoint.
        print("[Query] Cancel clicked — auto-resend stopped")

    def sync_auto_resend_off(self) -> None:
        """Host ended a timed session — uncheck toggle without re-notifying the host."""
        self._auto_resend_enabled = False
        self.auto_resend_btn.blockSignals(True)
        self.auto_resend_btn.setChecked(False)
        self.auto_resend_btn.setText("↻  Auto Resend: OFF")
        self.auto_resend_btn.setStyleSheet(self._auto_sep_style(False))
        self.auto_resend_btn.blockSignals(False)
        self.set_auto_resend_session_deadline(None)

    def _on_auto_resend_toggled(self, enabled: bool) -> None:
        self._auto_resend_enabled = bool(enabled)
        self.auto_resend_btn.setText("↻  Auto Resend: ON" if enabled else "↻  Auto Resend: OFF")
        self.auto_resend_btn.setStyleSheet(self._auto_sep_style(bool(enabled)))
        self._emit_auto_resend_changed()

    def _emit_auto_resend_changed(self) -> None:
        cb = getattr(self, "_on_auto_resend_changed", None)
        if callable(cb):
            try:
                cb(
                    self.auto_resend_enabled(),
                    self.auto_resend_interval_sec(),
                    self.auto_resend_duration_sec(),
                )
            except Exception:
                pass

    def _on_send_clicked(self):
        text = self.query_input.text().strip()
        if not text:
            print("[Query] No query text entered")
            return

        self._last_sent_query = text

        # #11 — push to history (skip duplicates of the most recent entry).
        if not self._query_history or self._query_history[-1] != text:
            self._query_history.append(text)
            if len(self._query_history) > self._max_history:
                self._query_history = self._query_history[-self._max_history :]
        self.query_input.reset_history_cursor()

        targets = list(self._target_devices)
        if self._on_query_callback:
            try:
                self._on_query_callback(text, targets)
            except TypeError:
                # Backward-compat: legacy callback that only accepts one arg.
                self._on_query_callback(text)
        else:
            tgt_str = (", ".join(targets) if targets else "broadcast")
            src_str = self._selected_video or "live camera"
            print(f"[Query] Query sent: '{text}' → {tgt_str} (source: {src_str}) "
                  f"— no callback registered")

    # ── chips / target devices ───────────────────────────────────────────────
    def _rebuild_chips(self) -> None:
        """Rebuild the chips strip from ``self._target_devices``."""
        # Clear existing chips (keep the trailing stretch).
        for chip in list(self._target_chip_widgets.values()):
            chip.setParent(None)
            chip.deleteLater()
        self._target_chip_widgets.clear()
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for name in self._target_devices:
            if name not in self._model_by_device:
                self._model_by_device[name] = "default"
            chip = _TargetChip(
                name,
                model=self.get_selected_model_for_device(name),
                available_models=self._available_models_by_device.get(name),
                parent=self._chips_container,
            )
            chip.removed.connect(self._on_chip_removed)
            chip.model_changed.connect(self._on_chip_model_changed)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)
            self._target_chip_widgets[name] = chip

        # Summary text right of the +Add button.
        n = len(self._target_devices)
        if n == 0:
            self.targets_summary_lbl.setText("Broadcast — all devices")
        elif n == 1:
            m = self.get_selected_model_for_device(self._target_devices[0])
            self.targets_summary_lbl.setText(
                f"Targeting 1 device · model: {m}"
            )
        else:
            self.targets_summary_lbl.setText(f"Targeting {n} devices · per-chip models")

        # The offered video list is scoped to the targets, so it moves with them.
        self._rebuild_video_combo()

        if self._on_targets_changed_callback:
            try:
                self._on_targets_changed_callback(list(self._target_devices))
            except Exception as exc:
                print(f"[Query] targets_changed callback error: {exc!r}")

    def _on_chip_removed(self, name: str) -> None:
        if name in self._target_devices:
            self._target_devices = [d for d in self._target_devices if d != name]
            self._model_by_device.pop(name, None)
            self._rebuild_chips()

    def _on_chip_model_changed(self, device_name: str, model: str) -> None:
        device_name = str(device_name or "").strip()
        if not device_name:
            return
        self._model_by_device[device_name] = str(model or "default")
        n = len(self._target_devices)
        if n == 1 and self._target_devices[0] == device_name:
            self.targets_summary_lbl.setText(
                f"Targeting 1 device · model: {self._model_by_device[device_name]}"
            )
        if self._on_models_changed_callback:
            try:
                self._on_models_changed_callback(device_name, self._model_by_device[device_name])
            except Exception as exc:
                print(f"[Query] models_changed callback error: {exc!r}")

    def _rebuild_add_target_menu(self) -> None:
        self.add_target_menu.clear()
        candidates = [d for d in self._available_devices if d not in self._target_devices]
        if not candidates:
            empty = self.add_target_menu.addAction("(no other devices)")
            empty.setEnabled(False)
            return
        for name in candidates:
            act = self.add_target_menu.addAction(name)
            act.triggered.connect(lambda _checked=False, n=name: self._add_target(n))
        self.add_target_menu.addSeparator()
        broadcast_act = self.add_target_menu.addAction("Clear all (broadcast)")
        broadcast_act.triggered.connect(lambda: self.set_target_devices([]))

    def _add_target(self, name: str) -> None:
        if name and name not in self._target_devices:
            self._target_devices.append(name)
            self._rebuild_chips()

    # ── QoL helpers ───────────────────────────────────────────────────────────
    def _refresh_action_buttons(self) -> None:
        """Enable/disable Copy / Save / Clear depending on whether we have data."""
        has_response = bool((self._current_metadata or {}).get("response"))
        self.copy_response_btn.setEnabled(has_response)
        has_image = isinstance(self._current_pixmap, QPixmap) and not self._current_pixmap.isNull()
        self.save_image_btn.setEnabled(has_image)
        self.clear_images_btn.setEnabled(bool(self.returned_images))

    def _on_copy_response(self) -> None:
        text = (self._current_metadata or {}).get("response", "")
        if not text:
            return
        QApplication.clipboard().setText(str(text))
        # Brief visual ack on the button label so the user knows it worked.
        original = self.copy_response_btn.text()
        self.copy_response_btn.setText("✓  Copied")
        QTimer.singleShot(1200, lambda: self.copy_response_btn.setText(original))

    def _on_save_image(self) -> None:
        px = self._current_pixmap
        if not isinstance(px, QPixmap) or px.isNull():
            return
        suggested = "vica_response.png"
        ts = (self._current_metadata or {}).get("time_processed")
        if isinstance(ts, str) and ts:
            safe = "".join(c if c.isalnum() else "_" for c in ts)
            suggested = f"vica_{safe}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save image", suggested,
            "PNG image (*.png);;JPEG image (*.jpg *.jpeg);;All files (*.*)"
        )
        if not path:
            return
        if not px.save(path):
            QMessageBox.warning(self, "Save failed",
                                f"Could not save image to:\n{path}")

    def _on_main_image_clicked(self, _event) -> None:
        # #14 — open the navigable popout focused on the current selection,
        # falling back to a simple viewer when there's nothing else to navigate.
        if self.returned_images:
            self._open_popout()
            return
        if isinstance(self._current_pixmap, QPixmap) and not self._current_pixmap.isNull():
            viewer = _ImageViewerDialog(self._current_pixmap, parent=None)
            viewer.show()
            viewer.raise_()
            viewer.activateWindow()

    def _on_clear_results_clicked(self) -> None:
        if not self.returned_images:
            return
        self.clear_returned_images()
        self.image_label.clear()
        self._current_pixmap = None
        self._current_metadata = {}
        self._refresh_action_buttons()

    def _tick_spinner(self) -> None:
        if not self._pending_active:
            self._spinner_timer.stop()
            return
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_index]
        self.pending_label.setText(f"{frame}  {self._pending_message_base}")

    def _on_query_timeout(self) -> None:
        if not self._pending_active:
            return
        self._spinner_timer.stop()
        self.pending_label.setStyleSheet(
            "color: rgba(255,200,140,0.95); background: transparent;"
        )
        self.pending_label.setText(
            f"⚠  No response after {self._query_timeout_ms // 1000}s — try again?"
        )
        # Re-enable the Send button so the user can retry.
        self.send_button.setEnabled(True)
        self._pending_active = False


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()