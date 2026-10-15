# LAS-VICA
Video Intelligence Chat Assistant (VICA)

VICA is a distributed vision-language querying system for time-limited surveillance video stored on multiple independent edge devices. It enables an analyst (on a host machine) to broadcast natural-language queries to a fleet of edge devices (drones, mobile units, fixed cameras). Each edge device searches its local video for relevant data.

---

## 1) Project Summary

### Brief Description
Intelligence analysts face a critical challenge in distributed surveillance operations: multiple edge devices (drones, mobile units, fixed cameras) monitor locations but retain video for only 12–24 hours before storage constraints force deletion. VICA addresses this ephemeral intelligence challenge by enabling analysts to broadcast natural language queries to multiple edge devices simultaneously, with each device independently processing its stored video using lightweight AI models and returning matching frames.

### Research Questions / Problem Statement
How can distributed vision-language AI systems maximize intelligence extraction from temporary video storage across multiple independent edge devices with 12–24 hour retention windows, enabling analysts to query entire surveillance networks with natural language commands and receive aggregated results before automatic data deletion?

---

## 2) High-Level Architecture

- **Host (Analyst Workstation)**
  - Runs the GUI and host client.
  - Publishes analyst natural-language queries.
  - Aggregates results returned from edge devices.
  - Displays returned frames / metadata to the analyst.

- **Edge Devices (Video Holders)**
  - Each edge device retains only 12–24 hours of video.
  - Runs an edge client + VLM initialization/inference pipeline.
  - Subscribes to broadcast queries, searches local video, and returns matches.

- **Network / Infrastructure (NUC Hub)**
  - Acts as the local “backbone” node in the system.
  - Hosts the **MQTT broker** and server components that route messages/data between host and edges.
  - May also host an upload/collection service for returned frames and status updates.
# vica_internvideo
# vica_files
