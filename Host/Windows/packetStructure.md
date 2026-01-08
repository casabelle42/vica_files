# MQTT Packet Specification

**Version 1.0 — Unified for EDGE + HOST**

This document defines the JSON packet structures for all messages exchanged between **Host devices**, **Edge devices**, and the **MQTT broker**. All packets follow a shared header structure to ensure consistency.

---

## 0. Common Packet Structure

All packets must follow this top-level JSON format:

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<device_name>",
    "message_type": "<type>"
  },
  "body": {}
}
```

---

# 1. EDGE DEVICE PACKETS

## 1.1 Incoming to Edge (from HOST)

### **query_request**

```json
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
```

### **cancel_query_request**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<host_name>",
    "message_type": "cancel_query_request"
  },
  "body": {
    "query_id": "<uuid>"
  }
}
```

---

## 1.2 Outgoing from Edge (to HOST)

### **device_status**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "device_status"
  },
  "body": {
    "name": "<edge_name>",
    "cpu": 0.0,
    "ram": 0.0,
    "gpu": 0.0,
    "network_strength": -60,
    "isProcessing": true
  }
}
```

### **container_status**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "container_status"
  },
  "body": {
    "status": "running | stopped | error",
    "uptime_seconds": 0,
    "current_operation": "idle | processing | loading_model"
  }
}
```

### **query_response**

```json
{
    "header": {
            "timestamp": "<ISO-8601>",
            "source_device": "<edge_name>",
            "message_type": "query_response"
    },
    "body": {
        "query_id": "<uuid>",
        "metadata": {
            "image_width": 0,
            "image_height": 0,
            "format": "jpeg",
            "image_base64": "<base64_encoded_image_data>",
            "chunk_index": 0,
            "total_chunks": 1
        },
        "frame": {
            "frame_id": 0,
            "timestamp": "<ISO-8601>",
            "detections": [
                {
                    "label": "string",
                    "confidence": 0.0,
                    "dets": ["det1"]
                }
            ]
        }
    }
}
```

### **cancel_query_status**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "cancel_query_status"
  },
  "body": {
    "query_id": "<uuid>",
    "status": "cancelled | not_found | already_completed"
  }
}
```

---

# 2. HOST DEVICE PACKETS

## 2.1 Outgoing from Host (to EDGE)

### **discovery**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<host_name>",
    "message_type": "discovery"
  },
  "body": {}
}
```

### **query_request**

```json
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
```

### **cancel_query**
```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<host_name>",
    "message_type": "cancel_query"
  },
  "body": {
    "query_id": "<uuid>"
  }
}
```

---

## 2.2 Incoming to Host (from EDGE)

### **available_devices**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "available_devices"
  },
  "body": {
    "devices": [
      {
        "name": "<edge_name>",
        "status": "online",
        "cpu": 0.0,
        "ram": 0.0,
        "gpu": 0.0,
        "network_strength": -60
      }
    ]
  }
}
```

### **device_status**
```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "device_status"
  },
  "body": {
    "name": "<edge_name>",
    "cpu": 0.0,
    "ram": 0.0,
    "gpu": 0.0,
    "network_strength": -60,
    "isProcessing": true
  }
}
```

### **query_response**  
```json
{
    "header": {
            "timestamp": "<ISO-8601>",
            "source_device": "<edge_name>",
            "message_type": "query_response"
    },
    "body": {
        "query_id": "<uuid>",
        "metadata": {
            "image_width": 0,
            "image_height": 0,
            "format": "jpeg",
            "image_base64": "<base64_encoded_image_data>",
            "chunk_index": 0,
            "total_chunks": 1
        },
        "frame": {
            "frame_id": 0,
            "timestamp": "<ISO-8601>",
            "detections": [
                {
                    "label": "string",
                    "confidence": 0.0,
                    "dets": ["det1"]
                }
            ]
        }
    }
}
```

### **container_status**  
```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<edge_name>",
    "message_type": "container_status"
  },
  "body": {
    "status": "running | stopped | error",
    "uptime_seconds": 0,
    "current_operation": "idle | processing | loading_model"
  }
}
```

---

# 3. SERVER PACKETS
## 3.1 Incoming to Server (from HOST)

### **discovery_request**
```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<host_name>",
    "message_type": "discovery_request"
  },
  "body": {}
}
```

## 3.2 Outgoing from Server (to HOST)

### **discovery_response**

```json
{
  "header": {
    "timestamp": "<ISO-8601>",
    "source_device": "<server_name>",
    "message_type": "discovery_response"
  },
  "body": {
    "devices": [
      {
        "name": "<edge_name>",
        "status": "online | offline",
        "cpu": 0.0,
        "ram": 0.0,
        "gpu": 0.0,
        "network_strength": -60,
        "isProcessing": false
      }
    ]
  }
}
```
