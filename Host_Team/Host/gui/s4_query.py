from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QFont, QPixmap, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QWidget,
    QVBoxLayout,
)
import sys
import math
import base64


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
        # Reduced corner radius for less intense beveling
        radius = min(rect.width(), rect.height()) * 0.04

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Glassmorphism: Semi-transparent background with stronger contrast gradient
        # Darker at top, lighter at bottom for more contrast
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(0x0D, 0x14, 0x4A, int(255 * 0.5)))  # Darker blue at top
        gradient.setColorAt(0.3, QColor(0x13, 0x1A, 0x5C, int(255 * 0.45)))  # Medium dark
        gradient.setColorAt(1, QColor(0xB8, 0xDD, 0xFF, int(255 * 0.4)))  # Light blue at bottom

        painter.fillPath(path, gradient)
        
        # Subtle glow around edges
        painter.save()
        glow_path = QPainterPath()
        glow_path.addRoundedRect(rect, radius, radius)
        
        # Create a soft glow effect at the edges
        edge_glow = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.6)
        edge_glow.setColorAt(0.0, QColor(0x5F, 0x73, 0xF9, 0))  # Transparent at center
        edge_glow.setColorAt(0.7, QColor(0x5F, 0x73, 0xF9, 0))
        edge_glow.setColorAt(0.9, QColor(0x5F, 0x73, 0xF9, 20))  # Subtle glow at edges
        edge_glow.setColorAt(1.0, QColor(0x5F, 0x73, 0xF9, 30))  # Slightly stronger at very edge
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge_glow)
        painter.drawPath(glow_path)
        painter.restore()

        # Inner shadow effect (Apple glass effect) - softer, more gradual
        # Position: X=0, Y=4, Blur=15, Spread=8, Color=#5F73F9 at 30% opacity
        painter.save()
        painter.setClipPath(path)
        
        # Create inner shadow with larger spread for softer effect
        inner_shadow_rect = QRectF(rect)
        inner_shadow_rect.adjust(12.0, 12.0 + 4.0, -12.0, -12.0)  # Larger spread for softer edge
        inner_shadow_radius = max(0.0, radius - 12)
        
        # Create paths
        outer_path = QPainterPath()
        outer_path.addRoundedRect(rect, radius, radius)
        
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner_shadow_rect, inner_shadow_radius, inner_shadow_radius)
        
        # The inner shadow is the area between outer and inner paths
        shadow_path = outer_path.subtracted(inner_path)
        
        # Draw with smoother, more gradual blur using more passes
        blur_passes = 15  # More passes for smoother gradient
        for i in range(blur_passes):
            # Softer fade with exponential curve
            fade_factor = (1.0 - (i / blur_passes)) ** 1.5  # Exponential fade for softer edge
            alpha = int(255 * 0.2 * fade_factor / blur_passes)  # Reduced base opacity
            if alpha > 0:
                blur_color = QColor(0x5F, 0x73, 0xF9, alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(blur_color)
                painter.drawPath(shadow_path)
        
        # Additional soft gradient overlay for extra softness
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        soft_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        soft_gradient.setColorAt(0.0, QColor(0x5F, 0x73, 0xF9, 5))  # Very subtle at top
        soft_gradient.setColorAt(0.5, QColor(0x5F, 0x73, 0xF9, 0))
        soft_gradient.setColorAt(1.0, QColor(0x5F, 0x73, 0xF9, 0))
        painter.setBrush(soft_gradient)
        painter.drawPath(shadow_path)
        
        painter.restore()

        # Glassmorphism: Subtle light overlay on top
        painter.save()
        painter.setClipPath(path)
        top_highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top_highlight.setColorAt(0.0, QColor(255, 255, 255, 60))  # Bright highlight at top
        top_highlight.setColorAt(0.3, QColor(255, 255, 255, 20))
        top_highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        painter.setBrush(top_highlight)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)
        painter.restore()

        # Glassmorphism: Gradient border that fades from top to bottom
        # Create a gradient that matches the card gradient - visible at top, fades at bottom
        border_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        border_gradient.setColorAt(0.0, QColor(0xB8, 0xDD, 0xFF, 150))  # Visible at top
        border_gradient.setColorAt(0.5, QColor(0xB8, 0xDD, 0xFF, 80))   # Fading in middle
        border_gradient.setColorAt(1.0, QColor(0xB8, 0xDD, 0xFF, 0))    # Transparent at bottom
        
        # Draw border using gradient brush
        border_pen = QPen(QBrush(border_gradient), 1.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class GlassButton(QPushButton):
    """Button with glassmorphism effect: drop shadow and inner shadow"""
    def __init__(self, text: str, bg_color: str = "#E0E0E0", text_color: str = "#1E1E1E", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._bg_color = QColor(bg_color)
        self._text_color = QColor(text_color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setMinimumHeight(40)

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Account for shadow space
        rect = QRectF(self.rect()).adjusted(0, 0, 0, -4)  # Leave space for shadow
        radius = 8.0

        # Drop shadow (darker, multiply mode) - drawn first, behind button
        painter.save()
        shadow_rect = QRectF(rect)
        shadow_rect.translate(0, 4)  # Offset downward
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, radius, radius)
        
        # Dark shadow gradient
        shadow_gradient = QRadialGradient(shadow_rect.center(), max(shadow_rect.width(), shadow_rect.height()) * 0.7)
        shadow_gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow_gradient.setColorAt(0.6, QColor(0, 0, 0, 80))
        shadow_gradient.setColorAt(1.0, QColor(0, 0, 0, 120))
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow_gradient)
        painter.drawPath(shadow_path)
        painter.restore()

        # Main button shape
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Fill background
        painter.fillPath(path, self._bg_color)

        # Inner shadow (lighter, softlight mode)
        painter.save()
        painter.setClipPath(path)
        inner_shadow_rect = QRectF(rect)
        inner_shadow_rect.adjust(2.0, 2.0, -2.0, -2.0)
        inner_shadow_path = QPainterPath()
        inner_shadow_path.addRoundedRect(inner_shadow_rect, radius - 2, radius - 2)
        
        # Create inner shadow gradient (lighter at edges)
        inner_shadow_gradient = QLinearGradient(inner_shadow_rect.topLeft(), inner_shadow_rect.bottomLeft())
        inner_shadow_gradient.setColorAt(0.0, QColor(255, 255, 255, 50))
        inner_shadow_gradient.setColorAt(0.5, QColor(255, 255, 255, 20))
        inner_shadow_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        
        outer_path = QPainterPath()
        outer_path.addRoundedRect(rect, radius, radius)
        shadow_area = outer_path.subtracted(inner_shadow_path)
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SoftLight)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(inner_shadow_gradient)
        painter.drawPath(shadow_area)
        painter.restore()

        # Draw text with padding
        text_rect = QRectF(rect)
        text_rect.adjust(12, 0, -12, 0)  # Horizontal padding
        painter.setPen(self._text_color)
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())


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


class TitleBarButton(QPushButton):
    """Custom window control button with light gray outline icons"""
    def __init__(self, icon_char: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(icon_char, parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._hover = False
        self._icon_char = icon_char
        
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
        
        rect = QRectF(self.rect())
        
        # Light gray outline icon
        if self._hover:
            icon_color = QColor(255, 255, 255, 220)  # Slightly brighter on hover
        else:
            icon_color = QColor(255, 255, 255, 150)  # Light gray outline
        
        # Set consistent pen width for all icons
        pen = QPen(icon_color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Draw icon based on character
        if self._icon_char == "⚙":
            # Settings icon - simple outline gear
            center_x = rect.center().x()
            center_y = rect.center().y()
            outer_radius = 7
            inner_radius = 4
            
            # Draw gear as outline: outer circle with notches
            gear_path = QPainterPath()
            num_teeth = 8
            for i in range(num_teeth * 2):
                angle = i * 360.0 / (num_teeth * 2)
                rad = math.radians(angle)
                if i % 2 == 0:
                    # Outer point
                    radius = outer_radius
                else:
                    # Inner point
                    radius = inner_radius
                x = center_x + radius * math.cos(rad)
                y = center_y + radius * math.sin(rad)
                if i == 0:
                    gear_path.moveTo(x, y)
                else:
                    gear_path.lineTo(x, y)
            gear_path.closeSubpath()
            painter.drawPath(gear_path)
        elif self._icon_char == "−":
            # Minimize - horizontal line
            y = rect.center().y()
            painter.drawLine(QPointF(rect.left() + 4, y), QPointF(rect.right() - 4, y))
        elif self._icon_char == "□":
            # Maximize - two overlapping squares (outline style)
            size = 8
            center_x = rect.center().x()
            center_y = rect.center().y()
            # Back square
            back_rect = QRectF(center_x - size/2, center_y - size/2, size, size)
            painter.drawRect(back_rect)
            # Front square (offset)
            front_rect = QRectF(center_x - size/2 + 1, center_y - size/2 + 1, size, size)
            painter.drawRect(front_rect)
        elif self._icon_char == "×":
            # Close - X
            margin = 4
            painter.drawLine(QPointF(rect.left() + margin, rect.top() + margin), 
                           QPointF(rect.right() - margin, rect.bottom() - margin))
            painter.drawLine(QPointF(rect.right() - margin, rect.top() + margin), 
                           QPointF(rect.left() + margin, rect.bottom() - margin))


class TitleBar(QWidget):
    """Custom glassmorphism title bar"""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)  # Thinner title bar
        self._drag_position = QPoint()
        self._dragging = False
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        
        layout.addStretch()
        
        # Centered title
        title = QLabel("Sentinal Nexus")
        title_font = QFont("SF Pro Display", 11)
        title_font.setWeight(500)  # Medium weight
        title.setFont(title_font)
        title.setStyleSheet("color: rgba(255, 255, 255, 0.8); background-color: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # All buttons on right: settings, minimize, maximize, close
        # Settings button
        settings_btn = TitleBarButton("⚙")
        # settings_btn.clicked.connect(self._show_settings)  # TODO: Add settings functionality
        layout.addWidget(settings_btn)
        
        layout.addSpacing(8)
        
        # Window controls with light gray outline icons
        minimize_btn = TitleBarButton("−")
        minimize_btn.clicked.connect(self.window().showMinimized)
        layout.addWidget(minimize_btn)
        
        self._maximize_btn = TitleBarButton("□")
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self._maximize_btn)
        
        close_btn = TitleBarButton("×")
        close_btn.clicked.connect(self.window().close)
        layout.addWidget(close_btn)
        
        # Initialize button icon based on initial window state
        QTimer.singleShot(0, self._update_maximize_button)
        
    def _toggle_maximize(self):
        window = self.window()
        if window:
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            
            # Update button icon after state change (use timer to check after change completes)
            QTimer.singleShot(10, self._update_maximize_button)
    
    def _update_maximize_button(self):
        """Update maximize button icon based on current window state"""
        window = self.window()
        if window:
            if window.isMaximized():
                self._maximize_btn._icon_char = "□"  # Show restore icon
            else:
                self._maximize_btn._icon_char = "□"  # Show maximize icon
            self._maximize_btn.update()
            
    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):  # type: ignore[override]
        if self._dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
            
    def mouseReleaseEvent(self, event):  # type: ignore[override]
        self._dragging = False
        event.accept()
        
    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = QRectF(self.rect())
        
        # Glassmorphism background
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(0x0D, 0x14, 0x4A, int(255 * 0.6)))
        gradient.setColorAt(1, QColor(0x13, 0x1A, 0x5C, int(255 * 0.5)))
        painter.fillRect(rect, gradient)
        
        # Subtle bottom border
        border_pen = QPen(QColor(0xB8, 0xDD, 0xFF, 30), 1.0)
        painter.setPen(border_pen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Remove default title bar
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Image Management")
        self.resize(1440, 960)

        # Main container
        main_container = QWidget()
        main_container.setStyleSheet("background-color: #1D2BA1;")
        
        # Vertical layout for title bar and content
        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Custom title bar
        title_bar = TitleBar(self)
        container_layout.addWidget(title_bar)

        central = QWidget()
        central.setStyleSheet("background-color: #1D2BA1;")

        # Main horizontal layout for two columns
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Left column - contains Query and Starred Images
        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        left_column.setContentsMargins(0, 0, 0, 0)

        # Query panel
        query_card = CardWidget(600, 250)
        query_layout = query_card.content_layout()
        
        query_title = QLabel("Query")
        # Apple-style typography: system font, tighter spacing, semibold weight
        query_title_font = QFont("SF Pro Display", 17)  # Apple's preferred font, fallback to system
        query_title_font.setWeight(QFont.Weight.DemiBold)
        query_title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)  # Tighter spacing
        query_title.setFont(query_title_font)
        query_title.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        query_layout.addWidget(query_title, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Add spacing between title and input
        query_layout.addSpacing(20)
        
        # Input field (vertical layout)
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("")
        # Apple-style font for input
        input_font = QFont("SF Pro Text", 14)
        input_font.setWeight(QFont.Weight.Normal)
        self.query_input.setFont(input_font)
        self.query_input.setStyleSheet(
            "background-color: #E0E0E0;"
            "border-radius: 8px;"
            "padding: 8px 12px;"
            "color: #1E1E1E;"
        )
        self.query_input.setMinimumHeight(40)
        self.query_input.setObjectName("query_input")
        query_layout.addWidget(self.query_input)
        
        # Send button below input
        query_layout.addSpacing(8)
        self.send_button = GlassButton("Send", bg_color="#E0E0E0", text_color="#1E1E1E")
        # Apple-style font for button
        button_font = QFont("SF Pro Text", 14)
        button_font.setWeight(500)  # Medium weight
        self.send_button.setFont(button_font)
        self.send_button.setMinimumWidth(80)
        self.send_button.setObjectName("send_button")
        self.send_button.clicked.connect(self._on_send_clicked)
        query_layout.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Callback for when query is sent (to be set by handler)
        self._on_query_callback = None
        
        query_layout.addStretch(1)
        
        left_column.addWidget(query_card)

        # Starred Images panel
        starred_card = CardWidget(600, 678)
        starred_layout = starred_card.content_layout()
        
        starred_title = QLabel("Image / Metadata")
        # Apple-style typography: system font, tighter spacing, semibold weight
        starred_title_font = QFont("SF Pro Display", 17)
        starred_title_font.setWeight(QFont.Weight.DemiBold)
        starred_title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        starred_title.setFont(starred_title_font)
        starred_title.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        starred_layout.addWidget(starred_title, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Add spacing between title and content
        starred_layout.addSpacing(20)
        
        # Vertical layout for image box and metadata section
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        
        # Large image display widget (3/4 of the space)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.1);"
        )
        self.image_label.setScaledContents(True)
        self.image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_label.setObjectName("image_label")
        
        # Create a hardcoded placeholder image (400x300 colored gradient)
        placeholder_pixmap = QPixmap(400, 300)
        placeholder_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(placeholder_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Create a gradient background
        gradient = QLinearGradient(0, 0, 400, 300)
        gradient.setColorAt(0, QColor(100, 150, 200))
        gradient.setColorAt(0.5, QColor(150, 200, 255))
        gradient.setColorAt(1, QColor(200, 220, 255))
        painter.fillRect(placeholder_pixmap.rect(), gradient)
        
        # Add some text to indicate it's a placeholder
        painter.setPen(QColor(255, 255, 255, 180))
        font = QFont("SF Pro Display", 24)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(placeholder_pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Image Preview")
        painter.end()
        
        self.image_label.setPixmap(placeholder_pixmap)
        content_layout.addWidget(self.image_label, stretch=6)
        
        # Lighter grey metadata section box (larger size)
        metadata_box = QWidget()
        metadata_box.setStyleSheet(
            "background-color: #E0E0E0;"
        )
        metadata_layout = QVBoxLayout(metadata_box)
        metadata_layout.setContentsMargins(20, 20, 20, 20)
        metadata_layout.setSpacing(8)
        
        metadata_text_font = QFont("SF Pro Text", 12)
        
        # Create 6 metadata lines
        metadata_labels = [
            "Image:",
            "Edge Device:",
            "Query:",
            "Response:",
            "Confidence Rate:",
            "Time Processed:"
        ]
        
        # Store metadata labels for handler access
        self.metadata_labels = {}
        for label_text in metadata_labels:
            field_name = label_text.replace(":", "").replace(" ", "_").lower()
            if field_name == "response":
                # Dedicated scrollable response area
                response_title = QLabel("Response:")
                response_title.setStyleSheet("color: #000000; background-color: transparent;")
                response_title.setFont(metadata_text_font)
                metadata_layout.addWidget(response_title, alignment=Qt.AlignmentFlag.AlignLeft)

                response_box = QTextEdit()
                response_box.setReadOnly(True)
                response_box.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                response_box.setStyleSheet(
                    "color: #000000;"
                    "background-color: rgba(255, 255, 255, 0.55);"
                    "border-radius: 8px;"
                    "padding: 8px;"
                )
                response_box.setMinimumHeight(140)
                response_box.setObjectName("metadata_response")
                self.metadata_labels[field_name] = response_box
                metadata_layout.addWidget(response_box)
            else:
                label = QLabel(label_text)
                label.setStyleSheet("color: #000000; background-color: transparent;")
                label.setFont(metadata_text_font)
                label.setWordWrap(True)
                label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
                if field_name == "query":
                    label.setMinimumHeight(48)
                label.setObjectName(f"metadata_{field_name}")
                self.metadata_labels[field_name] = label
                metadata_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignLeft)
        
        metadata_layout.addStretch(1)
        
        content_layout.addWidget(metadata_box, stretch=2)
        
        starred_layout.addLayout(content_layout, stretch=1)
        
        left_column.addWidget(starred_card)
        
        main_layout.addLayout(left_column)

        # Right column - Images Returned
        self.images_card = CardWidget(800, 960)
        images_layout = self.images_card.content_layout()
        
        images_title = QLabel("Images Returned")
        # Apple-style typography: system font, tighter spacing, semibold weight
        images_title_font = QFont("SF Pro Display", 17)
        images_title_font.setWeight(QFont.Weight.DemiBold)
        images_title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        images_title.setFont(images_title_font)
        images_title.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        images_layout.addWidget(images_title, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Container for returned images
        self.returned_images_container = QWidget()
        self.returned_images_layout = QVBoxLayout(self.returned_images_container)
        self.returned_images_layout.setContentsMargins(0, 0, 0, 0)
        self.returned_images_layout.setSpacing(8)
        images_layout.addWidget(self.returned_images_container)
        
        images_layout.addStretch(1)
        
        main_layout.addWidget(self.images_card)

        # Add central content to container
        container_layout.addWidget(central)
        
        # Set main container as central widget
        self.setCentralWidget(main_container)
        
        # Initialize returned images list
        self.returned_images = []
    
    def _on_send_clicked(self):
        """Handle Send button click - triggers query request"""
        query_text = self.query_input.text().strip()
        if not query_text:
            print("[Query] No query text entered")
            return
        
        if self._on_query_callback:
            # Call the registered callback (set by handler/MQTT client)
            self._on_query_callback(query_text)
        else:
            print(f"[Query] Query sent: '{query_text}' - no callback registered")
    
    def set_query_callback(self, callback):
        """Set the callback function to be called when Send is clicked.
        
        The callback receives the query text and should send a query_request packet
        as per packetStructure.md section 2.1:
        {
            "header": {
                "timestamp": "<ISO-8601>",
                "source_device": "<host_name>",
                "message_type": "query_request"
            },
            "body": {
                "query_id": "<uuid>",
                "query": "<natural_language_query>"
            }
        }
        """
        self._on_query_callback = callback
    
    def update_metadata(self, metadata: dict):
        """Update metadata labels with new values.
        
        Args:
            metadata: Dictionary with keys matching field names:
                - image, edge_device, query, response, confidence_rate, time_processed
        """
        for field_name, value in metadata.items():
            if field_name in self.metadata_labels:
                # Get the label text prefix (e.g., "Image:" from "Image: value")
                widget = self.metadata_labels[field_name]
                if isinstance(widget, QTextEdit):
                    widget.setPlainText("" if value is None else str(value))
                    continue

                current_text = widget.text()
                if ":" in current_text:
                    prefix = current_text.split(":")[0]
                    widget.setText(f"{prefix}: {value}")
                else:
                    widget.setText(f"{field_name}: {value}")
    
    def add_returned_image(self, image_path_or_data: str, metadata: dict = None):
        """Add an image to the returned images section."""
        from PyQt6.QtCore import QByteArray
        
        # Create image label
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.1);"
            "border-radius: 8px;"
            "padding: 8px;"
        )
        image_label.setScaledContents(True)
        image_label.setFixedSize(200, 150)
        
        # Load image
        pixmap = QPixmap()
        if image_path_or_data.startswith("data:image") or len(image_path_or_data) > 100:
            # Assume base64 data
            try:
                if "," in image_path_or_data:
                    image_path_or_data = image_path_or_data.split(",")[1]
                image_bytes = base64.b64decode(image_path_or_data)
                pixmap.loadFromData(QByteArray(image_bytes))
            except:
                pass
        else:
            # File path
            pixmap = QPixmap(image_path_or_data)
        
        if not pixmap.isNull():
            image_label.setPixmap(pixmap.scaled(200, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        self.returned_images_layout.addWidget(image_label)
        self.returned_images.append({"label": image_label, "metadata": metadata or {}})
    
    def clear_returned_images(self):
        """Clear all returned images."""
        while self.returned_images_layout.count():
            child = self.returned_images_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.returned_images.clear()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()