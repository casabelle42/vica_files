from __future__ import annotations

import sys
import os
import time

# Add the parent directory to the path to import Network module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, pyqtSlot, QTimer, QMetaObject, Q_ARG
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

# Import network modules
from Network.Host_Network import DeviceDiscovery, EdgeDevice, ConnectionManager
from Network.Host_Network.image_handler import ImageHandler, ReceivedImage

# Import the new Nano-VLM client (optional - for direct communication)
# import sys
# import os
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# from nano_vlm_host_client import NanoVLMHostClient


class FitContentItemDelegate(QStyledItemDelegate):
    """Custom delegate that sizes list items to fit their content width."""
    
    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """Return size hint based on item's text width."""
        # Get the text from the model
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            # Calculate width needed for text
            font_metrics = QFontMetrics(option.font)
            text_lines = str(text).split('\n')
            max_text_width = max(font_metrics.horizontalAdvance(line) for line in text_lines)
            # Add padding: 24px (12px on each side from padding) + 4px (2px margin on each side)
            item_width = max_text_width + 28
            # Get default height from super
            default_size = super().sizeHint(option, index)
            return QSize(item_width, default_size.height())
        # Fallback to default behavior
        return super().sizeHint(option, index)


class DiscoveryThread(QThread):
    """Thread for running device discovery in the background."""
    
    devices_found = pyqtSignal(list)  # Signal emitted when devices are found
    discovery_finished = pyqtSignal()  # Signal emitted when discovery is complete
    
    def __init__(self):
        super().__init__()
        self.discovery = DeviceDiscovery()
    
    def run(self):
        """Run device discovery in background thread."""
        try:
            print("=== DiscoveryThread: Starting device discovery ===")
            devices = self.discovery.discover_devices()
            print(f"=== DiscoveryThread: Found {len(devices)} devices ===")
            for device in devices:
                print(f"=== DiscoveryThread: Device: {device.device_name} at {device.ip_address} ===")
            print("=== DiscoveryThread: Emitting devices_found signal ===")
            self.devices_found.emit(devices)
            print("=== DiscoveryThread: Signal emitted ===")
        except Exception as e:
            print(f"=== DiscoveryThread: Error: {e} ===")
        finally:
            print("=== DiscoveryThread: Emitting discovery_finished signal ===")
            self.discovery_finished.emit()


class MainWindow(QMainWindow):
    """Main application window for the Sentinel Nexus Host UI.

    This window intentionally contains only a centered title at the top.
    No functional elements or interactions are included at this stage.
    """
    
    # Signal for thread-safe UI text updates (must be class attribute)
    _update_ui_signal = pyqtSignal(str, bool)  # (text, append)

    def __init__(self) -> None:
        super().__init__()

        self.device_list_widget = None
        self.discovery_thread = None
        self.discovery_button = None
        self.disconnect_button = None
        self.connection_manager = None
        self.selected_device = None
        self.connections_title = None
        self.left_widget = None  # Store reference for resize handling
        self.start_button = None
        self.stop_query_button = None
        self.question_input = None
        self.edge_question_title = None
        self.response_display = None
        self.edge_info_display = None  # For other edge device information
        self.image_gallery = None
        self.received_images = []  # Store received images
        self.max_images = 20  # Maximum number of images to display
        
        # Model loading status tracking
        self.model_status = "unknown"  # "not_loaded", "loading", "ready", "error"
        self.model_ready = False
        self.model_loading_progress = None
        
        # Frame update tracking
        self.last_frame_number = 0
        self.frame_update_count = 0
        self.last_update_time = 0
        
        # Live feed state tracking
        self.live_feed_active = False
        self.live_feed_started = False
        
        # Data triage state tracking
        self.triage_enabled = False
        self.triage_button = None
        
        # Connect signal to update method (signal is class attribute)
        try:
            self._update_ui_signal.connect(self._direct_ui_update)
            print(f"✅ UI update signal connected successfully")
            print(f"   Signal type: {type(self._update_ui_signal)}")
            print(f"   Connected slots: {self._update_ui_signal.receivers if hasattr(self._update_ui_signal, 'receivers') else 'N/A'}")
        except Exception as e:
            print(f"❌ ERROR: Failed to connect UI update signal: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
        
        # Initialize connection manager
        self.connection_manager = ConnectionManager()
        
        # Initialize image handler
        self.image_handler = ImageHandler(self._on_image_received)
        
        # Nano-VLM results will be received through the existing network protocol
        
        self._configure_window()
        self._apply_styles()
        self._build_layout()

    def _configure_window(self) -> None:
        self.setWindowTitle("Sentinel Nexus")
        self.resize(1400, 900)  # Increased from 1040x680 to 1400x900
        self.setMinimumSize(1000, 700)  # Increased from 720x480 to 1000x700

    def _apply_styles(self) -> None:
        # Modern dark theme with subtle contrast and accessible colors
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #0f172a; /* slate-900 */
            }
            QLabel#AppTitleLabel {
                color: #e2e8f0; /* slate-200 */
                font-size: 34px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QLabel#SectionLabel {
                color: #cbd5e1; /* slate-300 */
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
                background-color: #1e293b; /* slate-800 */
                border: 1px solid #334155; /* slate-700 */
                border-radius: 6px;
                margin: 4px;
            }
            QLabel#ConnectionsTitle {
                color: #e2e8f0; /* slate-200 */
                font-size: 18px;
                font-weight: 700;
                padding: 8px 0px;
            }
            QLabel#RightTitle {
                color: #e2e8f0; /* slate-200 */
                font-size: 18px;
                font-weight: 700;
                padding: 8px 0px;
            }
            QLabel#LightBlueBox {
                background-color: #0ea5e9; /* sky-500 */
                border: 1px solid #0284c7; /* sky-600 */
                border-radius: 8px;
                padding: 20px;
                margin: 4px;
                min-height: 120px;
            }
            QPushButton#SelectDeviceButton {
                background-color: #3b82f6; /* blue-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#SelectDeviceButton:hover {
                background-color: #2563eb; /* blue-600 */
            }
            QPushButton#SelectDeviceButton:pressed {
                background-color: #1d4ed8; /* blue-700 */
            }
            QPushButton#SendButton {
                background-color: #10b981; /* emerald-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#SendButton:hover {
                background-color: #059669; /* emerald-600 */
            }
            QPushButton#SendButton:pressed {
                background-color: #047857; /* emerald-700 */
            }
            QPushButton#ExitButton {
                background-color: #ef4444; /* red-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#ExitButton:hover {
                background-color: #dc2626; /* red-600 */
            }
            QPushButton#ExitButton:pressed {
                background-color: #b91c1c; /* red-700 */
            }
            QPushButton#DiscoveryButton {
                background-color: #8b5cf6; /* violet-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#DiscoveryButton:hover {
                background-color: #7c3aed; /* violet-600 */
            }
            QPushButton#DiscoveryButton:pressed {
                background-color: #6d28d9; /* violet-700 */
            }
            QPushButton#DiscoveryButton:disabled {
                background-color: #6b7280; /* gray-500 */
                color: #9ca3af; /* gray-400 */
            }
            QPushButton#DisconnectButton {
                background-color: #dc2626; /* red-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#DisconnectButton:hover {
                background-color: #b91c1c; /* red-600 */
            }
            QPushButton#DisconnectButton:pressed {
                background-color: #991b1b; /* red-700 */
            }
            QPushButton#DisconnectButton:disabled {
                background-color: #6b7280; /* gray-500 */
                color: #9ca3af; /* gray-400 */
            }
            QPushButton#TriageButton {
                background-color: #6b7280; /* gray-500 - OFF state */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#TriageButton:hover {
                background-color: #4b5563; /* gray-600 */
            }
            QPushButton#TriageButton:pressed {
                background-color: #374151; /* gray-700 */
            }
            QPushButton#TriageButton:checked {
                background-color: #10b981; /* emerald-500 - ON state */
                color: white;
            }
            QPushButton#TriageButton:checked:hover {
                background-color: #059669; /* emerald-600 */
            }
            QPushButton#TriageButton:checked:pressed {
                background-color: #047857; /* emerald-700 */
            }
            QPushButton#ClearButton {
                background-color: #f59e0b; /* amber-500 */
                color: white;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                margin: 4px;
            }
            QPushButton#ClearButton:hover {
                background-color: #d97706; /* amber-600 */
            }
            QPushButton#ClearButton:pressed {
                background-color: #b45309; /* amber-700 */
            }
            QLineEdit#QuestionInput {
                background-color: #1e293b; /* slate-800 */
                color: #e2e8f0; /* slate-200 */
                border: 2px solid #334155; /* slate-700 */
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                margin: 4px;
            }
            QLineEdit#QuestionInput:focus {
                border-color: #3b82f6; /* blue-500 */
                background-color: #0f172a; /* slate-900 */
            }
            QLineEdit#QuestionInput::placeholder {
                color: #64748b; /* slate-500 */
            }
            QLabel#ModelStatusDisplay {
                background-color: #1e293b; /* slate-800 */
                color: #e2e8f0; /* slate-200 */
                border: 2px solid #334155; /* slate-700 */
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                font-weight: 600;
                margin: 4px;
                min-height: 40px;
            }
            QLabel#ModelStatusDisplay.model_loading {
                background-color: #1e40af; /* blue-800 */
                border-color: #3b82f6; /* blue-500 */
                color: #dbeafe; /* blue-100 */
            }
            QLabel#ModelStatusDisplay.model_ready {
                background-color: #166534; /* green-800 */
                border-color: #10b981; /* emerald-500 */
                color: #dcfce7; /* green-100 */
            }
            QLabel#ModelStatusDisplay.model_error {
                background-color: #991b1b; /* red-800 */
                border-color: #ef4444; /* red-500 */
                color: #fecaca; /* red-100 */
            }
            QLabel#ResponseDisplay {
                background-color: #1e293b; /* slate-800 */
                color: #e2e8f0; /* slate-200 */
                border: 2px solid #334155; /* slate-700 */
                border-radius: 8px;
                padding: 16px 20px;
                font-size: 14px;
                margin: 4px;
                min-height: 200px;
                max-height: 400px;
            }
            QScrollArea#ImageGallery {
                background-color: #1e293b; /* slate-800 */
                border: 2px solid #334155; /* slate-700 */
                border-radius: 8px;
                margin: 4px;
            }
            QScrollArea#ImageGallery QWidget {
                background-color: #1e293b; /* slate-800 */
            }
            QLabel#ImagePlaceholder {
                background-color: #374151; /* gray-700 */
                border: 1px solid #4b5563; /* gray-600 */
                border-radius: 4px;
                color: #9ca3af; /* gray-400 */
                font-size: 12px;
                padding: 8px;
                margin: 2px;
                min-width: 80px;
                min-height: 80px;
                max-width: 80px;
                max-height: 80px;
            }
            QListWidget#DeviceList {
                background-color: #1e293b; /* slate-800 */
                border: 2px solid #334155; /* slate-700 */
                border-radius: 8px;
                color: #e2e8f0; /* slate-200 */
                font-size: 14px;
                margin: 4px;
                padding: 8px;
            }
            QListWidget#DeviceList::item {
                background-color: #374151; /* gray-700 */
                border: 1px solid #4b5563; /* gray-600 */
                border-radius: 4px;
                padding: 8px 12px;
                margin: 2px;
                min-height: 20px;
                color: #e2e8f0; /* slate-200 */
            }
            QListWidget#DeviceList::item:selected {
                background-color: #3b82f6; /* blue-500 */
                color: white;
            }
            QListWidget#DeviceList::item:hover {
                background-color: #4b5563; /* gray-600 */
            }
            """
        )

    def _build_layout(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(32, 32, 32, 32)  # Increased margins from 24 to 32
        main_layout.setSpacing(24)  # Increased spacing from 16 to 24

        # Title row
        title_label = QLabel("SENTINEL NEXUS", self)
        title_label.setObjectName("AppTitleLabel")
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )

        # Prefer font APIs for better cross-platform rendering
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(28)  # paired with stylesheet for consistency
        title_label.setFont(title_font)

        main_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Three column layout below title
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(32)  # Increased spacing from 16 to 32

        # Left column - Connections
        left_column = QVBoxLayout()
        left_column.setSpacing(16)  # Increased spacing from 8 to 16
        
        # Connections title
        connections_title = QLabel("Connections", self)
        connections_title.setObjectName("ConnectionsTitle")
        self.connections_title = connections_title  # Store reference for updates
        
        # Device list
        device_list = self._create_device_list()
        
        # SELECT DEVICE button
        select_device_button = QPushButton("SELECT DEVICE", self)
        select_device_button.setObjectName("SelectDeviceButton")
        select_device_button.clicked.connect(self._select_device)
        
        # DISCOVERY button
        discovery_button = QPushButton("DISCOVERY", self)
        discovery_button.setObjectName("DiscoveryButton")
        discovery_button.clicked.connect(self._start_discovery)
        self.discovery_button = discovery_button  # Store reference
        
        # DISCONNECT button
        disconnect_button = QPushButton("DISCONNECT", self)
        disconnect_button.setObjectName("DisconnectButton")
        disconnect_button.clicked.connect(self._disconnect_device)
        disconnect_button.setEnabled(False)  # Initially disabled
        self.disconnect_button = disconnect_button  # Store reference
        
        left_column.addWidget(connections_title)
        left_column.addWidget(device_list)
        left_column.addWidget(select_device_button)
        left_column.addWidget(discovery_button)
        left_column.addWidget(disconnect_button)
        left_column.addStretch(1)  # Fill remaining space

        # Middle column - Query/Response
        middle_column = QVBoxLayout()
        middle_column.setSpacing(16)  # Increased spacing from 8 to 16
        
        # Section 1: Live Feed Question
        edge_question = QLabel("Live Feed Question", self)
        edge_question.setObjectName("RightTitle")
        self.edge_question_title = edge_question  # Store reference for updates
        
        # Section 2: Question input field
        question_input = QLineEdit(self)
        question_input.setObjectName("QuestionInput")
        question_input.setPlaceholderText("Enter your question here...")
        self.question_input = question_input  # Store reference
        
        # Model Status Display removed - not needed
        
        # Row 1: Query results display area - for live feed query results
        response_display = QLabel("Waiting for live feed results...\n\nEnter a question and click START to begin analysis.", self)
        response_display.setObjectName("ResponseDisplay")
        response_display.setWordWrap(True)
        response_display.setMinimumHeight(150)
        response_display.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.response_display = response_display  # Store reference for query results
        
        # Section 3: START, STOP buttons
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center the buttons
        
        # Start button - re-enabled with functionality
        start_button = QPushButton("START", self)
        start_button.setObjectName("StartButton")
        start_button.clicked.connect(self._start_query)
        start_button.setEnabled(False)  # Initially disabled until device connected
        start_button.setFixedWidth(120)
        self.start_button = start_button
        
        stop_query_button = QPushButton("STOP", self)
        stop_query_button.setObjectName("StopQueryButton")
        stop_query_button.setEnabled(False)  # Disabled
        stop_query_button.setFixedWidth(120)
        stop_query_button.clicked.connect(self._stop_query)  # Connect to stop handler
        self.stop_query_button = stop_query_button
        
        button_layout.addWidget(start_button)
        button_layout.addWidget(stop_query_button)
        
        # Row 2: Other edge device information display area
        edge_info_display = QLabel("Edge device information will appear here...", self)
        edge_info_display.setObjectName("ResponseDisplay")
        edge_info_display.setWordWrap(True)
        edge_info_display.setMinimumHeight(150)
        edge_info_display.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.edge_info_display = edge_info_display  # Store reference for other edge info
        
        # Data Triage button - below edge info display
        triage_button = QPushButton("DATA TRIAGE: OFF", self)
        triage_button.setObjectName("TriageButton")
        triage_button.clicked.connect(self._toggle_triage)
        triage_button.setCheckable(True)  # Make it a toggle button
        triage_button.setChecked(False)  # Initially unchecked (triage disabled)
        self.triage_button = triage_button  # Store reference
        
        middle_column.addWidget(edge_question)
        middle_column.addWidget(question_input)
        middle_column.addWidget(response_display)  # Row 1: Query results
        middle_column.addLayout(button_layout)    # Buttons
        middle_column.addWidget(edge_info_display)  # Row 2: Other edge device info
        middle_column.addWidget(triage_button)  # Data triage toggle button
        middle_column.addStretch(1)  # Fill remaining space
        
        # Right column - Images
        images_column = QVBoxLayout()
        images_column.setSpacing(16)  # Increased spacing from 8 to 16
        
        # Images title
        edge_images = QLabel("Live Feed Images", self)
        edge_images.setObjectName("RightTitle")
        
        # Image gallery with scroll
        self.image_gallery = self._create_image_gallery()
        
        # Exit button - moved to images column at the bottom
        exit_button = QPushButton("Exit", self)
        exit_button.setObjectName("ExitButton")
        exit_button.clicked.connect(self.close)  # Close the program when clicked
        # Button width: increased by 20% from 80px to 96px
        exit_button.setFixedWidth(150)
        
        images_column.addWidget(edge_images)
        images_column.addWidget(self.image_gallery, 1)  # Add stretch factor so gallery expands
        # No stretch here - gallery will expand above the button
        
        # Create a horizontal layout to align button to the right
        exit_button_layout = QHBoxLayout()
        exit_button_layout.addStretch(1)  # Push button to the right
        exit_button_layout.addWidget(exit_button)  # Button aligned to bottom-right
        images_column.addLayout(exit_button_layout)

        # Add columns to horizontal layout
        left_widget = QWidget()
        left_widget.setLayout(left_column)
        self.left_widget = left_widget  # Store reference for potential resize handling
        # Prevent the connections column from expanding horizontally when content changes
        # Calculate maximum width as 22% of window width (slightly more than the 18.2% stretch factor)
        # Account for margins (64px total: 32px on each side)
        available_width = self.width() - 64
        left_widget.setMaximumWidth(int(available_width * 0.22))
        
        middle_widget = QWidget()
        middle_widget.setLayout(middle_column)
        
        images_widget = QWidget()
        images_widget.setLayout(images_column)
        
        # Column proportions: 4 (Connections, reduced by 20%) : 8 (Query) : 10 (Images)
        # This gives approximately: 18.2% : 36.4% : 45.5% (connections reduced by 20% from previous 21.7%)
        columns_layout.addWidget(left_widget, 4)    # Left column takes ~18.2% (4/22) - reduced by 20%
        columns_layout.addWidget(middle_widget, 8)  # Middle column takes ~36.4% (8/22)
        columns_layout.addWidget(images_widget, 10) # Right column takes ~45.5% (10/22)

        main_layout.addLayout(columns_layout)

        central_widget.setLayout(main_layout)

    def _create_image_gallery(self) -> QScrollArea:
        """Create a scrollable image gallery with 3 columns max."""
        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("ImageGallery")
        scroll_area.setMinimumHeight(200)  # Minimum height for gallery
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Create the content widget for the gallery
        gallery_content = QWidget()
        gallery_layout = QGridLayout()
        gallery_layout.setSpacing(4)
        gallery_layout.setContentsMargins(8, 8, 8, 8)
        
        # Store references for dynamic updates
        self.gallery_content = gallery_content
        self.gallery_layout = gallery_layout
        
        # Create initial empty gallery
        self._update_image_gallery()
        
        gallery_content.setLayout(gallery_layout)
        scroll_area.setWidget(gallery_content)
        
        return scroll_area

    def _update_image_gallery(self):
        """Update the image gallery with current received images."""
        if not hasattr(self, 'gallery_layout'):
            return
        
        # Clear existing widgets
        for i in reversed(range(self.gallery_layout.count())):
            self.gallery_layout.itemAt(i).widget().setParent(None)
        
        # Always show 15 slots (3 columns × 5 rows)
        total_slots = 15
        columns = 3
        rows = 5
        
        # Add received images (up to 15 max)
        for i, image_data in enumerate(self.received_images[-total_slots:]):
            row = i // columns
            col = i % columns
            
            # Create image label
            image_label = QLabel(self)
            image_label.setObjectName("ImagePlaceholder")
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.setScaledContents(True)
            image_label.setFixedSize(80, 80)
            
            # Set image if available
            if image_data.get('pixmap'):
                image_label.setPixmap(image_data['pixmap'])
            else:
                image_label.setText(f"Img {i+1}")
            
            self.gallery_layout.addWidget(image_label, row, col)
        
        # Add placeholder for empty slots to fill all 15 slots (3 columns × 5 rows)
        num_images = min(len(self.received_images), total_slots)
        for i in range(num_images, total_slots):
            row = i // columns
            col = i % columns
            
            placeholder = QLabel("Empty", self)
            placeholder.setObjectName("ImagePlaceholder")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setFixedSize(80, 80)
            
            self.gallery_layout.addWidget(placeholder, row, col)

    def _add_received_image(self, image_data: dict):
        """Add a received image to the gallery."""
        try:
            # Add timestamp if not present
            if 'timestamp' not in image_data:
                image_data['timestamp'] = time.time()
            
            # Add to received images list
            self.received_images.append(image_data)
            
            # Keep only the most recent images
            if len(self.received_images) > self.max_images:
                self.received_images = self.received_images[-self.max_images:]
            
            # Update the gallery display
            self._update_image_gallery()
            
            print(f"✅ Added image to gallery. Total images: {len(self.received_images)}")
            
        except Exception as e:
            print(f"❌ Error adding image to gallery: {e}")

    def _on_image_received(self, received_image: ReceivedImage):
        """Callback for when an image is received from the image handler."""
        try:
            print(f"✅ Received image: {received_image.image_id} from {received_image.device_id}")
            print(f"   Size: {received_image.width}x{received_image.height}")
            print(f"   Format: {received_image.image_format}")
            print(f"   Data size: {len(received_image.image_bytes)} bytes")
            
            # Convert image bytes to QImage (handle JPEG from edge device)
            if received_image.image_format == 'JPEG':
                # Edge device sends JPEG bytes - load directly
                qimage = QImage.fromData(received_image.image_bytes)
                print(f"   Loading JPEG image from {len(received_image.image_bytes)} bytes")
            elif received_image.image_format == 'RGB':
                qimage = QImage(received_image.image_bytes, received_image.width, received_image.height, QImage.Format.Format_RGB888)
            elif received_image.image_format == 'RGBA':
                qimage = QImage(received_image.image_bytes, received_image.width, received_image.height, QImage.Format.Format_RGBA8888)
            else:
                # Try to load from bytes directly (fallback)
                qimage = QImage.fromData(received_image.image_bytes)
            
            if not qimage.isNull():
                # Convert to QPixmap for display
                pixmap = QPixmap.fromImage(qimage)
                
                # Create image data for storage
                image_info = {
                    'pixmap': pixmap,
                    'timestamp': received_image.timestamp,
                    'width': received_image.width,
                    'height': received_image.height,
                    'format': received_image.image_format,
                    'image_id': received_image.image_id,
                    'device_id': received_image.device_id
                }
                
                # Add to gallery
                self._add_received_image(image_info)
                
                print(f"✅ Image {received_image.image_id} added to gallery")
            else:
                print(f"❌ Failed to create QImage from received image {received_image.image_id}")
                self._display_response(f"Failed to process image {received_image.image_id}")
                
        except Exception as e:
            print(f"❌ Error processing received image: {e}")
            self._display_response(f"Error processing image: {e}")

    def _create_device_list(self) -> QListWidget:
        """Create a list of available edge devices for connection."""
        device_list = QListWidget(self)
        device_list.setObjectName("DeviceList")
        self.device_list_widget = device_list  # Store reference for discovery updates
        
        # Set custom delegate to size items based on content width
        device_list.setItemDelegate(FitContentItemDelegate(device_list))
        
        # Set minimum height to ensure content is visible
        device_list.setMinimumHeight(150)  # Increased from 120 to 150
        
        # Add initial message
        initial_item = QListWidgetItem("Click DISCOVERY to find devices")
        initial_item.setFlags(initial_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        device_list.addItem(initial_item)
        
        # Auto-adjust height based on number of items (max 8 visible)
        self._update_device_list_height()
        
        # Enable single selection
        device_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        return device_list

    def _update_device_list_height(self):
        """Update device list height based on number of items."""
        if not self.device_list_widget:
            return
            
        item_count = self.device_list_widget.count()
        max_visible_items = 8
        item_height = 40  # Increased height per item for better visibility
        
        if item_count <= max_visible_items:
            # Auto-adjust to fit all items
            calculated_height = max(150, item_count * item_height + 30)  # Increased minimum from 120 to 150
            self.device_list_widget.setFixedHeight(calculated_height)
        else:
            # Fixed height for 8 items with scroll bar
            self.device_list_widget.setFixedHeight(max_visible_items * item_height + 30)  # Increased padding from 20 to 30
            self.device_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def _start_discovery(self):
        """Start device discovery in background thread."""
        if self.discovery_thread and self.discovery_thread.isRunning():
            print("Discovery already in progress...")
            return
        
        print("Starting device discovery...")
        
        # Update button state
        if self.discovery_button:
            self.discovery_button.setEnabled(False)
        
        self.discovery_thread = DiscoveryThread()
        print("=== Connecting signals ===")
        self.discovery_thread.devices_found.connect(self._on_devices_found)
        self.discovery_thread.discovery_finished.connect(self._on_discovery_finished)
        print("=== Signals connected, starting thread ===")
        self.discovery_thread.start()
        print("=== Thread started ===")

    def _on_devices_found(self, devices):
        """Handle discovered devices."""
        print(f"=== _on_devices_found called with {len(devices)} devices ===")
        print(f"Found {len(devices)} devices:")
        
        # Clear existing items
        self.device_list_widget.clear()
        print("Device list cleared")
        
        if devices:
            # Add discovered devices
            for device in devices:
                # Format device text with model status
                model_status_icon = "✅" if device.model_ready else "⏳" if device.model_status == "loading" else "❌" if device.model_status == "error" else "⭕"
                device_text = f"{device.device_name} {model_status_icon}\n{device.device_id} - {device.ip_address}\nModel: {device.model_status}"
                item = QListWidgetItem(device_text)
                # Store device info in the item for later use
                item.setData(Qt.ItemDataRole.UserRole, device)
                
                # Calculate width needed for text (use longest line)
                font = self.device_list_widget.font()
                font_metrics = QFontMetrics(font)
                text_lines = device_text.split('\n')
                max_text_width = max(font_metrics.horizontalAdvance(line) for line in text_lines)
                # Add padding: 24px (12px on each side from padding) + 4px (2px margin on each side)
                item_width = max_text_width + 28
                # Set size hint to match text width
                item.setSizeHint(QSize(item_width, item.sizeHint().height()))
                
                self.device_list_widget.addItem(item)
                print(f"  - {device.device_name} at {device.ip_address} (Model: {device.model_status}, Ready: {device.model_ready})")
            
            # Update Connections title to show available devices
            if len(devices) == 1:
                self.connections_title.setText(f"Available: {devices[0].device_name}")
            else:
                self.connections_title.setText(f"Available: {len(devices)} devices")
        else:
            # No devices found, show message
            no_devices_item = QListWidgetItem("No devices found on network")
            no_devices_item.setFlags(no_devices_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.device_list_widget.addItem(no_devices_item)
            print("  - No devices found")
            
            # Reset Connections title
            self.connections_title.setText("Connections")
        
        # Update height
        self._update_device_list_height()

    def _on_discovery_finished(self):
        """Handle discovery completion."""
        print("=== _on_discovery_finished called ===")
        print("Device discovery completed")
        
        # Update button state
        if self.discovery_button:
            self.discovery_button.setEnabled(True)
        
        if self.discovery_thread:
            self.discovery_thread.deleteLater()
            self.discovery_thread = None

    def _select_device(self):
        """Handle device selection and connection."""
        if not self.device_list_widget:
            print("Device list not available")
            return
        
        current_item = self.device_list_widget.currentItem()
        if not current_item:
            print("No device selected - please select a device from the list first")
            return
        
        # Get device data from the item
        device = current_item.data(Qt.ItemDataRole.UserRole)
        if not device:
            print("No device data available - please select a valid device")
            return
        
        print(f"Connecting to device: {device.device_name} at {device.ip_address}")
        
        # Update Connections title to show connecting status
        self.connections_title.setText(f"Connecting to {device.device_name}...")
        
        try:
            # Add device to connection manager
            connection = self.connection_manager.add_device(
                device.device_id, 
                device.ip_address, 
                device.port
            )
            
            # Attempt to connect
            success = self.connection_manager.connect_device(device.device_id)
            print(f"Debug: Connection attempt result: {success}")
            
            if success:
                self.selected_device = device
                print(f"✅ Connected to {device.device_name}")
                
                # Update model status display based on device status
                self._update_model_status(device.model_status)
                self._update_model_ready_status(device.model_ready)
                
                # Check connection status immediately
                connected_devices = self.connection_manager.get_connected_devices()
                print(f"Debug: Immediately after connection - connected devices: {connected_devices}")
                
                # Update device list to show connection status
                self._update_device_connection_status(device.device_id, "Connected")
                
                # Update Connections title to show connected device
                self._update_connections_title(device.device_name)
                
                # Enable disconnect button
                if self.disconnect_button:
                    self.disconnect_button.setEnabled(True)
                
                # Enable query functionality
                self._enable_query_functionality()
                
                # Register response handlers
                self._register_response_handlers()
            else:
                print(f"❌ Failed to connect to {device.device_name}")
                self._update_device_connection_status(device.device_id, "Connection Failed")
                # Reset connections title on failure
                self._reset_connections_title()
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            # Reset connections title on error
            self._reset_connections_title()
    
    def _update_device_connection_status(self, device_id: str, status: str):
        """Update the device list to show connection status."""
        if not self.device_list_widget:
            return
        
        for i in range(self.device_list_widget.count()):
            item = self.device_list_widget.item(i)
            device = item.data(Qt.ItemDataRole.UserRole)
            if device and device.device_id == device_id:
                # Update the display text with new formatting
                status_text = f"{device.device_name} [{status}]\n{device.device_id} - {device.ip_address}"
                item.setText(status_text)
                
                # Recalculate and update item width to match new text
                font = self.device_list_widget.font()
                font_metrics = QFontMetrics(font)
                text_lines = status_text.split('\n')
                max_text_width = max(font_metrics.horizontalAdvance(line) for line in text_lines)
                item_width = max_text_width + 28  # Add padding
                item.setSizeHint(QSize(item_width, item.sizeHint().height()))
                break
    
    def _update_connections_title(self, device_name: str):
        """Update the Connections title to show connected device."""
        if self.connections_title:
            self.connections_title.setText(f"Connected: {device_name}")
            print(f"Connections updated to show: {device_name}")
        
        # Also update the Live Feed Question title
        if self.edge_question_title:
            self.edge_question_title.setText(f"{device_name} Live Feed Question")
            print(f"Question title updated to: {device_name} Live Feed Question")
    
    def _reset_connections_title(self):
        """Reset the Connections title to default."""
        if self.connections_title:
            self.connections_title.setText("Connections")
            print("Connections title reset to default")
        
        # Also reset the Live Feed Question title
        if self.edge_question_title:
            self.edge_question_title.setText("Live Feed Question")
            print("Question title reset to default")
    
    def _reset_device_list(self):
        """Reset the device list to its original state."""
        if not self.device_list_widget:
            return
        
        # Clear all items and selection
        self.device_list_widget.clear()
        self.device_list_widget.clearSelection()
        
        # Add the original message
        initial_item = QListWidgetItem("Click DISCOVERY to find devices")
        initial_item.setFlags(initial_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.device_list_widget.addItem(initial_item)
        
        # Update height
        self._update_device_list_height()
        
        print("Device list reset to original state - cleared all devices and selection")
    
    def _disconnect_device(self):
        """Disconnect from the currently connected device."""
        if not self.selected_device:
            print("No device connected to disconnect")
            return
        
        try:
            print(f"Disconnecting from {self.selected_device.device_name}")
            
            # Disconnect from the device
            self.connection_manager.disconnect_device(self.selected_device.device_id)
            
            # Reset device list to original state FIRST
            self._reset_device_list()
            
            # Reset connections title
            self._reset_connections_title()
            
            # Disable disconnect button
            if self.disconnect_button:
                self.disconnect_button.setEnabled(False)
            
            # Disable query buttons
            if self.start_button:
                self.start_button.setEnabled(False)
            if self.stop_query_button:
                self.stop_query_button.setEnabled(False)
            
            # Clear selected device
            self.selected_device = None
            
            print("✅ Disconnected from device")
            
        except Exception as e:
            print(f"❌ Disconnect error: {e}")
    
    def _enable_query_functionality(self):
        """Enable query functionality when device is connected."""
        print("Query functionality enabled - ready to send queries to edge device")
        
        # Enable START button
        if self.start_button:
            self.start_button.setEnabled(True)
        
        # Start connection monitoring
        self._start_connection_monitoring()
    
    def _register_response_handlers(self):
        """Register response handlers for the connected device."""
        if not self.selected_device:
            return
        
        def handle_query_response(message):
            """Handle query response from edge device (including Nano-VLM results)."""
            try:
                response_data = message.data
                response_text = response_data.get('response_text', 'No response text')
                confidence = response_data.get('confidence', 0.0)
                processing_time = response_data.get('processing_time', 0.0)
                frame_count = response_data.get('frame_count', 0)
                
                # Format the response for display with Nano-VLM specific information
                formatted_response = f"""Nano-VLM Analysis Result:
                
Response: {response_text}

Confidence: {confidence:.2f}
Processing Time: {processing_time:.2f}s
Frame Count: {frame_count}"""
                
                # Update the response display
                self._display_response(formatted_response)
                
                # Re-enable START button, disable STOP button
                if self.start_button:
                    self.start_button.setEnabled(True)
                if self.stop_query_button:
                    self.stop_query_button.setEnabled(False)
                
                print(f"✅ Received Nano-VLM response: {response_text}")
                print(f"   Confidence: {confidence:.2f}, Processing Time: {processing_time:.2f}s")
                
            except Exception as e:
                print(f"❌ Error handling response: {e}")
                self._display_response(f"Error processing response: {e}")
        
        def handle_live_feed_result(message):
            """Handle live feed results from edge device."""
            print(f"🚨🚨🚨 LIVE FEED RESULT HANDLER CALLED 🚨🚨🚨")
            print(f"   Handler function executed!")
            
            try:
                print(f"   Message type: {message.message_type}")
                print(f"   Message data type: {type(message.data)}")
                print(f"   Message data keys: {list(message.data.keys()) if message.data and isinstance(message.data, dict) else 'No data or not dict'}")
                print(f"   Full message data: {message.data}")
                
                if not message.data:
                    print(f"❌ ERROR: message.data is None or empty!")
                    return
                
                if not isinstance(message.data, dict):
                    print(f"❌ ERROR: message.data is not a dict, it's {type(message.data)}")
                    return
                
                message_data = message.data
                
                # Extract all required fields according to specification
                analysis = message_data.get('analysis', 'No analysis available')
                confidence = message_data.get('confidence', 0.0)
                processing_time = message_data.get('processing_time', 0.0)
                frame_number = message_data.get('frame_number', 0)
                query_text = message_data.get('query_text', 'Unknown query')
                timestamp = message_data.get('timestamp', 0.0)
                model_version = message_data.get('model_version', 'Unknown')
                inference_device = message_data.get('inference_device', 'Unknown')
                
                # Extract frame metadata
                frame_metadata = message_data.get('frame_metadata', {})
                resolution = frame_metadata.get('resolution', 'Unknown')
                fps = frame_metadata.get('fps', 0)
                compression = frame_metadata.get('compression', 'Unknown')
                quality = frame_metadata.get('quality', 0)
                
                print(f"   Extracted - Analysis: '{analysis}', Confidence: {confidence}, Frame: {frame_number}")
                print(f"   Model: {model_version} on {inference_device}")
                print(f"   Resolution: {resolution} @ {fps}fps")
                
                # Track ALL message updates (not just frame increments)
                import time
                current_time = time.time()
                self.frame_update_count += 1  # Count every message received
                
                # Track frame progression separately
                if frame_number > self.last_frame_number:
                    time_since_last = current_time - self.last_update_time if self.last_update_time > 0 else 0
                    self.last_frame_number = frame_number
                    print(f"📊 Frame #{frame_number} (new frame) - Time since last: {time_since_last:.2f}s")
                else:
                    print(f"📊 Frame #{frame_number} (repeat or earlier frame)")
                
                self.last_update_time = current_time
                
                # Format the live feed result for display according to EDGE_TO_HOST_JSON_SPECIFICATION_OUT.md
                # Split into two displays: query results and other edge device info
                
                # Format timestamp as readable date/time
                from datetime import datetime
                try:
                    timestamp_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp_str = f"{timestamp:.2f}"
                
                # Row 1: Query results (query text, analysis, confidence, processing time)
                query_results = f"""🎥 LIVE FEED RESULT - Frame #{frame_number}

📝 Query: {query_text}

🤖 Analysis: {analysis}

📊 Confidence: {confidence:.2f}
⏱️ Processing Time: {processing_time:.2f}s
"""
                
                # Row 2: Other edge device information (model info, frame metadata, timestamp, status)
                edge_info = f"""🖥️ Model Information:
   • Version: {model_version}
   • Device: {inference_device}

📐 Frame Metadata:
   • Resolution: {resolution}
   • FPS: {fps}
   • Compression: {compression}
   • Quality: {quality}

📅 Timestamp: {timestamp_str}
🔄 Continuous Updates: Active (updating every frame)
"""
                
                # Update the response displays - REPLACE old information (continuous refresh)
                print(f"📤 Updating UI with live feed result - Frame #{frame_number}")
                print(f"   Analysis: {analysis[:50]}...")
                print(f"   Query results length: {len(query_results)} chars")
                print(f"   Edge info length: {len(edge_info)} chars")
                print(f"   response_display widget exists: {self.response_display is not None}")
                print(f"   edge_info_display widget exists: {self.edge_info_display is not None}")
                
                # Update UI - query results to response_display
                print(f"🔄 Calling _display_response for query results...")
                self._display_response(query_results, append=False)
                
                # Update UI - other edge info to edge_info_display
                print(f"🔄 Calling _display_edge_info...")
                self._display_edge_info(edge_info, append=False)
                
                print(f"✅ Update call completed for Frame #{frame_number}")
                print(f"   Analysis: {analysis[:100]}...")
                print(f"   Confidence: {confidence:.2f}")
                
            except Exception as e:
                print(f"❌ Error handling live feed result: {e}")
                self._display_response(f"Error processing live feed result: {e}")
        
        def handle_live_feed_started(message):
            """Handle live feed started confirmation."""
            try:
                message_data = message.data
                query_text = message_data.get('query_text', 'Unknown query')
                streaming = message_data.get('streaming', True)
                
                # Set live feed as active
                self.live_feed_active = True
                self.live_feed_started = True
                
                print(f"✅ Live feed started - Query: {query_text}")
                print(f"   Live feed state set: active={self.live_feed_active}, started={self.live_feed_started}")
                print(f"   Streaming: {streaming}")
                print(f"   Waiting for first analysis result...")
                
                # Show initial status that we're waiting for results
                initial_message = f"""🎥 Live Feed Started

📝 Query: {query_text}
🔄 Streaming: {'Active' if streaming else 'Inactive'}

⏳ Waiting for first analysis result from edge device...
"""
                self._display_response(initial_message)
                
            except Exception as e:
                print(f"❌ Error handling live feed started: {e}")
                self._display_response(f"Error processing live feed started: {e}")
        
        def handle_welcome(message):
            """Handle welcome message from edge device."""
            try:
                message_data = message.data
                device_name = message_data.get('device_name', 'Unknown Device')
                capabilities = message_data.get('capabilities', [])
                
                formatted_response = f"""🎉 WELCOME FROM {device_name}
🔧 Capabilities: {', '.join(capabilities)}
✅ Connected to live feed system
Ready to start live feed analysis..."""
                
                self._display_response(formatted_response)
                print(f"✅ Welcome from {device_name}")
                print(f"   Capabilities: {capabilities}")
                
            except Exception as e:
                print(f"❌ Error handling welcome message: {e}")
                self._display_response(f"Error processing welcome message: {e}")
        
        def handle_live_feed_stopped(message):
            """Handle live feed stopped confirmation."""
            try:
                message_data = message.data
                reason = message_data.get('reason', 'unknown')
                total_frames_processed = message_data.get('total_frames_processed', 0)
                total_analysis_time = message_data.get('total_analysis_time', 0.0)
                average_processing_time = message_data.get('average_processing_time', 0.0)
                successful_analyses = message_data.get('successful_analyses', 0)
                failed_analyses = message_data.get('failed_analyses', 0)
                
                # Extract final statistics
                final_statistics = message_data.get('final_statistics', {})
                total_runtime = final_statistics.get('total_runtime', 0.0)
                frames_per_second = final_statistics.get('frames_per_second', 0.0)
                average_confidence = final_statistics.get('average_confidence', 0.0)
                peak_memory_usage = final_statistics.get('peak_memory_usage', 0.0)
                peak_gpu_usage = final_statistics.get('peak_gpu_usage', 0.0)
                
                print(f"✅ Live feed stopped - Reason: {reason}")
                print(f"   Frames processed: {total_frames_processed}")
                print(f"   Analysis time: {total_analysis_time:.2f}s")
                print(f"   Success rate: {successful_analyses}/{total_frames_processed}")
                
                # Reset live feed state
                self.live_feed_active = False
                self.live_feed_started = False
                
                formatted_response = f"""🛑 LIVE FEED STOPPED
📝 Reason: {reason}
📊 Statistics:
   • Frames Processed: {total_frames_processed}
   • Total Runtime: {total_runtime:.2f}s
   • Average Processing Time: {average_processing_time:.2f}s
   • Frames per Second: {frames_per_second:.2f}
   • Successful Analyses: {successful_analyses}
   • Failed Analyses: {failed_analyses}
   • Average Confidence: {average_confidence:.2f}
   • Peak Memory Usage: {peak_memory_usage:.1f}GB
   • Peak GPU Usage: {peak_gpu_usage:.1f}%
✅ Processing stopped successfully
Ready for new queries..."""
                
                self._display_response(formatted_response)
                
                # Reset UI state
                if self.start_button:
                    self.start_button.setEnabled(True)
                if self.stop_query_button:
                    self.stop_query_button.setEnabled(False)
                
            except Exception as e:
                print(f"❌ Error handling live feed stopped: {e}")
                self._display_response(f"Error processing stop confirmation: {e}")
        
        def handle_heartbeat_response(message):
            """Handle heartbeat response from edge device."""
            try:
                message_data = message.data
                status = message_data.get('status', 'unknown')
                device_id = message_data.get('device_id', 'unknown')
                uptime = message_data.get('uptime', 0.0)
                active_connections = message_data.get('active_connections', 0)
                live_feed_active = message_data.get('live_feed_active', False)
                
                # Extract system health information
                system_health = message_data.get('system_health', {})
                overall_status = system_health.get('overall_status', 'unknown')
                gpu_status = system_health.get('gpu_status', 'unknown')
                memory_status = system_health.get('memory_status', 'unknown')
                temperature_status = system_health.get('temperature_status', 'unknown')
                
                print(f"💓 Heartbeat response - Status: {status}, Live Feed: {live_feed_active}, Clients: {active_connections}")
                print(f"   Uptime: {uptime:.1f}s, Overall Health: {overall_status}")
                print(f"   GPU: {gpu_status}, Memory: {memory_status}, Temperature: {temperature_status}")
                
            except Exception as e:
                print(f"❌ Error handling heartbeat response: {e}")
        
        def handle_live_feed_error(message):
            """Handle live feed error messages."""
            try:
                message_data = message.data
                error_type = message_data.get('error_type', 'unknown')
                error_message = message_data.get('error_message', 'Unknown error')
                frame_number = message_data.get('frame_number', 0)
                error_code = message_data.get('error_code', 'UNKNOWN_ERROR')
                
                # Extract error details
                error_details = message_data.get('error_details', {})
                available_memory = error_details.get('available_memory', 0.0)
                required_memory = error_details.get('required_memory', 0.0)
                suggestion = error_details.get('suggestion', 'No suggestion available')
                
                recovery_attempted = message_data.get('recovery_attempted', False)
                recovery_successful = message_data.get('recovery_successful', False)
                
                print(f"❌ Live feed error - Type: {error_type}, Code: {error_code}")
                print(f"   Frame: {frame_number}, Message: {error_message}")
                print(f"   Recovery attempted: {recovery_attempted}, Successful: {recovery_successful}")
                
                formatted_response = f"""❌ LIVE FEED ERROR - Frame #{frame_number}
🚨 Error Type: {error_type}
📝 Message: {error_message}
🔢 Error Code: {error_code}
⚠️ Processing may be affected"""
                
                # Add error details if available
                if error_details:
                    formatted_response += f"""
📊 Error Details:
   • Available Memory: {available_memory:.1f}GB
   • Required Memory: {required_memory:.1f}GB
   • Suggestion: {suggestion}"""
                
                # Add recovery information
                if recovery_attempted:
                    recovery_status = "✅ Successful" if recovery_successful else "❌ Failed"
                    formatted_response += f"""
🔄 Recovery: {recovery_status}"""
                
                self._display_response(formatted_response)
                
            except Exception as e:
                print(f"❌ Error handling live feed error: {e}")
                self._display_response(f"Error processing error message: {e}")
        
        def handle_status_update(message):
            """Handle status update messages - simplified to avoid UI conflicts."""
            try:
                message_data = message.data
                status_type = message_data.get('status_type', 'unknown')
                status_message = message_data.get('message', 'No message')
                
                print(f"📊 Status update received: {status_type} - {status_message}")
                
                # Only handle critical status updates that affect the UI
                if status_type == 'model_error':
                    # Only show errors in the UI
                    self._update_model_status("error", status_message)
                    formatted_response = f"""❌ MODEL ERROR
📝 Status: {status_message}
⚠️ Model loading failed - please check edge device"""
                    self._display_response(formatted_response)
                else:
                    # Log all other status updates but don't update the UI
                    print(f"📊 Status update logged (not updating UI): {status_type} - {status_message}")
                
            except Exception as e:
                print(f"❌ Error handling status update: {e}")
                # Don't show status update errors in UI to avoid conflicts
        
        def handle_discovery_response(message):
            """Handle discovery response from edge device."""
            try:
                message_data = message.data
                device_name = message_data.get('device_name', 'Unknown Device')
                device_id = message_data.get('device_id', 'unknown')
                device_type = message_data.get('device_type', 'unknown')
                capabilities = message_data.get('capabilities', [])
                model_status = message_data.get('model_status', 'unknown')
                model_ready = message_data.get('model_ready', False)
                model_loading = message_data.get('model_loading', False)
                camera_available = message_data.get('camera_available', False)
                max_resolution = message_data.get('max_resolution', 'Unknown')
                supported_formats = message_data.get('supported_formats', [])
                processing_fps = message_data.get('processing_fps', 0)
                memory_usage = message_data.get('memory_usage', 'Unknown')
                model_auto_load = message_data.get('model_auto_load', False)
                
                print(f"✅ Discovery response from {device_name} ({device_id})")
                print(f"   Device Type: {device_type}")
                print(f"   Capabilities: {capabilities}")
                print(f"   Model Status: {model_status}, Ready: {model_ready}, Loading: {model_loading}")
                print(f"   Camera: {camera_available}, Resolution: {max_resolution}")
                print(f"   Formats: {supported_formats}, FPS: {processing_fps}")
                
                # Update model status if available
                if model_status != 'unknown':
                    self._update_model_status(model_status)
                if model_ready:
                    self._update_model_ready_status(True)
                
            except Exception as e:
                print(f"❌ Error handling discovery response: {e}")
                self._display_response(f"Error processing discovery response: {e}")
        
        def handle_connect_response(message):
            """Handle connect response from edge device."""
            try:
                message_data = message.data
                status = message_data.get('status', 'unknown')
                device_id = message_data.get('device_id', 'unknown')
                model_status = message_data.get('model_status', 'unknown')
                capabilities = message_data.get('capabilities', [])
                
                print(f"✅ Connect response from {device_id}")
                print(f"   Status: {status}")
                print(f"   Model Status: {model_status}")
                print(f"   Capabilities: {capabilities}")
                
                if status == 'connected':
                    # Update model status if available
                    if model_status != 'unknown':
                        self._update_model_status(model_status)
                    
                    formatted_response = f"""✅ CONNECTION ESTABLISHED
📱 Device: {device_id}
📊 Model Status: {model_status}
🔧 Capabilities: {', '.join(capabilities)}
🚀 Ready for live feed analysis!"""
                    self._display_response(formatted_response)
                else:
                    formatted_response = f"""❌ CONNECTION FAILED
📱 Device: {device_id}
📊 Status: {status}
⚠️ Unable to establish connection"""
                    self._display_response(formatted_response)
                
            except Exception as e:
                print(f"❌ Error handling connect response: {e}")
                self._display_response(f"Error processing connect response: {e}")
        
        def handle_error_response(message):
            """Handle error response from edge device."""
            try:
                error_data = message.data
                error_code = error_data.get('error_code', 'unknown_error')
                error_message = error_data.get('error_message', 'Unknown error')
                
                # Display error message
                self._display_response(f"Error from edge device: {error_message}")
                
                # Re-enable START button, disable STOP button
                if self.start_button:
                    self.start_button.setEnabled(True)
                if self.stop_query_button:
                    self.stop_query_button.setEnabled(False)
                
                print(f"❌ Error from edge device: {error_message}")
                
            except Exception as e:
                print(f"❌ Error handling error response: {e}")
                self._display_response(f"Error processing error response: {e}")
        
        def handle_image_message(message):
            """Handle image message from edge device using dedicated image handler."""
            try:
                print(f"📸 Processing image message: {message.message_type}")
                print(f"   Message data keys: {list(message.data.keys()) if message.data else 'No data'}")
                
                # Use the dedicated image handler to process the message
                received_image = self.image_handler.handle_image_message(message)
                
                if received_image:
                    print(f"✅ Image message processed by ImageHandler: {received_image.image_id}")
                    print(f"   Image size: {received_image.width}x{received_image.height}")
                    print(f"   Image format: {received_image.image_format}")
                    print(f"   Data size: {len(received_image.image_bytes)} bytes")
                else:
                    print("❌ ImageHandler failed to process image message")
                    self._display_response("Failed to process image message")
                    
            except Exception as e:
                print(f"❌ Error in image message handler: {e}")
                import traceback
                print(f"   Traceback: {traceback.format_exc()}")
                self._display_response(f"Error processing image message: {e}")
        
        # Register handlers with the connection manager
        self.connection_manager.register_response_handler(
            self.selected_device.device_id, 
            handle_query_response
        )
        self.connection_manager.register_error_handler(
            self.selected_device.device_id, 
            handle_error_response
        )
        
        # Register live feed message handlers
        print(f"🔧 Registering live_feed_result handler for device: {self.selected_device.device_id}")
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "live_feed_result",
            handle_live_feed_result
        )
        # Verify handler was registered
        if self.selected_device.device_id in self.connection_manager.connections:
            client = self.connection_manager.connections[self.selected_device.device_id].client
            if "live_feed_result" in client.message_handlers:
                print(f"✅ CONFIRMED: live_feed_result handler registered successfully")
            else:
                print(f"❌ ERROR: live_feed_result handler NOT registered!")
        else:
            print(f"❌ ERROR: Device connection not found!")
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "live_feed_started",
            handle_live_feed_started
        )
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "welcome",
            handle_welcome
        )
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "live_feed_stopped",
            handle_live_feed_stopped
        )
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "heartbeat_response",
            handle_heartbeat_response
        )
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "live_feed_error",
            handle_live_feed_error
        )
        
        # Register image handler
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "image_data",
            handle_image_message
        )
        
        # Register status update handler
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "status_update",
            handle_status_update
        )
        
        # Register discovery response handler
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "discovery_response",
            handle_discovery_response
        )
        
        # Register connect response handler
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "connect_response",
            handle_connect_response
        )
        
        def handle_stop_response(message):
            """Handle stop response from edge device."""
            try:
                message_data = message.data
                status = message_data.get('status', 'unknown')
                message_text = message_data.get('message', 'Stop command acknowledged')
                
                print(f"✅ Stop response received - Status: {status}")
                print(f"   Message: {message_text}")
                
                # Reset live feed state
                self.live_feed_active = False
                self.live_feed_started = False
                
                # Reset frame tracking
                self.last_frame_number = 0
                self.frame_update_count = 0
                self.last_update_time = 0
                
                # Update UI state - re-enable START, keep STOP disabled
                if self.start_button:
                    self.start_button.setEnabled(True)
                if self.stop_query_button:
                    self.stop_query_button.setEnabled(False)
                
                # Display confirmation message
                formatted_response = f"""🛑 STOP CONFIRMED

✅ Edge device has stopped processing
📝 Status: {status}
💬 {message_text}

🔄 Ready for new queries - enter a question and click START"""
                
                self._display_response(formatted_response)
                
                # Reset the bottom edge device information field
                if self.edge_info_display:
                    self.edge_info_display.setText("Edge device information will appear here...")
                    self.edge_info_display.repaint()
                    self.edge_info_display.update()
                
                print(f"✅ UI updated - ready for new queries")
                
            except Exception as e:
                print(f"❌ Error handling stop response: {e}")
                import traceback
                print(f"   Traceback: {traceback.format_exc()}")
                self._display_response(f"Stop confirmed, but error processing response: {e}")
        
        # Register stop response handler
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "stop_response",
            handle_stop_response
        )
        
        print(f"Response handlers registered for device {self.selected_device.device_name}")
        
        # Add a test message handler to verify message reception
        def handle_test_message(message):
            """Test handler to verify any message reception."""
            print(f"🔍 TEST HANDLER: Received message type: {message.message_type}")
            print(f"   Data keys: {list(message.data.keys()) if message.data else 'No data'}")
        
        # Register test handler for debugging
        self.connection_manager.register_message_handler(
            self.selected_device.device_id,
            "test_message",
            handle_test_message
        )
        
        # Debug: Log all registered handlers
        print(f"🔍 DEBUG: Registered handlers for {self.selected_device.device_id}:")
        print(f"   Available message types: {list(self.connection_manager.connections[self.selected_device.device_id].client.message_handlers.keys())}")
        
        # Add a comprehensive debug handler to catch ALL incoming messages
        def debug_all_messages(message):
            """Debug handler to log ALL incoming messages."""
            print(f"🔍 ALL MESSAGES DEBUG:")
            print(f"   Message Type: '{message.message_type}'")
            print(f"   Message ID: {message.message_id}")
            print(f"   Device ID: {message.device_id}")
            print(f"   Timestamp: {message.timestamp}")
            print(f"   Data Keys: {list(message.data.keys()) if message.data else 'No data'}")
            print(f"   Full Data: {message.data}")
            client = self.connection_manager.connections[self.selected_device.device_id].client
            handler_available = message.message_type in client.message_handlers
            print(f"   Handler Available: {'YES' if handler_available else 'NO'}")
            if not handler_available:
                print(f"   ⚠️ WARNING: No handler for '{message.message_type}'!")
                print(f"   Available handlers: {list(client.message_handlers.keys())}")
            if message.message_type == "live_feed_result":
                print(f"   🎯 LIVE_FEED_RESULT DETECTED - This should trigger UI updates!")
            print("-" * 60)
        
        # Register debug handler for common message types that might be missed
        debug_message_types = [
            "live_feed_result", "status_update", "live_feed_started", 
            "live_feed_stopped", "live_feed_error", "discovery_response",
            "connect_response", "heartbeat_response", "image_data", "welcome",
            "stop_response"  # Added stop_response to debug handlers
        ]
        
        for msg_type in debug_message_types:
            # Store original handler (capture by value in lambda)
            original_handler = self.connection_manager.connections[self.selected_device.device_id].client.message_handlers.get(msg_type)
            
            # Create wrapper that calls both debug and original handler
            # Use lambda with proper value capture (closure fix)
            def make_wrapper(orig_handler, msg_typ):
                def wrapper(message):
                    debug_all_messages(message)
                    if orig_handler:
                        orig_handler(message)
                return wrapper
            
            # Create wrapper with captured values
            wrapper_handler = make_wrapper(original_handler, msg_type)
            self.connection_manager.register_message_handler(
                self.selected_device.device_id,
                msg_type,
                wrapper_handler
            )
            print(f"🔧 Registered debug wrapper for: {msg_type} (original handler: {original_handler is not None})")
    
    def _start_connection_monitoring(self):
        """Start monitoring the connection status."""
        if not self.selected_device:
            return
        
        # Check connection status periodically
        import threading
        def monitor_connection():
            while self.selected_device and self.connection_manager:
                try:
                    # Check if device is still connected
                    connected_devices = self.connection_manager.get_connected_devices()
                    print(f"Debug: Connected devices: {connected_devices}")
                    print(f"Debug: Selected device ID: {self.selected_device.device_id}")
                    
                    if self.selected_device.device_id not in connected_devices:
                        print(f"⚠️ Connection lost to {self.selected_device.device_name}")
                        # Update UI to show disconnection
                        self._handle_connection_lost()
                        break
                    else:
                        print(f"✅ Connection to {self.selected_device.device_name} is stable")
                    
                    time.sleep(5)  # Check every 5 seconds
                except Exception as e:
                    print(f"Connection monitoring error: {e}")
                    break
        
        monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
        monitor_thread.start()
    
    def _handle_connection_lost(self):
        """Handle when connection is lost."""
        if self.selected_device:
            # Update device status
            self._update_device_connection_status(self.selected_device.device_id, "Connection Lost")
            
            # Reset connections title
            self._reset_connections_title()
            
            # Disable disconnect button
            if self.disconnect_button:
                self.disconnect_button.setEnabled(False)
            
            # Clear selected device
            self.selected_device = None
            
            print("❌ Connection lost - device disconnected")
    
    def _verify_connection_and_handlers(self) -> bool:
        """Verify connection is active and handlers are registered."""
        if not self.selected_device:
            print("❌ No device selected")
            return False
        
        device_id = self.selected_device.device_id
        
        # Check if device is connected
        if device_id not in self.connection_manager.connections:
            print(f"❌ Device {device_id} not in connections")
            return False
        
        connection = self.connection_manager.connections[device_id]
        if not connection.is_connected():
            print(f"❌ Device {device_id} is not connected")
            return False
        
        # Check if handlers are registered
        client = connection.client
        required_handlers = ["live_feed_result", "live_feed_started", "live_feed_error"]
        missing_handlers = [h for h in required_handlers if h not in client.message_handlers]
        
        if missing_handlers:
            print(f"⚠️ Missing handlers: {missing_handlers} - re-registering...")
            # Re-register handlers if missing
            self._register_response_handlers()
            return True
        else:
            print(f"✅ All required handlers registered: {required_handlers}")
            return True
    
    def _start_query(self):
        """Start query processing on the edge device using correct JSON format."""
        if not self.selected_device:
            print("❌ No device selected")
            return
        
        if not self.question_input:
            print("❌ Question input field not available")
            return
        
        query_text = self.question_input.text().strip()
        if not query_text:
            print("❌ Please enter a question")
            return
        
        # Verify connection and handlers before starting
        if not self._verify_connection_and_handlers():
            print("❌ Connection verification failed - cannot start query")
            self._display_response("❌ Connection issue detected. Please reconnect to the device.")
            return
        
        try:
            print(f"🚀 Starting query: '{query_text}'")
            
            # Create query message according to HOST_TO_EDGE_JSON_SPECIFICATION_IN.md
            # Format: {"type": "query", "data": {"query": "...", "streaming": true, "triage_enabled": true/false}}
            import time
            query_data = {
                "query": query_text,
                "streaming": True,  # Boolean true for continuous streaming mode
                "triage_enabled": self.triage_enabled  # Enable data triage if button is activated
            }
            
            # Generate unique message ID
            message_id = f"query_{int(time.time())}"
            
            # Create NetworkMessage with proper format
            from Network.Host_Network.network_client import NetworkMessage
            message = NetworkMessage(
                message_type="query",  # Will be converted to "type" in JSON output
                data=query_data,
                timestamp=time.time(),
                message_id=message_id,
                device_id="edge_device"
            )
            
            print(f"📤 Created query message:")
            print(f"   Type: query")
            print(f"   Query: {query_text}")
            print(f"   Streaming: True")
            print(f"   Triage Enabled: {self.triage_enabled}")
            print(f"   Message ID: {message_id}")
            
            # Send message using connection manager
            if self.selected_device.device_id in self.connection_manager.connections:
                connection = self.connection_manager.connections[self.selected_device.device_id]
                success = connection.client.send_message(message)
                
                if success:
                    print("✅ Query message sent successfully to edge device")
                    # Disable START, enable STOP
                    if self.start_button:
                        self.start_button.setEnabled(False)
                    if self.stop_query_button:
                        self.stop_query_button.setEnabled(True)
                else:
                    print("❌ Failed to send query message")
            else:
                print("❌ Device connection not found")
                
        except Exception as e:
            print(f"❌ Error starting query: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
    
    def _send_live_feed_command(self, command: str, data: dict = None) -> bool:
        """Send live feed command to edge device."""
        if not self.selected_device:
            return False
        
        try:
            # Create live feed command message
            from Network.Host_Network.network_client import NetworkMessage
            message = NetworkMessage(
                message_type=command,
                data=data or {},
                timestamp=time.time()
            )
            
            # Get the connection and send the message
            if self.selected_device.device_id in self.connection_manager.connections:
                connection = self.connection_manager.connections[self.selected_device.device_id]
                return connection.client.send_message(message)
            
            return False
            
        except Exception as e:
            print(f"❌ Error sending live feed command: {e}")
            return False
    
    def _display_response(self, response_text: str, append: bool = False):
        """Display response text in the response display area - thread-safe using signal."""
        print(f"📡 _display_response called - emitting signal...")
        print(f"   Text length: {len(response_text)}")
        print(f"   Signal exists: {hasattr(self, '_update_ui_signal')}")
        print(f"   response_display widget: {self.response_display is not None}")
        
        # ALWAYS try direct update first (if we're on main thread or widget exists)
        if self.response_display:
            try:
                from PyQt6.QtCore import QThread
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    current_thread = QThread.currentThread()
                    main_thread = app.thread()
                    # If on main thread, update directly immediately
                    if current_thread == main_thread:
                        self.response_display.setText(response_text)
                        self.response_display.repaint()
                        self.response_display.update()
                        print(f"✅ Direct update completed (main thread)")
                        # Also emit signal as backup
                        try:
                            self._update_ui_signal.emit(response_text, append)
                        except:
                            pass
                        return
            except Exception as e:
                print(f"⚠️ Thread check failed: {e}")
        
        # If not on main thread or direct update failed, use signal
        try:
            # Use signal for thread-safe update (works from any thread)
            if hasattr(self, '_update_ui_signal'):
                self._update_ui_signal.emit(response_text, append)
                print(f"✅ Signal emitted successfully")
            else:
                print(f"❌ Signal not available, trying direct update...")
                if self.response_display:
                    self.response_display.setText(response_text)
                    print(f"✅ Direct update successful (no signal)")
        except Exception as e:
            print(f"❌ ERROR: Failed to emit signal: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            
            # Fallback: try direct update if signal fails
            print(f"🔄 Fallback: Attempting direct UI update...")
            if self.response_display:
                try:
                    self.response_display.setText(response_text)
                    self.response_display.repaint()
                    self.response_display.update()
                    print(f"✅ Direct update successful (fallback)")
                except Exception as e2:
                    print(f"❌ Direct update also failed: {e2}")
                    import traceback
                    print(f"   Fallback traceback: {traceback.format_exc()}")
            else:
                print(f"❌ response_display widget is None - cannot update UI")
    
    def _display_edge_info(self, info_text: str, append: bool = False):
        """Display edge device information in the edge info display area - thread-safe."""
        if self.edge_info_display:
            try:
                from PyQt6.QtCore import QThread
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    current_thread = QThread.currentThread()
                    main_thread = app.thread()
                    # If on main thread, update directly immediately
                    if current_thread == main_thread:
                        self.edge_info_display.setText(info_text)
                        self.edge_info_display.repaint()
                        self.edge_info_display.update()
                        return
            except Exception as e:
                print(f"⚠️ Thread check failed in _display_edge_info: {e}")
        
        # If not on main thread, use QMetaObject.invokeMethod for thread-safe update
        try:
            from PyQt6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(
                self.edge_info_display,
                "setText",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, info_text)
            )
        except Exception as e:
            print(f"❌ Error updating edge_info_display: {e}")
            # Fallback: try direct update
            if self.edge_info_display:
                try:
                    self.edge_info_display.setText(info_text)
                    self.edge_info_display.repaint()
                    self.edge_info_display.update()
                except Exception as e2:
                    print(f"❌ Direct update also failed: {e2}")
    
    def _direct_ui_update(self, response_text: str, append: bool = False):
        """Direct UI update - called via signal from main thread (thread-safe)."""
        if self.response_display:
            try:
                # Always replace (don't append) - continuous updates replace old info
                self.response_display.setText(response_text)
                self.response_display.repaint()
                self.response_display.update()
                print(f"✅ UI updated via signal callback")
            except Exception as e:
                print(f"❌ Error updating UI widget: {e}")
                import traceback
                print(f"   Traceback: {traceback.format_exc()}")
        else:
            print(f"❌ response_display widget not available in signal callback")
    
    def _diagnose_update_system(self) -> dict:
        """Diagnose the update system to identify why updates aren't working."""
        diagnostics = {
            "response_display_exists": self.response_display is not None,
            "signal_exists": hasattr(self, '_update_ui_signal'),
            "selected_device": self.selected_device is not None,
            "connection_active": False,
            "handlers_registered": {},
            "issues": []
        }
        
        if not diagnostics["response_display_exists"]:
            diagnostics["issues"].append("response_display widget is None")
        
        if not diagnostics["signal_exists"]:
            diagnostics["issues"].append("_update_ui_signal not found")
        
        if self.selected_device and self.connection_manager:
            device_id = self.selected_device.device_id
            if device_id in self.connection_manager.connections:
                connection = self.connection_manager.connections[device_id]
                diagnostics["connection_active"] = connection.is_connected()
                client = connection.client
                required_handlers = ["live_feed_result", "live_feed_started", "live_feed_error"]
                for handler_type in required_handlers:
                    diagnostics["handlers_registered"][handler_type] = handler_type in client.message_handlers
                    if handler_type not in client.message_handlers:
                        diagnostics["issues"].append(f"Handler '{handler_type}' not registered")
            else:
                diagnostics["issues"].append(f"Device {device_id} not in connections")
        else:
            diagnostics["issues"].append("No device selected or connection manager not initialized")
        
        if not diagnostics["connection_active"]:
            diagnostics["issues"].append("Connection to device is not active")
        
        return diagnostics
    
    def _update_model_status(self, status: str, message: str = None):
        """Model status updates removed - not needed."""
        pass
    
    def _update_model_ready_status(self, model_ready: bool):
        """Model ready status updates removed - not needed."""
        pass
    
    def _stop_query(self):
        """Stop the current query/streaming on the edge device."""
        if not self.selected_device:
            print("❌ No device selected")
            return
        
        if not self.selected_device.device_id in self.connection_manager.connections:
            print("❌ Device connection not found")
            return
        
        try:
            print(f"🛑 Sending stop command to edge device...")
            
            # Create stop message according to HOST_TO_EDGE_JSON_SPECIFICATION_IN.md
            # Format: {"type": "stop", "data": {}}
            import time
            message_id = f"stop_{int(time.time())}"
            
            # Create NetworkMessage with proper format
            from Network.Host_Network.network_client import NetworkMessage
            message = NetworkMessage(
                message_type="stop",  # Will be converted to "type" in JSON output
                data={},  # Empty data object as per specification
                timestamp=time.time(),
                message_id=message_id,
                device_id="edge_device"
            )
            
            print(f"📤 Created stop message:")
            print(f"   Type: stop")
            print(f"   Message ID: {message_id}")
            
            # Send message using connection manager
            connection = self.connection_manager.connections[self.selected_device.device_id]
            success = connection.client.send_message(message)
            
            if success:
                print("✅ Stop message sent successfully to edge device")
                # Update UI state - disable STOP button, will be re-enabled after stop_response
                if self.stop_query_button:
                    self.stop_query_button.setEnabled(False)
                # Display message that stop was requested
                self._display_response("🛑 Stop command sent to edge device. Waiting for confirmation...")
            else:
                print("❌ Failed to send stop message")
                self._display_response("❌ Failed to send stop command to edge device.")
                
        except Exception as e:
            print(f"❌ Error sending stop command: {e}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            self._display_response(f"❌ Error sending stop command: {e}")
    
    def _toggle_triage(self):
        """Toggle data triage on/off."""
        if not self.triage_button:
            return
        
        # Toggle the state based on button checked status
        self.triage_enabled = self.triage_button.isChecked()
        
        # Update button text to reflect current state
        if self.triage_enabled:
            self.triage_button.setText("DATA TRIAGE: ON")
            print("✅ Data triage enabled")
        else:
            self.triage_button.setText("DATA TRIAGE: OFF")
            print("❌ Data triage disabled")
    
    def resizeEvent(self, event):
        """Handle window resize to update left column maximum width."""
        super().resizeEvent(event)
        if self.left_widget:
            # Update maximum width to maintain column proportions
            # Account for margins (64px total: 32px on each side)
            available_width = self.width() - 64
            self.left_widget.setMaximumWidth(int(available_width * 0.22))
    
    def closeEvent(self, event):
        """Handle window close event - send exit message and disconnect from edge devices before closing."""
        print("🛑 Application closing - sending exit message to edge devices...")
        
        # Send exit message and disconnect from all connected devices before closing
        if self.connection_manager:
            try:
                # Exit all devices (this will send exit messages)
                self.connection_manager.exit_all()
                print("✅ Sent exit messages and disconnected from all edge devices")
            except Exception as e:
                print(f"⚠️ Error sending exit messages: {e}")
        
        # Accept the close event to allow the window to close
        event.accept()
    
    def _clear_results(self):
        """Clear button functionality removed."""
        print("⚠️ CLEAR button functionality has been removed")
        pass


def _enable_high_dpi_attributes() -> None:
    # High DPI scaling is enabled by default in PyQt6
    # No additional attributes needed for modern PyQt6
    pass


def main() -> int:
    _enable_high_dpi_attributes()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


