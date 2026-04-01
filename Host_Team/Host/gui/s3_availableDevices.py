from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QFont, QPixmap, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QWidget,
    QVBoxLayout,
)
import sys
import os

# Add necessary paths for imports
current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)  # Host/gui/
host_dir = os.path.dirname(current_dir)  # Host/
host_team_dir = os.path.dirname(host_dir)  # Host_Team/
project_root = os.path.dirname(host_team_dir)  # project root

for path in [current_dir, host_dir, host_team_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from s4_query import MainWindow as QueryWindow


class CardWidget(QWidget):
    def __init__(self, width: int, height: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(30, 20, 30, 20)
        self._layout.setSpacing(0)

    def content_layout(self) -> QVBoxLayout:
        return self._layout

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())
        rect.adjust(1.0, 1.0, -1.0, -1.0)
        radius = min(rect.width(), rect.height()) * 0.15

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(0x13, 0x1A, 0x5C, int(255 * 0.7)))
        gradient.setColorAt(1, QColor(0xB8, 0xDD, 0xFF, int(255 * 0.7)))

        painter.fillPath(path, gradient)

        shadow_gradient = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.6)
        shadow_gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow_gradient.setColorAt(0.75, QColor(0, 0, 0, 0))
        shadow_gradient.setColorAt(1.0, QColor(0, 0, 0, 80))

        painter.setBrush(shadow_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        inner_rect = QRectF(rect)
        inner_rect.adjust(6.0, 6.0, -6.0, -6.0)
        inner_radius = max(0.0, radius - 6)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner_rect, inner_radius, inner_radius)

        highlight = QLinearGradient(inner_rect.topLeft(), inner_rect.bottomRight())
        highlight.setColorAt(0.0, QColor(255, 255, 255, 40))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setBrush(highlight)
        painter.drawPath(inner_path)

        border_pen = QPen(QColor(255, 255, 255, 50), 1.5)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class PillButton(QPushButton):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._base_color = QColor("#051140")
        self._hover_color = QColor("#0A1C66")
        self._pressed_color = QColor("#030A28")
        self._text_color = QColor("#BABABA")
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setMinimumWidth(240)
        self.setFixedHeight(80)

    def enterEvent(self, event):  # type: ignore[override]
        self._hover = True
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):  # type: ignore[override]
        self._hover = False
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = min(200.0, rect.height() / 2.0)

        if self.isDown():
            color = self._pressed_color
        elif self._hover:
            color = self._hover_color
        else:
            color = self._base_color

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, color)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        font = self.font()
        painter.setFont(font)
        painter.setPen(self._text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


def create_camera_pixmap(size: int = 96) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    body_rect = QRectF(size * 0.18, size * 0.25, size * 0.64, size * 0.32)
    body_gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
    body_gradient.setColorAt(0.0, QColor(32, 36, 58))
    body_gradient.setColorAt(0.5, QColor(56, 61, 92))
    body_gradient.setColorAt(1.0, QColor(20, 24, 42))
    painter.setBrush(QBrush(body_gradient))
    painter.setPen(QPen(QColor(15, 15, 25), 1.5))
    painter.drawRoundedRect(body_rect, size * 0.08, size * 0.08)

    visor_path = QPainterPath()
    visor_rect = QRectF(body_rect.left(), body_rect.top() - size * 0.18, body_rect.width(), body_rect.height() * 0.7)
    visor_path.addRoundedRect(visor_rect, size * 0.08, size * 0.08)
    painter.fillPath(visor_path, QColor(22, 24, 40, 210))

    lens_center = QPointF(body_rect.left() + body_rect.height() * 0.65, body_rect.center().y())
    lens_gradient = QRadialGradient(lens_center, body_rect.height() * 0.35)
    lens_gradient.setColorAt(0.0, QColor(210, 50, 70))
    lens_gradient.setColorAt(0.4, QColor(110, 20, 35))
    lens_gradient.setColorAt(0.8, QColor(25, 28, 44))
    lens_gradient.setColorAt(1.0, QColor(15, 17, 28))
    painter.setBrush(QBrush(lens_gradient))
    painter.setPen(QPen(QColor(12, 14, 26), 1))
    painter.drawEllipse(lens_center, body_rect.height() * 0.28, body_rect.height() * 0.28)

    mount_path = QPainterPath()
    base_point = QPointF(body_rect.left() + body_rect.width() * 0.15, body_rect.bottom())
    mount_path.moveTo(base_point)
    mount_path.lineTo(base_point + QPointF(-size * 0.12, size * 0.22))
    mount_path.lineTo(base_point + QPointF(-size * 0.04, size * 0.22))
    mount_path.lineTo(base_point + QPointF(size * 0.12, size * 0.05))
    mount_path.closeSubpath()
    painter.setBrush(QColor(30, 32, 50))
    painter.setPen(QPen(QColor(12, 14, 26), 1))
    painter.drawPath(mount_path)

    painter.end()
    return pixmap


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Available Devices")
        self.resize(1440, 960)

        central = QWidget()
        central.setStyleSheet("background-color: #1D2BA1;")

        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        cards: list[CardWidget] = []
        for width, height in [(1407, 68), (1407, 644), (1407, 183)]:
            card = CardWidget(width, height)
            layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
            cards.append(card)

        top_card, middle_card, bottom_card = cards

        title = QLabel("Available Devices")
        title_font = QFont("Inter", 48)
        title_font.setWeight(QFont.Weight.Normal)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 116.0)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setMinimumSize(788, 43)
        title.setStyleSheet(
            "color: #FFFFFF;"
            "background-color: transparent;"
        )
        top_card.content_layout().addStretch(1)
        top_card.content_layout().addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        top_card.content_layout().addStretch(1)

        # Devices list - initially empty, populated via discovery_response packets
        # Format matches packetStructure.md discovery_response -> GUI format:
        # - name: device name from packet
        # - location: auto-generated or from extended metadata
        # - status: mapped from "online"/"offline" to "Online"/"Offline"/"Needs Attention"
        # - connection: mapped from network_strength dBm to "Strong"/"Medium"/"Weak"
        # - metadata: generated from cpu/ram/gpu/isProcessing
        self.devices = []
        
        # Callback for when discovery is requested (to be set by handler)
        self._on_discover_callback = None

        middle_layout = middle_card.content_layout()
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)
        middle_layout.addStretch(1)

        self.devices_panel = QWidget()
        self.devices_panel.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.95);"
            "border-radius: 28px;"
        )
        self.devices_panel.setFixedWidth(1320)

        shadow = QGraphicsDropShadowEffect(self.devices_panel)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 12)
        self.devices_panel.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(self.devices_panel)
        panel_layout.setContentsMargins(56, 40, 56, 40)
        panel_layout.setSpacing(28)

        middle_title = QLabel("Edge Devices")
        middle_title_font = QFont("Inter", 20)
        middle_title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 125.0)
        middle_title.setFont(middle_title_font)
        middle_title.setStyleSheet("color: #1E1E1E; background-color: transparent;")
        panel_layout.addWidget(middle_title, alignment=Qt.AlignmentFlag.AlignLeft)

        # Store device widgets for updates
        self.device_widgets = {}
        
        for device in self.devices:
            row = QWidget()
            row.setStyleSheet(
                "background-color: rgba(255, 255, 255, 1.0);"
                "border: 1px solid rgba(19, 26, 92, 0.12);"
                "border-radius: 16px;"
            )

            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(24, 20, 24, 20)
            row_layout.setSpacing(32)

            thumb = QLabel()
            thumb.setFixedSize(96, 96)
            thumb.setStyleSheet(
                "background-color: rgba(240, 240, 240, 0.0);"
                "border: none;"
            )
            camera_pixmap = create_camera_pixmap(96)
            thumb.setPixmap(camera_pixmap)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(thumb)

            info_column = QVBoxLayout()
            info_column.setSpacing(8)

            name_label = QLabel(device["name"])
            name_font = QFont("Inter", 16)
            name_font.setWeight(QFont.Weight.Medium)
            name_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112.0)
            name_label.setFont(name_font)
            name_label.setStyleSheet("color: #1E1E1E; background-color: transparent;")
            info_column.addWidget(name_label)

            location_label = QLabel(device["location"])
            location_label.setWordWrap(True)
            location_font = QFont("Inter", 12)
            location_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108.0)
            location_label.setFont(location_font)
            location_label.setStyleSheet("color: #555B76; background-color: transparent;")
            info_column.addWidget(location_label)

            row_layout.addLayout(info_column, stretch=3)

            status_column = QVBoxLayout()
            status_column.setSpacing(10)

            status_font = QFont("Inter", 12)
            status_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110.0)

            status_label = QLabel(f"Status: {device['status']}")
            status_label.setFont(status_font)
            status_label.setStyleSheet("color: #131A5C; background-color: transparent;")

            connection_label = QLabel(f"Connection: {device['connection']}")
            connection_label.setFont(status_font)
            connection_label.setStyleSheet("color: #131A5C; background-color: transparent;")

            metadata_label = QLabel(f"Metadata: {device['metadata']}")
            metadata_label.setFont(status_font)
            metadata_label.setStyleSheet("color: #131A5C; background-color: transparent;")

            status_column.addWidget(status_label)
            status_column.addWidget(connection_label)
            status_column.addWidget(metadata_label)

            row_layout.addLayout(status_column, stretch=2)

            panel_layout.addWidget(row)
            
            # Store widget references for updates
            self.device_widgets[device["name"]] = {
                "row": row,
                "name_label": name_label,
                "location_label": location_label,
                "status_label": status_label,
                "connection_label": connection_label,
                "metadata_label": metadata_label
            }

        middle_layout.addWidget(self.devices_panel, alignment=Qt.AlignmentFlag.AlignCenter)
        middle_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(0)
        button_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        font = QFont("Segoe UI", 16)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104.0)

        button_row.addStretch(1)
        self.discover_btn = None
        self.query_btn = None
        self.exit_btn = None
        
        for index, label in enumerate(("Discover", "Query", "Exit")):
            btn = PillButton(label)
            btn.setFont(font)
            button_row.addWidget(btn)
            
            if label == "Discover":
                self.discover_btn = btn
                self.discover_btn.clicked.connect(self._on_discover_clicked)
            elif label == "Query":
                self.query_btn = btn
                self.query_btn.clicked.connect(self._open_query_window)
            elif label == "Exit":
                self.exit_btn = btn
                self.exit_btn.clicked.connect(self._exit_application)
            
            if index < 2:
                button_row.addStretch(1)
        button_row.addStretch(1)

        bottom_card.content_layout().addLayout(button_row)

        self.setCentralWidget(central)
        self._query_window = None
    
    def _on_discover_clicked(self):
        """Handle Discover button click - triggers discovery request"""
        if self._on_discover_callback:
            # Call the registered callback (set by handler/MQTT client)
            self._on_discover_callback()
        else:
            print("[AvailableDevices] Discover clicked - no callback registered")
    
    def set_discover_callback(self, callback):
        """Set the callback function to be called when Discover is clicked.
        
        The callback should send a discovery packet as per packetStructure.md:
        {
            "header": {
                "timestamp": "<ISO-8601>",
                "source_device": "<host_name>",
                "message_type": "discovery"
            },
            "body": {}
        }
        """
        self._on_discover_callback = callback
    
    def _open_query_window(self):
        """Open the query window when Query button is clicked"""
        if self._query_window is None or not self._query_window.isVisible():
            self._query_window = QueryWindow()
            self._query_window.show()
        else:
            self._query_window.raise_()
            self._query_window.activateWindow()
    
    def _exit_application(self):
        """Exit the application when Exit button is clicked"""
        QApplication.instance().quit()
    
    def update_devices(self, devices: list):
        """Update the device list with new devices."""
        self.devices = devices
        # Clear existing device widgets
        for widget_dict in self.device_widgets.values():
            widget_dict["row"].setParent(None)
            widget_dict["row"].deleteLater()
        self.device_widgets.clear()
        
        # Get panel layout
        panel_layout = self.devices_panel.layout()
        # Remove title but keep it
        title_widget = panel_layout.itemAt(0).widget()
        # Clear all items except title
        while panel_layout.count() > 1:
            item = panel_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        
        # Recreate device rows
        for device in devices:
            self._create_device_row(device, panel_layout)
        
        panel_layout.invalidate()
        self.devices_panel.adjustSize()
        self.devices_panel.update()
        self.devices_panel.repaint()

    
    def add_device(self, device: dict):
        """Add a new device to the list."""
        self.devices.append(device)
        panel_layout = self.devices_panel.layout()
        self._create_device_row(device, panel_layout)
    
    def remove_device(self, device_name: str):
        """Remove a device from the list."""
        if device_name in self.device_widgets:
            widget_dict = self.device_widgets[device_name]
            widget_dict["row"].setParent(None)
            widget_dict["row"].deleteLater()
            del self.device_widgets[device_name]
            self.devices = [d for d in self.devices if d["name"] != device_name]
    
    def update_device_status(self, device_name: str, status: dict):
        """Update status information for a specific device."""
        if device_name in self.device_widgets:
            widget_dict = self.device_widgets[device_name]
            if "status" in status:
                widget_dict["status_label"].setText(f"Status: {status['status']}")
            if "connection" in status:
                widget_dict["connection_label"].setText(f"Connection: {status['connection']}")
            if "metadata" in status:
                widget_dict["metadata_label"].setText(f"Metadata: {status['metadata']}")
            
            # Update device data
            for device in self.devices:
                if device["name"] == device_name:
                    device.update(status)
                    break
    
    def _create_device_row(self, device: dict, panel_layout):
        """Create a device row widget and add it to the panel."""
        row = QWidget()
        row.setStyleSheet(
            "background-color: rgba(255, 255, 255, 1.0);"
            "border: 1px solid rgba(19, 26, 92, 0.12);"
            "border-radius: 16px;"
        )

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(24, 20, 24, 20)
        row_layout.setSpacing(32)

        thumb = QLabel()
        thumb.setFixedSize(96, 96)
        thumb.setStyleSheet(
            "background-color: rgba(240, 240, 240, 0.0);"
            "border: none;"
        )
        camera_pixmap = create_camera_pixmap(96)
        thumb.setPixmap(camera_pixmap)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(thumb)

        info_column = QVBoxLayout()
        info_column.setSpacing(8)

        name_label = QLabel(device["name"])
        name_font = QFont("Inter", 16)
        name_font.setWeight(QFont.Weight.Medium)
        name_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112.0)
        name_label.setFont(name_font)
        name_label.setStyleSheet("color: #1E1E1E; background-color: transparent;")
        info_column.addWidget(name_label)

        location_label = QLabel(device["location"])
        location_label.setWordWrap(True)
        location_font = QFont("Inter", 12)
        location_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108.0)
        location_label.setFont(location_font)
        location_label.setStyleSheet("color: #555B76; background-color: transparent;")
        info_column.addWidget(location_label)

        row_layout.addLayout(info_column, stretch=3)

        status_column = QVBoxLayout()
        status_column.setSpacing(10)

        status_font = QFont("Inter", 12)
        status_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110.0)

        status_label = QLabel(f"Status: {device.get('status', 'Unknown')}")
        status_label.setFont(status_font)
        status_label.setStyleSheet("color: #131A5C; background-color: transparent;")

        connection_label = QLabel(f"Connection: {device.get('connection', 'Unknown')}")
        connection_label.setFont(status_font)
        connection_label.setStyleSheet("color: #131A5C; background-color: transparent;")

        metadata_label = QLabel(f"Metadata: {device.get('metadata', 'N/A')}")
        metadata_label.setFont(status_font)
        metadata_label.setStyleSheet("color: #131A5C; background-color: transparent;")

        status_column.addWidget(status_label)
        status_column.addWidget(connection_label)
        status_column.addWidget(metadata_label)

        row_layout.addLayout(status_column, stretch=2)

        panel_layout.addWidget(row)
        
        # Store widget references
        self.device_widgets[device["name"]] = {
            "row": row,
            "name_label": name_label,
            "location_label": location_label,
            "status_label": status_label,
            "connection_label": connection_label,
            "metadata_label": metadata_label
        }


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
