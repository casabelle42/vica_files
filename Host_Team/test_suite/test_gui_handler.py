"""
Unit tests for Host_Team/Host/gui/gui_handler.py — GUIHandler's JSON
command dispatch. GUIHandler is a QObject subclass, so a (headless)
QApplication instance is required for PyQt6 to function, but no real
window/widget classes are ever constructed here — ``available_devices_window``
and ``query_window`` are plain Mock objects, so these tests exercise
GUIHandler's own dispatch/validation logic rather than real Qt widget
behavior.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

import gui_handler
from gui_handler import GUIHandler


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def devices_window():
    return MagicMock()


@pytest.fixture
def query_window():
    return MagicMock()


@pytest.fixture
def handler(devices_window, query_window):
    return GUIHandler(available_devices_window=devices_window, query_window=query_window)


class TestProcessJsonValidation:
    def test_invalid_json_returns_error_status(self, handler):
        result = handler.process_json("{not valid json")
        assert result["status"] == "error"
        assert "Invalid JSON" in result["message"]

    def test_missing_command_field_returns_error(self, handler):
        result = handler.process_json('{"params": {}}')
        assert result["status"] == "error"
        assert "Missing 'command'" in result["message"]

    def test_unknown_command_returns_error(self, handler):
        result = handler.process_json('{"command": "does_not_exist"}')
        assert result["status"] == "error"
        assert "Unknown command" in result["message"]

    def test_handler_exception_is_caught_and_reported(self, handler, devices_window):
        devices_window.update_devices.side_effect = RuntimeError("widget gone")
        result = handler.process_json('{"command": "update_devices", "params": {"devices": []}}')
        assert result["status"] == "error"
        assert "widget gone" in result["message"]


class TestDeviceCommands:
    def test_update_devices_calls_window_method_with_list(self, handler, devices_window):
        devices = [{"name": "Edge-01"}]
        result = handler.process_json(f'{{"command": "update_devices", "params": {{"devices": {devices!r}}}}}'.replace("'", '"'))
        assert result["status"] == "success"
        devices_window.update_devices.assert_called_once_with(devices)

    def test_update_devices_without_window_returns_message(self, devices_window):
        handler = GUIHandler(available_devices_window=None)
        result = handler.process_json('{"command": "update_devices", "params": {"devices": []}}')
        assert result["status"] == "success"
        assert "not available" in result["result"]["message"]

    def test_add_device_without_device_data_reports_missing(self, handler):
        result = handler.process_json('{"command": "add_device", "params": {}}')
        assert "No device data provided" in result["result"]["message"]

    def test_remove_device_without_name_reports_missing(self, handler):
        result = handler.process_json('{"command": "remove_device", "params": {}}')
        assert "No device name provided" in result["result"]["message"]

    def test_update_device_status_forwards_to_window(self, handler, devices_window):
        handler.process_json(
            '{"command": "update_device_status", "params": {"device_name": "Edge-01", "status": {"cpu": 5}}}'
        )
        devices_window.update_device_status.assert_called_once_with("Edge-01", {"cpu": 5})


class TestQueryCommands:
    def test_send_query_without_query_window_reports_not_available(self):
        handler = GUIHandler(available_devices_window=None, query_window=None)
        result = handler.process_json('{"command": "send_query", "params": {}}')
        assert "not available" in result["result"]["message"]

    def test_clear_query_calls_query_input_clear(self, handler, query_window):
        query_window.query_input = MagicMock()
        handler.process_json('{"command": "clear_query", "params": {}}')
        query_window.query_input.clear.assert_called_once()


class TestButtonCommands:
    def test_click_exit_without_qapplication_instance_reports_not_found(self, handler, monkeypatch):
        fake_qapp_class = MagicMock()
        fake_qapp_class.instance.return_value = None
        monkeypatch.setattr(gui_handler, "QApplication", fake_qapp_class)
        result = handler.process_json('{"command": "click_exit", "params": {}}')
        assert "not found" in result["result"]["message"]

    def test_click_discover_without_devices_window(self):
        handler = GUIHandler(available_devices_window=None)
        result = handler.process_json('{"command": "click_discover", "params": {}}')
        assert "not available" in result["result"]["message"]


class TestNetworkCallbacks:
    def test_discover_callback_invoked_on_ui_trigger(self, handler):
        called = []
        handler.set_network_callbacks(on_discover=lambda: called.append(True))
        handler._handle_ui_discover_clicked()
        assert called == [True]

    def test_discover_click_with_no_callback_registered_does_not_raise(self, handler):
        handler._on_discover_callback = None
        handler._handle_ui_discover_clicked()  # must not raise

    def test_query_callback_receives_text_and_targets(self, handler):
        received = []
        handler.set_network_callbacks(on_query=lambda text, targets: received.append((text, targets)))
        handler._handle_ui_query_sent("find people", ["Edge-01"])
        assert received == [("find people", ["Edge-01"])]

    def test_query_callback_falls_back_to_single_arg_on_type_error(self, handler):
        received = []

        def legacy_callback(text):
            received.append(text)

        handler.set_network_callbacks(on_query=legacy_callback)
        handler._handle_ui_query_sent("find people", ["Edge-01"])
        assert received == ["find people"]


class TestGetAvailableCommands:
    def test_returns_all_registered_command_names(self, handler):
        commands = handler.get_available_commands()
        assert "update_devices" in commands
        assert "send_query" in commands
        assert len(commands) == len(handler.command_map)
