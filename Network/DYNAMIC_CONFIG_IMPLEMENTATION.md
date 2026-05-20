# Dynamic Configuration Implementation Guide

**Version 1.0**  
**Date: May 19, 2026**  
**Scope:** Edge Team + GUI/Host Team

---

## Overview

Previously, edge devices required **hardcoded MQTT broker IP addresses** in their source code. This document outlines the implementation of a **dynamic configuration system** allowing the GUI to update broker settings without modifying code.

**Key Benefit:** Change broker IP, port, or device name through the GUI → Edge devices reconnect on restart.

---

## EDGE TEAM IMPLEMENTATION

### Step 1: Create `config.json` in Edge Directory

**File:** `LAS-VICA/Edge/config.json`

```json
{
  "mqtt": {
    "broker": "10.148.0.95",
    "port": 1883
  },
  "device": {
    "name": "Edge-Cam-01",
    "device_id": "edge_cam_01"
  },
  "model": {
    "id": "nvidia/Cosmos-Reason1-7B",
    "available_models": [
      "nvidia/Cosmos-Reason1-7B",
      "dino-v2",
      "sam-3d"
    ]
  },
  "logging": {
    "level": "INFO"
  }
}
```

### Step 2: Update `client.py` - Add Configuration Loader

Add this function near the top of `client.py` after imports:

```python
from pathlib import Path

def load_config():
    """
    Load configuration from file or environment variables.
    Priority: env vars > config.json > defaults
    """
    config = {
        "mqtt_broker": "localhost",
        "mqtt_port": 1883,
        "device_name": "Edge-Device-01"
    }
    
    # Try to load from config.json
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config["mqtt_broker"] = file_config.get("mqtt", {}).get("broker", config["mqtt_broker"])
                config["mqtt_port"] = file_config.get("mqtt", {}).get("port", config["mqtt_port"])
                config["device_name"] = file_config.get("device", {}).get("name", config["device_name"])
                print(f"[Config] ✅ Loaded from {config_file}")
        except Exception as e:
            print(f"[Config] ⚠️  Error reading config.json: {e}, using env vars or defaults")
    else:
        print(f"[Config] ℹ️  No config.json found, checking environment variables")
    
    # Override with environment variables (highest priority)
    config["mqtt_broker"] = os.environ.get("VICA_MQTT_BROKER", config["mqtt_broker"])
    config["mqtt_port"] = int(os.environ.get("VICA_MQTT_PORT", config["mqtt_port"]))
    config["device_name"] = os.environ.get("VICA_DEVICE_NAME", config["device_name"])
    
    print(f"[Config] Using broker: {config['mqtt_broker']}:{config['mqtt_port']} | Device: {config['device_name']}")
    return config
```

### Step 3: Update `MQTTEdgeClient` Constructor

Change the `__init__` method signature:

```python
def __init__(self, mqtt_broker="localhost", mqtt_port=1883, device_name="Edge-Device"):
    self.mqtt_broker = mqtt_broker
    self.mqtt_port = mqtt_port
    self.device_name = device_name
    # ... rest of init code
```

### Step 4: Update `_on_mqtt_connect` Method

```python
def _on_mqtt_connect(self, client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTTEdgeClient] ✅ Connected to broker {self.mqtt_broker}:{self.mqtt_port}")
        # Subscribe to both device-specific and broadcast topics
        device_topic = f"edge/{self.device_name}/control"
        client.subscribe([(device_topic, 0), ("edge/control", 0)])
        print(f"[MQTTEdgeClient] Subscribed to: {device_topic} and edge/control")
    else:
        print(f"[MQTTEdgeClient] ❌ Connection failed with code {rc}")
```

### Step 5: Update `__main__` Entry Point

```python
if __name__ == "__main__":
    config = load_config()
    client = MQTTEdgeClient(
        mqtt_broker=config["mqtt_broker"],
        mqtt_port=config["mqtt_port"],
        device_name=config["device_name"]
    )
    client.start()
```

### Edge Team Checklist

- [ ] Create `config.json` with correct broker IP
- [ ] Add `load_config()` function to `client.py`
- [ ] Update `MQTTEdgeClient.__init__()` signature
- [ ] Update `_on_mqtt_connect()` subscription method
- [ ] Update `__main__` entry point
- [ ] Test with: `python client.py` (should load from config.json)
- [ ] Verify logs show device subscription to `edge/Edge-Cam-01/control`

---

## GUI/HOST TEAM IMPLEMENTATION

### Step 1: Create Configuration Manager

**File:** `LAS-VICA/Host_Team/Host/gui/config_manager.py`

```python
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

class EdgeConfigManager:
    """Manages edge device configuration files."""
    
    EDGE_DIR = Path(__file__).parent.parent.parent.parent / "Edge"
    CONFIG_FILE = EDGE_DIR / "config.json"
    
    @classmethod
    def get_current_config(cls) -> Optional[Dict[str, Any]]:
        """Read current edge configuration."""
        if not cls.CONFIG_FILE.exists():
            return None
        
        try:
            with open(cls.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading config: {e}")
            return None
    
    @classmethod
    def update_config(
        cls,
        broker_ip: str,
        broker_port: int = 1883,
        device_name: str = "Edge-Cam-01"
    ) -> bool:
        """Update edge device configuration."""
        config = cls.get_current_config() or {
            "mqtt": {},
            "device": {},
            "model": {},
            "logging": {}
        }
        
        config["mqtt"]["broker"] = broker_ip
        config["mqtt"]["port"] = broker_port
        config["device"]["name"] = device_name
        
        try:
            with open(cls.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✅ Config updated: {broker_ip}:{broker_port} | Device: {device_name}")
            return True
        except Exception as e:
            print(f"❌ Error writing config: {e}")
            return False
    
    @classmethod
    def validate_config(cls, broker_ip: str, broker_port: int = 1883) -> bool:
        """Validate broker connection."""
        import socket
        try:
            socket.create_connection((broker_ip, broker_port), timeout=2)
            print(f"✅ Broker {broker_ip}:{broker_port} is reachable")
            return True
        except Exception as e:
            print(f"❌ Cannot reach broker: {e}")
            return False
```

### Step 2: Add REST API Endpoints (if using FastAPI/Flask)

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from config_manager import EdgeConfigManager

app = FastAPI()

class EdgeConfigRequest(BaseModel):
    broker_ip: str
    broker_port: int = 1883
    device_name: str

@app.post("/api/edge/config")
def update_edge_config(config: EdgeConfigRequest):
    """Update edge device configuration."""
    manager = EdgeConfigManager()
    
    # Validate broker
    if not manager.validate_config(config.broker_ip, config.broker_port):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reach broker at {config.broker_ip}:{config.broker_port}"
        )
    
    # Save config
    if manager.update_config(config.broker_ip, config.broker_port, config.device_name):
        return {
            "status": "success",
            "message": "Configuration saved. Restart edge device to apply.",
            "config": {
                "broker_ip": config.broker_ip,
                "broker_port": config.broker_port,
                "device_name": config.device_name
            }
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save configuration")

@app.get("/api/edge/config")
def get_edge_config():
    """Get current edge device configuration."""
    manager = EdgeConfigManager()
    config = manager.get_current_config()
    if config:
        return config
    else:
        raise HTTPException(status_code=404, detail="Configuration not found")
```

### Step 3: Add GUI Component (PyQt5 Example)

```python
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox
)
from config_manager import EdgeConfigManager

class EdgeConfigurationPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.config_manager = EdgeConfigManager()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Broker IP input
        self.broker_ip_input = QLineEdit()
        self.broker_ip_input.setPlaceholderText("e.g., 192.168.1.100 or 10.148.0.95")
        layout.addWidget(QLabel("MQTT Broker IP:"))
        layout.addWidget(self.broker_ip_input)
        
        # Broker Port input
        self.broker_port_input = QSpinBox()
        self.broker_port_input.setValue(1883)
        self.broker_port_input.setRange(1, 65535)
        layout.addWidget(QLabel("MQTT Broker Port:"))
        layout.addWidget(self.broker_port_input)
        
        # Device Name input
        self.device_name_input = QLineEdit()
        self.device_name_input.setPlaceholderText("e.g., Edge-Cam-01")
        layout.addWidget(QLabel("Device Name:"))
        layout.addWidget(self.device_name_input)
        
        # Test connection button
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self.test_connection)
        layout.addWidget(test_btn)
        
        # Save button
        save_btn = QPushButton("Save & Apply")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        
        # Status label
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        self.load_current_config()
    
    def load_current_config(self):
        """Load and display current configuration."""
        config = self.config_manager.get_current_config()
        if config:
            self.broker_ip_input.setText(config.get("mqtt", {}).get("broker", ""))
            self.broker_port_input.setValue(config.get("mqtt", {}).get("port", 1883))
            self.device_name_input.setText(config.get("device", {}).get("name", ""))
    
    def test_connection(self):
        """Test connection to specified broker."""
        broker_ip = self.broker_ip_input.text().strip()
        broker_port = self.broker_port_input.value()
        
        if not broker_ip:
            self.status_label.setText("❌ Broker IP cannot be empty")
            return
        
        if self.config_manager.validate_config(broker_ip, broker_port):
            self.status_label.setText(f"✅ Connected to {broker_ip}:{broker_port}")
        else:
            self.status_label.setText(f"❌ Cannot reach {broker_ip}:{broker_port}")
    
    def save_config(self):
        """Save configuration."""
        broker_ip = self.broker_ip_input.text().strip()
        broker_port = self.broker_port_input.value()
        device_name = self.device_name_input.text().strip()
        
        if not broker_ip or not device_name:
            self.status_label.setText("❌ Broker IP and Device Name are required")
            return
        
        if self.config_manager.update_config(broker_ip, broker_port, device_name):
            self.status_label.setText(
                f"✅ Config saved! Restart edge device to apply.\n"
                f"Broker: {broker_ip}:{broker_port} | Device: {device_name}"
            )
        else:
            self.status_label.setText("❌ Failed to save configuration")
```

### GUI Team Checklist

- [ ] Create `config_manager.py` with `EdgeConfigManager` class
- [ ] Add REST API endpoints for config CRUD operations
- [ ] Create GUI panel with broker IP, port, and device name inputs
- [ ] Add "Test Connection" button
- [ ] Add "Save & Apply" button
- [ ] Display current config on load
- [ ] Show clear status messages
- [ ] Test updating config via GUI

---

## Testing Workflow

### Test 1: Edge Device Loads Config

```bash
cd LAS-VICA/Edge
python client.py
# Logs should show:
# [Config] ✅ Loaded from .../config.json
# [Config] Using broker: 10.148.0.95:1883 | Device: Edge-Cam-01
# [MQTTEdgeClient] Subscribed to: edge/Edge-Cam-01/control and edge/control
```

### Test 2: GUI Updates Config

1. Open GUI Edge Configuration panel
2. Enter broker IP: `192.168.1.100`
3. Click "Test Connection" → Should show ✅
4. Click "Save & Apply" → Should show "Config saved"
5. Verify `LAS-VICA/Edge/config.json` was updated

### Test 3: Edge Device Reconnects

```bash
# Restart edge device after config update
cd LAS-VICA/Edge
pkill -f client.py  # Kill old process
python client.py
# Should now use 192.168.1.100 broker
```

---

## Configuration Priority

1. **Environment Variables** (highest)
   - `VICA_MQTT_BROKER`
   - `VICA_MQTT_PORT`
   - `VICA_DEVICE_NAME`

2. **config.json File** (modified by GUI)
   - `mqtt.broker`
   - `mqtt.port`
   - `device.name`

3. **Hardcoded Defaults** (lowest)
   - `localhost:1883`
   - `Edge-Device-01`

---

## Summary

| Action | Team | File | What to Do |
|--------|------|------|-----------|
| Create config file | Edge | `LAS-VICA/Edge/config.json` | Create with broker IP |
| Add config loader | Edge | `LAS-VICA/Edge/client.py` | Add `load_config()` function |
| Update client init | Edge | `LAS-VICA/Edge/client.py` | Accept `device_name` parameter |
| Update subscriptions | Edge | `LAS-VICA/Edge/client.py` | Subscribe to device-specific topic |
| Create config manager | GUI | New file | `config_manager.py` |
| Add REST API | GUI | Backend | `/api/edge/config` endpoints |
| Add GUI panel | GUI | UI module | Configuration dialog |

Once implemented, all broker IP changes are **GUI-driven** without touching edge code.
