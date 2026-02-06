# LAS-VICA GUI Test Suite

This test suite allows testing the GUI with simulated edge device responses without requiring actual edge devices, MQTT broker, or VILA inference.

## Quick Start

### Option 1: Full GUI Simulator (RECOMMENDED - No MQTT Required)
```bash
cd Host_Team/Host/gui/tests
python full_gui_simulator.py
```

This runs the complete GUI with all features simulated:
- Device discovery with 3 simulated edge devices
- Real-time device status updates (CPU/RAM/GPU)
- Query processing with test images
- Image display with metadata

### Option 2: Generate Test Images Only
```bash
cd Host_Team/Host/gui/tests
python generate_test_images.py
```

### Option 3: MQTT-Based Test (requires MQTT broker)
```bash
# Terminal 1: Start MQTT broker (e.g., mosquitto)
mosquitto -v

# Terminal 2: Start mock edge server
python mock_edge_server.py --broker localhost

# Terminal 3: Run the GUI
python run_gui_test.py --broker localhost
```

### Option 4: Standalone Query Matching Test
```bash
python run_gui_test.py --standalone
```

## Test Query

The test suite is designed to respond to queries like:
- **"is there anyone behind the black car"**
- "show me people behind the car"
- "where is the black car"
- "find all people in the scene"

## Components

### `generate_test_images.py`
Generates synthetic images depicting people standing behind a black car. Creates 5 test images with varying numbers of people (1-3) and detection bounding boxes.

### `mock_edge_server.py`
A mock MQTT server that:
- Responds to discovery requests with mock device information
- Responds to query requests with test images and detection metadata
- Simulates realistic response times

### `run_gui_test.py`
Main test runner that:
1. Checks/installs dependencies
2. Generates test images
3. Starts the mock edge server
4. Launches the GUI application

## Test Images

Generated images are stored in `test_images/` and include:
- `person_behind_car_01.jpg` - 1 person behind black car
- `person_behind_car_02.jpg` - 2 people behind black car
- `person_behind_car_03.jpg` - 3 people behind black car
- `person_behind_car_04.jpg` - 2 people (alternate view)
- `person_behind_car_05.jpg` - 1 person (alternate view)

Each image includes:
- Green bounding boxes around detected persons
- Confidence labels (85-99%)
- Timestamp overlay
- Device identifier

## Response Format

The mock server returns responses following the packet structure defined in `Host_Team/Host/packetStructure.md`:

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "Edge-Cam-01",
    "message_type": "query_response"
  },
  "body": {
    "query_id": "<uuid>",
    "metadata": {
      "image_width": 800,
      "image_height": 600,
      "format": "jpeg",
      "image_base64": "<base64_data>",
      "chunk_index": 0,
      "total_chunks": 3
    },
    "frame": {
      "frame_id": 0,
      "timestamp": "<ISO-8601>",
      "detections": [
        {
          "label": "person",
          "confidence": 0.92,
          "bbox": [100, 150, 160, 350]
        }
      ]
    }
  }
}
```

## Requirements

- Python 3.8+
- paho-mqtt
- Pillow
- PyQt6
- MQTT broker (mosquitto recommended for local testing)

Install dependencies:
```bash
pip install paho-mqtt Pillow PyQt6
```

## MQTT Broker Setup (Optional)

For local testing, install mosquitto:

**Windows:**
```bash
winget install mosquitto
```

**Ubuntu/Debian:**
```bash
sudo apt install mosquitto mosquitto-clients
```

**macOS:**
```bash
brew install mosquitto
```

Start the broker:
```bash
mosquitto -v
```
