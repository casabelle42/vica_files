# GUI Handler Documentation

The GUI Handler (`gui_handler.py`) is a bridge between incoming JSON commands and GUI functions. It allows you to control and update the GUI programmatically through JSON commands.

## Overview

The handler receives JSON commands and maps them to corresponding GUI functions, enabling:
- Window navigation
- Device list management
- Query operations
- Image display and metadata updates
- Button actions

## Usage

### Basic Setup

```python
from Host.gui.gui_handler import GUIHandler
from Host.gui.availibleDevices import MainWindow as AvailableDevicesWindow
from Host.gui.query import MainWindow as QueryWindow

# Create GUI windows
devices_window = AvailableDevicesWindow()
query_window = QueryWindow()

# Create handler
handler = GUIHandler(
    available_devices_window=devices_window,
    query_window=query_window
)

# Process JSON commands
json_command = '{"command": "update_devices", "params": {...}}'
result = handler.process_json(json_command)
```

### JSON Command Format

All commands follow this structure:

```json
{
    "command": "command_name",
    "params": {
        "param1": "value1",
        "param2": "value2"
    }
}
```

## Available Commands

### Window Navigation

#### `open_query_window`
Opens the query window.

```json
{
    "command": "open_query_window",
    "params": {}
}
```

#### `open_devices_window`
Opens/shows the devices window.

```json
{
    "command": "open_devices_window",
    "params": {}
}
```

#### `close_window`
Closes a specific window.

```json
{
    "command": "close_window",
    "params": {
        "window": "query"  // or "devices"
    }
}
```

#### `exit_application`
Exits the application.

```json
{
    "command": "exit_application",
    "params": {}
}
```

### Device Management

#### `update_devices`
Updates the entire device list.

```json
{
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
}
```

#### `add_device`
Adds a new device to the list.

```json
{
    "command": "add_device",
    "params": {
        "device": {
            "name": "Edge Device 4",
            "location": "Room 133",
            "status": "Online",
            "connection": "Medium",
            "metadata": "v2.1.0 • Active"
        }
    }
}
```

#### `remove_device`
Removes a device from the list.

```json
{
    "command": "remove_device",
    "params": {
        "device_name": "Edge Device 1"
    }
}
```

#### `update_device_status`
Updates status information for a specific device.

```json
{
    "command": "update_device_status",
    "params": {
        "device_name": "Edge Device 1",
        "status": {
            "status": "Offline",
            "connection": "Weak",
            "metadata": "v2.1.3 • Maintenance"
        }
    }
}
```

### Query Operations

#### `set_query_text`
Sets the query input text.

```json
{
    "command": "set_query_text",
    "params": {
        "text": "Show me all people in the room"
    }
}
```

#### `send_query`
Sends the current query (clicks the Send button).

```json
{
    "command": "send_query",
    "params": {}
}
```

#### `clear_query`
Clears the query input field.

```json
{
    "command": "clear_query",
    "params": {}
}
```

### Image Operations

#### `display_image`
Displays an image in the preview area.

```json
{
    "command": "display_image",
    "params": {
        "image_path": "/path/to/image.jpg"
    }
}
```

Or with base64 data:

```json
{
    "command": "display_image",
    "params": {
        "image_data": "base64_encoded_image_data"
    }
}
```

#### `update_image_metadata`
Updates image metadata fields.

```json
{
    "command": "update_image_metadata",
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
}
```

#### `add_returned_image`
Adds an image to the returned images section.

```json
{
    "command": "add_returned_image",
    "params": {
        "image_path": "/path/to/image.jpg",
        "metadata": {
            "timestamp": "2025-11-24 17:30:00",
            "confidence": "95%"
        }
    }
}
```

#### `clear_returned_images`
Clears all returned images.

```json
{
    "command": "clear_returned_images",
    "params": {}
}
```

### Metadata Operations

#### `update_metadata`
Updates all metadata fields at once.

```json
{
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
}
```

#### `set_metadata_field`
Sets a specific metadata field.

```json
{
    "command": "set_metadata_field",
    "params": {
        "field": "confidence_rate",
        "value": "98%"
    }
}
```

### Button Actions

#### `click_discover`
Clicks the Discover button.

```json
{
    "command": "click_discover",
    "params": {}
}
```

#### `click_query`
Clicks the Query button (opens query window).

```json
{
    "command": "click_query",
    "params": {}
}
```

#### `click_exit`
Clicks the Exit button (exits application).

```json
{
    "command": "click_exit",
    "params": {}
}
```

#### `click_send`
Clicks the Send button in query window.

```json
{
    "command": "click_send",
    "params": {}
}
```

## Response Format

All commands return a response in this format:

```json
{
    "status": "success" | "error",
    "command": "command_name",
    "result": {
        "message": "Operation completed",
        ...
    },
    "message": "Error message (if error)"
}
```

## Example: Complete Workflow

```python
import json
from Host.gui.gui_handler import GUIHandler
from Host.gui.availibleDevices import MainWindow as AvailableDevicesWindow
from Host.gui.query import MainWindow as QueryWindow

# Setup
app = QApplication(sys.argv)
devices_window = AvailableDevicesWindow()
query_window = QueryWindow()
handler = GUIHandler(devices_window, query_window)

devices_window.show()

# 1. Update device list
update_cmd = json.dumps({
    "command": "update_devices",
    "params": {
        "devices": [
            {"name": "Device 1", "location": "Room 1", "status": "Online", 
             "connection": "Strong", "metadata": "v2.1.3"}
        ]
    }
})
handler.process_json(update_cmd)

# 2. Open query window
open_cmd = json.dumps({
    "command": "open_query_window",
    "params": {}
})
handler.process_json(open_cmd)

# 3. Set query text
query_cmd = json.dumps({
    "command": "set_query_text",
    "params": {"text": "Show me all people"}
})
handler.process_json(query_cmd)

# 4. Send query
send_cmd = json.dumps({
    "command": "send_query",
    "params": {}
})
handler.process_json(send_cmd)

# 5. Update metadata when results arrive
metadata_cmd = json.dumps({
    "command": "update_metadata",
    "params": {
        "metadata": {
            "Image": "result_001.jpg",
            "Edge Device": "Device 1",
            "Query": "Show me all people",
            "Response": "3 people detected",
            "Confidence Rate": "95%",
            "Time Processed": "2025-11-24 17:30:00"
        }
    }
})
handler.process_json(metadata_cmd)

app.exec()
```

## Integration with Network Layer

The handler can be integrated with network communication to receive JSON commands from remote sources:

```python
# Example: Network integration
def on_message_received(json_data):
    """Callback for received network messages."""
    result = handler.process_json(json_data)
    # Send response back if needed
    return result
```

## Error Handling

The handler includes comprehensive error handling:
- Invalid JSON format
- Missing command or parameters
- Unknown commands
- Widget not found errors
- Method not implemented warnings

All errors are logged and returned in the response.

## Extending the Handler

To add new commands:

1. Add a handler method:
```python
def _handle_new_command(self, params: Dict) -> Dict:
    # Implementation
    return {"message": "Command executed"}
```

2. Register in command_map:
```python
self.command_map["new_command"] = self._handle_new_command
```

3. Update GUI classes if needed to expose new functionality.

## Notes

- All GUI operations are thread-safe when used with Qt's signal/slot mechanism
- The handler maintains references to GUI widgets for efficient updates
- Widget references are stored using object names for easy lookup
- Metadata field names are normalized (spaces to underscores, lowercase)

