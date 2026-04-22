"""
GUI Handler Script
Maps incoming JSON commands to GUI functions and updates GUI elements.
"""

import json
import logging
from typing import Any, Dict, Optional, List, Callable
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GUIHandler(QObject):
    """
    Handler class that maps JSON commands to GUI functions.
    Acts as a bridge between incoming JSON data and GUI components.
    """
    
    # Signals for async operations
    command_processed = pyqtSignal(str, dict)  # command_type, result
    
    def __init__(self, available_devices_window=None, query_window=None,
                 on_discover: Optional[Callable[[], None]] = None,
                 on_query: Optional[Callable[[str], None]] = None):
        """
        Initialize the GUI handler.
        
        Args:
            available_devices_window: Instance of availibleDevices.MainWindow
            query_window: Instance of query.MainWindow
        """
        super().__init__()
        self.available_devices_window = available_devices_window
        self.query_window = query_window

        # Network callbacks (typically set to publish MQTT packets)
        self._on_discover_callback = on_discover
        self._on_query_callback = on_query

        # Install UI->handler hooks so *real user clicks* trigger callbacks
        self._install_ui_hooks()

        
        # Store widget references for updates
        self._widget_refs = {}
        
        # Command mapping dictionary
        self.command_map = {
            # Window navigation
            "open_query_window": self._handle_open_query_window,
            "open_devices_window": self._handle_open_devices_window,
            "close_window": self._handle_close_window,
            "exit_application": self._handle_exit_application,
            
            # Device management
            "update_devices": self._handle_update_devices,
            "add_device": self._handle_add_device,
            "remove_device": self._handle_remove_device,
            "update_device_status": self._handle_update_device_status,
            
            # Query operations
            "set_query_text": self._handle_set_query_text,
            "send_query": self._handle_send_query,
            "clear_query": self._handle_clear_query,
            
            # Image operations
            "display_image": self._handle_display_image,
            "update_image_metadata": self._handle_update_image_metadata,
            "add_returned_image": self._handle_add_returned_image,
            "clear_returned_images": self._handle_clear_returned_images,
            
            # Metadata operations
            "update_metadata": self._handle_update_metadata,
            "set_metadata_field": self._handle_set_metadata_field,
            
            # Button actions
            "click_discover": self._handle_click_discover,
            "click_query": self._handle_click_query,
            "click_exit": self._handle_click_exit,
            "click_send": self._handle_click_send,
        }
    
    def process_json(self, json_data: str) -> Dict[str, Any]:
        """
        Process incoming JSON data and execute corresponding GUI actions.
        
        Args:
            json_data: JSON string containing command and parameters
            
        Returns:
            Dictionary with status and result information
        """
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        
        # Extract command and parameters
        command = data.get("command")
        params = data.get("params", {})
        
        if not command:
            error_msg = "Missing 'command' field in JSON"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        
        # Execute command
        if command in self.command_map:
            try:
                result = self.command_map[command](params)
                logger.info(f"Command '{command}' executed successfully")
                self.command_processed.emit(command, result)
                return {"status": "success", "command": command, "result": result}
            except Exception as e:
                error_msg = f"Error executing command '{command}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {"status": "error", "message": error_msg}
        else:
            error_msg = f"Unknown command: {command}"
            logger.warning(error_msg)
            return {"status": "error", "message": error_msg}
    
    def register_widget(self, name: str, widget: Any):
        """Register a widget reference for later updates."""
        self._widget_refs[name] = widget
        logger.debug(f"Registered widget: {name}")
    
    # ==================== Window Navigation Handlers ====================
    
    def _handle_open_query_window(self, params: Dict) -> Dict:
        """Open the query window."""
        if self.available_devices_window:
            self.available_devices_window._open_query_window()
            # Update handler's query window reference if it was just created
            if self.available_devices_window._query_window and (not self.query_window or self.query_window is not self.available_devices_window._query_window):
                self.query_window = self.available_devices_window._query_window
                self._bind_query_window_callbacks(self.query_window)
            return {"message": "Query window opened"}
        return {"message": "Available devices window not available"}
    
    def _handle_open_devices_window(self, params: Dict) -> Dict:
        """Open the devices window."""
        if self.available_devices_window:
            self.available_devices_window.show()
            self.available_devices_window.raise_()
            return {"message": "Devices window opened"}
        return {"message": "Available devices window not available"}
    
    def _handle_close_window(self, params: Dict) -> Dict:
        """Close a window."""
        window_type = params.get("window", "query")
        if window_type == "query":
            query_window = self._get_query_window()
            if query_window:
                query_window.close()
                return {"message": "Query window closed"}
            return {"message": "Query window not available"}
        elif window_type == "devices" and self.available_devices_window:
            self.available_devices_window.close()
            return {"message": "Devices window closed"}
        return {"message": f"Window '{window_type}' not available"}
    
    def _handle_exit_application(self, params: Dict) -> Dict:
        """Exit the application."""
        app = QApplication.instance()
        if app:
            app.quit()
            return {"message": "Application exiting"}
        return {"message": "Application instance not found"}
    
    # ==================== Device Management Handlers ====================
    
    def _handle_update_devices(self, params: Dict) -> Dict:
        """Update the device list."""
        devices = params.get("devices", [])
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        # Store devices for GUI update
        # Note: This requires the GUI class to have an update_devices method
        if hasattr(self.available_devices_window, "update_devices"):
            self.available_devices_window.update_devices(devices)
            return {"message": f"Updated {len(devices)} devices", "count": len(devices)}
        else:
            logger.warning("update_devices method not available in MainWindow")
            return {"message": "update_devices method not implemented"}
    
    def _handle_add_device(self, params: Dict) -> Dict:
        """Add a new device to the list."""
        device = params.get("device", {})
        if not device:
            return {"message": "No device data provided"}
        
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        if hasattr(self.available_devices_window, "add_device"):
            self.available_devices_window.add_device(device)
            return {"message": "Device added", "device": device.get("name", "Unknown")}
        else:
            logger.warning("add_device method not available in MainWindow")
            return {"message": "add_device method not implemented"}
    
    def _handle_remove_device(self, params: Dict) -> Dict:
        """Remove a device from the list."""
        device_name = params.get("device_name")
        if not device_name:
            return {"message": "No device name provided"}
        
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        if hasattr(self.available_devices_window, "remove_device"):
            self.available_devices_window.remove_device(device_name)
            return {"message": f"Device '{device_name}' removed"}
        else:
            logger.warning("remove_device method not available in MainWindow")
            return {"message": "remove_device method not implemented"}
    
    def _handle_update_device_status(self, params: Dict) -> Dict:
        """Update status of a specific device."""
        device_name = params.get("device_name")
        status = params.get("status", {})
        
        if not device_name:
            return {"message": "No device name provided"}
        
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        if hasattr(self.available_devices_window, "update_device_status"):
            self.available_devices_window.update_device_status(device_name, status)
            return {"message": f"Device '{device_name}' status updated", "status": status}
        else:
            logger.warning("update_device_status method not available in MainWindow")
            return {"message": "update_device_status method not implemented"}
    
    # ==================== Query Operations Handlers ====================
    
    def _handle_set_query_text(self, params: Dict) -> Dict:
        """Set the query input text."""
        text = params.get("text", "")
        # Try to get query window from devices window if not directly available
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Find query input widget
        query_input = self._find_widget_in_window(query_window, "query_input")
        if query_input:
            query_input.setText(text)
            return {"message": "Query text set", "text": text}
        return {"message": "Query input widget not found"}
    
    def _handle_send_query(self, params: Dict) -> Dict:
        """Send the current query."""
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Find and click send button
        send_button = self._find_widget_in_window(query_window, "send_button")
        if send_button:
            send_button.click()
            return {"message": "Query sent"}
        return {"message": "Send button not found"}
    
    def _handle_clear_query(self, params: Dict) -> Dict:
        """Clear the query input."""
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        query_input = self._find_widget_in_window(query_window, "query_input")
        if query_input:
            query_input.clear()
            return {"message": "Query cleared"}
        return {"message": "Query input widget not found"}
    
    # ==================== Image Operations Handlers ====================
    
    def _handle_display_image(self, params: Dict) -> Dict:
        """Display an image in the image preview area."""
        image_path = params.get("image_path")
        image_data = params.get("image_data")  # Base64 encoded image
        
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Find image label widget
        image_label = self._find_widget_in_window(query_window, "image_label")
        if image_label:
            if image_path:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    image_label.setPixmap(pixmap)
                    return {"message": "Image displayed", "path": image_path}
                else:
                    return {"message": f"Failed to load image: {image_path}"}
            elif image_data:
                # Handle base64 image data
                from PyQt6.QtCore import QByteArray
                import base64
                try:
                    image_bytes = base64.b64decode(image_data)
                    pixmap = QPixmap()
                    if pixmap.loadFromData(QByteArray(image_bytes)):
                        image_label.setPixmap(pixmap)
                        return {"message": "Image displayed from data"}
                    else:
                        return {"message": "Failed to load image from data"}
                except Exception as e:
                    return {"message": f"Error decoding image data: {str(e)}"}
            else:
                return {"message": "No image_path or image_data provided"}
        return {"message": "Image label widget not found"}
    
    def _handle_update_image_metadata(self, params: Dict) -> Dict:
        """Update image metadata fields."""
        metadata = params.get("metadata", {})
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Update metadata fields
        result = {}
        for key, value in metadata.items():
            field_result = self._handle_set_metadata_field({"field": key, "value": value})
            result[key] = field_result.get("message", "updated")
        
        return {"message": "Metadata updated", "fields": list(metadata.keys())}
    
    def _handle_add_returned_image(self, params: Dict) -> Dict:
        """Add an image to the returned images section."""
        image_path = params.get("image_path")
        image_data = params.get("image_data")
        metadata = params.get("metadata", {})
        
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        if hasattr(query_window, "add_returned_image"):
            query_window.add_returned_image(image_path or image_data, metadata)
            return {"message": "Image added to returned images"}
        else:
            logger.warning("add_returned_image method not available in QueryWindow")
            return {"message": "add_returned_image method not implemented"}
    
    def _handle_clear_returned_images(self, params: Dict) -> Dict:
        """Clear all returned images."""
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        if hasattr(query_window, "clear_returned_images"):
            query_window.clear_returned_images()
            return {"message": "Returned images cleared"}
        else:
            logger.warning("clear_returned_images method not available in QueryWindow")
            return {"message": "clear_returned_images method not implemented"}
    
    # ==================== Metadata Operations Handlers ====================
    
    def _handle_update_metadata(self, params: Dict) -> Dict:
        """Update all metadata fields at once."""
        metadata = params.get("metadata", {})
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Use the new update_metadata method if available
        if hasattr(query_window, "update_metadata"):
            query_window.update_metadata(metadata)
            return {"message": "Metadata updated", "fields": list(metadata.keys())}
        
        # Fallback to individual field updates
        return self._handle_update_image_metadata(params)
    
    def _handle_set_metadata_field(self, params: Dict) -> Dict:
        """Set a specific metadata field."""
        field = params.get("field")
        value = params.get("value", "")
        
        if not field:
            return {"message": "No field name provided"}
        
        query_window = self._get_query_window()
        if not query_window:
            return {"message": "Query window not available. Please open it first."}
        
        # Find metadata label by field name
        metadata_label = self._find_widget_in_window(query_window, f"metadata_{field}")
        if metadata_label:
            # Update label text (assuming format "Field: value")
            current_text = metadata_label.text()
            if ":" in current_text:
                field_name = current_text.split(":")[0]
                metadata_label.setText(f"{field_name}: {value}")
            else:
                metadata_label.setText(f"{field}: {value}")
            return {"message": f"Metadata field '{field}' updated", "value": value}
        return {"message": f"Metadata field '{field}' not found"}
    
    # ==================== Button Action Handlers ====================
    
    def _handle_click_discover(self, params: Dict) -> Dict:
        """Click the Discover button."""
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        if self.available_devices_window.discover_btn:
            self.available_devices_window.discover_btn.click()
            return {"message": "Discover button clicked"}
        return {"message": "Discover button not found"}
    
    def _handle_click_query(self, params: Dict) -> Dict:
        """Click the Query button."""
        if not self.available_devices_window:
            return {"message": "Available devices window not available"}
        
        if self.available_devices_window.query_btn:
            self.available_devices_window.query_btn.click()
            return {"message": "Query button clicked"}
        return {"message": "Query button not found"}
    
    def _handle_click_exit(self, params: Dict) -> Dict:
        """Click the Exit button."""
        return self._handle_exit_application(params)
    
    def _handle_click_send(self, params: Dict) -> Dict:
        """Click the Send button in query window."""
        return self._handle_send_query(params)
    
    
    # ==================== UI Callback Wiring ====================

    def set_network_callbacks(self,
                              on_discover: Optional[Callable[[], None]] = None,
                              on_query: Optional[Callable[[str], None]] = None) -> None:
        """Register functions that will be invoked when the user clicks UI buttons.

        Typical usage: pass functions that publish MQTT packets for discovery/query.
        """
        self._on_discover_callback = on_discover
        self._on_query_callback = on_query

        # Re-apply hooks in case windows were created after init
        self._install_ui_hooks()

    def _install_ui_hooks(self) -> None:
        """Attach window callbacks so the UI can trigger network actions."""
        # Hook Discover button -> handler callback
        if self.available_devices_window and hasattr(self.available_devices_window, "set_discover_callback"):
            try:
                self.available_devices_window.set_discover_callback(self._handle_ui_discover_clicked)
            except Exception as e:
                logger.warning(f"Failed to set discover callback: {e}")
        if self.available_devices_window and hasattr(self.available_devices_window, "set_query_callback"):
            try:
                self.available_devices_window.set_query_callback(self._handle_ui_query_sent)
            except Exception as e:
                logger.warning(f"Failed to set query callback on devices window: {e}")

        # Wrap query window creation so we can bind the send callback every time it opens
        if self.available_devices_window and hasattr(self.available_devices_window, "_open_query_window"):
            if not hasattr(self.available_devices_window, "_gui_handler_wrapped_open_query"):
                original_open = self.available_devices_window._open_query_window

                def wrapped_open_query_window():  # noqa: ANN001
                    original_open()
                    # Grab the created window reference
                    try:
                        qw = getattr(self.available_devices_window, "_query_window", None)
                        if qw:
                            self.query_window = qw
                            self._bind_query_window_callbacks(qw)
                    except Exception as e:
                        logger.warning(f"Failed to bind query window after open: {e}")

                self.available_devices_window._open_query_window = wrapped_open_query_window
                setattr(self.available_devices_window, "_gui_handler_wrapped_open_query", True)
                # IMPORTANT: Qt signal connections capture the bound method at connect-time.
                # s3_availableDevices connects query_btn.clicked to the original method
                # during window init, so replacing the attribute is not enough; reconnect.
                try:
                    btn = getattr(self.available_devices_window, "query_btn", None)
                    if btn is not None and hasattr(btn, "clicked"):
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                        btn.clicked.connect(self.available_devices_window._open_query_window)
                except Exception as e:
                    logger.warning(f"Failed to rewire query button: {e}")

        # If a query window already exists, bind it now
        if self.query_window:
            self._bind_query_window_callbacks(self.query_window)

    def _bind_query_window_callbacks(self, query_window) -> None:
        """Bind the Send button behavior to the handler's on_query callback."""
        if hasattr(query_window, "set_query_callback"):
            try:
                query_window.set_query_callback(self._handle_ui_query_sent)
            except Exception as e:
                logger.warning(f"Failed to set query callback: {e}")

    def _handle_ui_discover_clicked(self) -> None:
        """Called when the user clicks Discover in the Available Devices UI."""
        if self._on_discover_callback:
            self._on_discover_callback()
        else:
            logger.info("[GUIHandler] Discover clicked, but no network callback registered")

    def _handle_ui_query_sent(self, query_text: str) -> None:
        """Called when the user clicks Send in the Query UI."""
        if self._on_query_callback:
            self._on_query_callback(query_text)
        else:
            logger.info(f"[GUIHandler] Query sent '{query_text}', but no network callback registered")

    # ==================== Helper Methods ====================
    
    def _get_query_window(self):
        """Get the query window, checking devices window if not directly available."""
        if self.query_window:
            return self.query_window
        # Try to get from devices window if it was created
        if self.available_devices_window and hasattr(self.available_devices_window, "_query_window"):
            if self.available_devices_window._query_window:
                self.query_window = self.available_devices_window._query_window
                return self.query_window
        return None
    
    def _find_widget_in_window(self, window: Any, widget_name: str) -> Optional[Any]:
        """
        Find a widget by name in a window.
        This is a helper method that searches through window's widgets.
        """
        # Check registered widgets first
        if widget_name in self._widget_refs:
            return self._widget_refs[widget_name]
        
        # Try to find widget by attribute name
        if hasattr(window, widget_name):
            return getattr(window, widget_name)
        
        # Recursive search through all widgets
        def search_widgets(parent):
            for child in parent.findChildren(QLabel) + parent.findChildren(type(parent)):
                if hasattr(child, "objectName") and child.objectName() == widget_name:
                    return child
            return None
        
        result = search_widgets(window)
        return result
    
    def get_available_commands(self) -> List[str]:
        """Get list of all available commands."""
        return list(self.command_map.keys())


# Example usage and JSON format documentation
EXAMPLE_JSON_COMMANDS = {
    "open_query_window": {
        "command": "open_query_window",
        "params": {}
    },
    "update_devices": {
        "command": "update_devices",
        "params": {
            "devices": [
                {
                    "name": "Edge Device 1",
                    "location": "Room 131",
                    "status": "Online",
                    "connection": "Strong",
                    "metadata": "v2.1.3 • Active"
                }
            ]
        }
    },
    "set_query_text": {
        "command": "set_query_text",
        "params": {
            "text": "Show me all people in the room"
        }
    },
    "send_query": {
        "command": "send_query",
        "params": {}
    },
    "display_image": {
        "command": "display_image",
        "params": {
            "image_path": "/path/to/image.jpg"
        }
    },
    "update_metadata": {
        "command": "update_metadata",
        "params": {
            "metadata": {
                "Image": "image_001.jpg",
                "Edge Device": "Edge Device 1",
                "Query": "Show me all people",
                "Response": "3 people detected",
                "Confidence Rate": "95%",
                "Time Processed": "2025-11-24 17:30:00"
            }
        }
    },
    "exit_application": {
        "command": "exit_application",
        "params": {}
    }
}


if __name__ == "__main__":
    # Example usage
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Create handler (windows would be passed in real usage)
    handler = GUIHandler()
    
    # Example: Process a JSON command
    example_json = json.dumps({
        "command": "update_devices",
        "params": {
            "devices": [
                {
                    "name": "Edge Device 1",
                    "location": "Room 131",
                    "status": "Online",
                    "connection": "Strong",
                    "metadata": "v2.1.3 • Active"
                }
            ]
        }
    })
    
    result = handler.process_json(example_json)
    print(f"Result: {result}")
    
    # Print available commands
    print(f"\nAvailable commands: {handler.get_available_commands()}")

