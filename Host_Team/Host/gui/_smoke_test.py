"""Temporary verification — delete after use."""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath("Host_Team/Host/gui"))
sys.path.insert(0, os.path.abspath("Host_Team"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from s1_start_app import run_app
from demo_query import DemoBackend

DemoBackend.DISCOVERY_DELAY_SEC = 0.05
DemoBackend.QUERY_FIRST_DELAY_SEC = 0.05
DemoBackend.QUERY_PER_TARGET_GAP_SEC = 0.05

backend = DemoBackend()
app = QApplication.instance() or QApplication([])
verdicts = []


def step1_discover():
    from s3_availableDevices import MainWindow as DevWin
    dw = next(w for w in app.topLevelWidgets() if isinstance(w, DevWin))
    dw._on_discover_clicked()
    QTimer.singleShot(400, lambda: step2_examine_devices(dw))


def step2_examine_devices(dw):
    rendered = []
    for name, wd in dw.device_widgets.items():
        rendered.append({
            "name": name,
            "status": wd["status_label"].text(),
            "connection": wd["connection_label"].text(),
            "metadata": wd["metadata_label"].text(),
        })
    verdicts.append(("rendered devices", rendered))

    dw._on_device_checked("Demo-Camera-Lobby", True)
    dw._on_device_checked("Demo-Sensor-ServerRoom", True)
    dw._open_query_window()
    qw = dw._query_window
    verdicts.append(("chips populated", qw.target_devices()))
    qw.query_input.setText("how many people?")
    qw._on_send_clicked()
    QTimer.singleShot(700, lambda: step3_examine_responses(qw))


def step3_examine_responses(qw):
    responses = [(item["metadata"].get("edge_device"),
                  (item["metadata"].get("response") or "")[:55])
                 for item in qw.returned_images]
    verdicts.append(("query responses", responses))
    app.quit()


QTimer.singleShot(50, step1_discover)
run_app(backend, banner="VERIFICATION", discovery_reply_topic="host/test/discovery_response")
print()
print("=" * 70)
for v in verdicts:
    print(v[0])
    if isinstance(v[1], list):
        for item in v[1]:
            print("   ", item)
    else:
        print("   ", v[1])
