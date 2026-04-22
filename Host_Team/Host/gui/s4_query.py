from typing import Optional
from pathlib import Path
import os
import sys
import math
import base64

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient, QFont, QPixmap, QBrush, QIcon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
)

# ── constants ─────────────────────────────────────────────────────────────────
WIN_W, WIN_H  = 1100, 760
BRAND_BG      = "#1D2BA1"
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

    def __init__(self) -> None:
        super().__init__()
        self._image_ready.connect(self._add_image_on_main_thread)
        self._metadata_ready.connect(self._update_metadata_on_main_thread)
        self._clear_ready.connect(self._clear_on_main_thread)

        # Native OS title bar – logo + descriptive title
        self.setWindowTitle("Query – Sentinel Nexus")
        self.setWindowIcon(_app_icon())
        self.resize(WIN_W, WIN_H)
        self.setMinimumSize(860, 580)

        self._on_query_callback = None

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
        query_card.setFixedHeight(200)
        ql = query_card.content_layout()
        ql.addWidget(_section_title("Query"))
        ql.addSpacing(14)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter query…")
        inf = QFont("Segoe UI", 12)
        self.query_input.setFont(inf)
        self.query_input.setStyleSheet(
            "background-color: rgba(255,255,255,0.12);"
            "border: 1px solid rgba(184,221,255,0.35);"
            "border-radius: 8px;"
            "padding: 7px 12px;"
            "color: #FFFFFF;"
        )
        self.query_input.setMinimumHeight(38)
        ql.addWidget(self.query_input)
        ql.addSpacing(10)

        self.send_button = GlassButton("Send", bg_color="#D8DEF0", text_color="#131A5C")
        sbf = QFont("Segoe UI", 12); sbf.setWeight(QFont.Weight.Medium)
        self.send_button.setFont(sbf)
        self.send_button.setMinimumWidth(90)
        self.send_button.clicked.connect(self._on_send_clicked)
        ql.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.pending_label = QLabel("")
        pf = QFont("Segoe UI", 10)
        self.pending_label.setFont(pf)
        self.pending_label.setStyleSheet("color: rgba(255,255,255,0.75); background: transparent;")
        self.pending_label.setVisible(False)
        ql.addWidget(self.pending_label, alignment=Qt.AlignmentFlag.AlignLeft)
        ql.addStretch(1)

        left_col.addWidget(query_card)

        # ── Image / Metadata card ─────────────────────────────────────────────
        meta_card = CardWidget()
        ml = meta_card.content_layout()
        ml.addWidget(_section_title("Image / Metadata"))
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
        il.addWidget(_section_title("Images Returned"))
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

    def set_query_pending(self, pending: bool, message: str = "Pending..."):
        """Toggle in-flight query UI state."""
        self.send_button.setEnabled(not pending)
        self.pending_label.setText(message if pending else "")
        self.pending_label.setVisible(bool(pending))

    def update_metadata(self, metadata: dict):
        """Thread-safe — emits signal so label updates happen on the main thread."""
        self._metadata_ready.emit(metadata)

    def _update_metadata_on_main_thread(self, metadata: dict):
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

    def add_returned_image(self, image_path_or_data: str, metadata: dict = None):
        """Thread-safe entry point — emits a signal so widget work happens on the main thread."""
        self._image_ready.emit(image_path_or_data or "", metadata or {})

    def _add_image_on_main_thread(self, image_path_or_data: str, metadata: dict):
        """Always runs on the main thread via Qt signal. Safe to create/update widgets here."""
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
        row = self._grid_count // self._grid_columns
        col = self._grid_count % self._grid_columns
        image_index = self._grid_count
        img_lbl.mousePressEvent = lambda event, idx=image_index: self._on_thumbnail_clicked(idx)
        self.returned_images_layout.addWidget(img_lbl, row, col)
        self._grid_count += 1
        self.returned_images.append({"label": img_lbl, "metadata": metadata or {}, "pixmap": px})
        # Select the latest image by default; users can click older thumbnails to inspect them.
        self._set_selected_image(image_index)

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
            preview = px.scaled(
                self.image_label.width() or 400,
                self.image_label.height() or 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(preview)

        metadata = item.get("metadata", {})
        if isinstance(metadata, dict):
            self.update_metadata(metadata)

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
    def _on_send_clicked(self):
        text = self.query_input.text().strip()
        if not text:
            print("[Query] No query text entered")
            return
        if self._on_query_callback:
            self._on_query_callback(text)
        else:
            print(f"[Query] Query sent: '{text}' – no callback registered")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()