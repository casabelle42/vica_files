"""
Unit tests for Edge/model_init.py — camera worker, jpeg encoding, and the
inference queueing logic in ModelService.

Real cv2 (opencv-python-headless) is installed so encode_jpeg_b64 and the
BGR/RGB frame handling run against the genuine library; only
cv2.VideoCapture (the part that touches physical hardware) is faked, per
the requirement that tests never open a real camera. torch/transformers
are stubbed in conftest.py since nothing here exercises real model weights.
"""

import queue
import threading
import time

import numpy as np
import pytest

import model_init
from model_init import CFG, CameraWorker, ModelService, encode_jpeg_b64, sys_metrics


def make_frame(color=(10, 20, 30)):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[:, :] = color
    return frame


class FakeCapture:
    """Stands in for cv2.VideoCapture without touching a real device."""

    def __init__(self, frames=None, opened=True):
        self._frames = list(frames or [])
        self._opened = opened
        self.released = False
        self.read_calls = 0

    def isOpened(self):
        return self._opened

    def read(self):
        self.read_calls += 1
        if self._frames:
            return True, self._frames.pop(0)
        return False, None

    def release(self):
        self.released = True
        self._opened = False


class FakeCaptureFactory:
    """cv2.VideoCapture replacement that hands out pre-scripted captures."""

    def __init__(self, captures):
        self._captures = list(captures)
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if self._captures:
            return self._captures.pop(0)
        return FakeCapture(opened=False)


# ---------------------------------------------------------------------------
# encode_jpeg_b64 / sys_metrics — pure utility functions
# ---------------------------------------------------------------------------

class TestEncodeJpegB64:
    def test_encodes_real_frame_to_base64_string(self):
        frame = make_frame()
        encoded = encode_jpeg_b64(frame)
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_returns_empty_string_when_cv2_imencode_fails(self, monkeypatch):
        monkeypatch.setattr(model_init.cv2, "imencode", lambda *a, **k: (False, None))
        assert encode_jpeg_b64(make_frame()) == ""


class TestSysMetrics:
    def test_returns_expected_keys(self):
        metrics = sys_metrics()
        assert set(metrics) == {"cpu_pct", "ram_used_mb", "ram_total_mb"}
        assert metrics["ram_total_mb"] >= metrics["ram_used_mb"] >= 0


# ---------------------------------------------------------------------------
# CameraWorker — retry/reopen state machine, no real hardware
# ---------------------------------------------------------------------------

class TestCameraWorkerOpenCapture:
    def test_open_capture_success_sets_opened_state(self, monkeypatch):
        cap = FakeCapture(opened=True)
        monkeypatch.setattr(model_init.cv2, "VideoCapture", lambda *a, **k: cap)

        worker = CameraWorker(cam_index=0, out_q=queue.Queue())
        assert worker._open_capture() is True
        assert worker.is_open is True
        assert worker.last_error == ""

    def test_open_capture_failure_sets_error_state(self, monkeypatch):
        cap = FakeCapture(opened=False)
        monkeypatch.setattr(model_init.cv2, "VideoCapture", lambda *a, **k: cap)

        worker = CameraWorker(cam_index=0, out_q=queue.Queue())
        assert worker._open_capture() is False
        assert worker.is_open is False
        assert "failed to open camera" in worker.last_error

    def test_uses_gstreamer_pipeline_when_configured(self, monkeypatch):
        monkeypatch.setattr(CFG, "CAMERA_GSTREAMER", "fakesrc ! appsink")
        factory = FakeCaptureFactory([FakeCapture(opened=True)])
        monkeypatch.setattr(model_init.cv2, "VideoCapture", factory)

        worker = CameraWorker(cam_index=0, out_q=queue.Queue())
        worker._open_capture()

        assert factory.calls[0][0] == "fakesrc ! appsink"
        monkeypatch.setattr(CFG, "CAMERA_GSTREAMER", "")

    def test_releases_previous_capture_before_reopening(self, monkeypatch):
        first_cap = FakeCapture(opened=True)
        second_cap = FakeCapture(opened=True)
        factory = FakeCaptureFactory([first_cap, second_cap])
        monkeypatch.setattr(model_init.cv2, "VideoCapture", factory)

        worker = CameraWorker(cam_index=0, out_q=queue.Queue())
        worker._open_capture()
        worker._open_capture()

        assert first_cap.released is True


class TestCameraWorkerRunLoop:
    def _run_briefly(self, worker, timeout=2.0):
        worker.start()
        deadline = time.time() + timeout
        while time.time() < deadline and worker.out_q.empty():
            time.sleep(0.01)
        worker.stop()
        worker.join(timeout=2.0)

    def test_frames_flow_into_queue_and_capture_is_released_on_stop(self, monkeypatch):
        cap = FakeCapture(frames=[make_frame() for _ in range(5)], opened=True)
        monkeypatch.setattr(model_init.cv2, "VideoCapture", lambda *a, **k: cap)
        monkeypatch.setattr(CFG, "FRAME_INTERVAL_SEC", 0.001)

        out_q = queue.Queue(maxsize=5)
        worker = CameraWorker(cam_index=0, out_q=out_q)
        self._run_briefly(worker)

        assert not out_q.empty()
        frame_id, frame_ts, frame = out_q.get_nowait()
        assert frame_id >= 1
        assert isinstance(frame_ts, float)
        assert cap.released is True
        assert worker.is_open is False

    def test_only_the_most_recent_frame_is_kept_in_queue(self, monkeypatch):
        cap = FakeCapture(frames=[make_frame((i, i, i)) for i in range(10)], opened=True)
        monkeypatch.setattr(model_init.cv2, "VideoCapture", lambda *a, **k: cap)
        monkeypatch.setattr(CFG, "FRAME_INTERVAL_SEC", 0.001)

        out_q = queue.Queue(maxsize=5)
        worker = CameraWorker(cam_index=0, out_q=out_q)
        worker.start()
        deadline = time.time() + 2.0
        while time.time() < deadline and cap.read_calls < 10:
            time.sleep(0.01)
        worker.stop()
        worker.join(timeout=2.0)

        # _drain_stale_frames keeps the queue from accumulating every frame.
        assert out_q.qsize() <= 1

    def test_reopens_after_max_consecutive_read_failures(self, monkeypatch):
        failing_cap = FakeCapture(frames=[], opened=True)  # read() always returns (False, None)
        recovered_cap = FakeCapture(frames=[make_frame()], opened=True)
        factory = FakeCaptureFactory([failing_cap, recovered_cap])
        monkeypatch.setattr(model_init.cv2, "VideoCapture", factory)
        monkeypatch.setattr(CFG, "FRAME_INTERVAL_SEC", 0.001)

        out_q = queue.Queue(maxsize=5)
        worker = CameraWorker(cam_index=0, out_q=out_q)
        worker.OPEN_RETRY_SEC = 0.01
        worker.MAX_CONSECUTIVE_READ_FAILS = 3
        self._run_briefly(worker, timeout=3.0)

        assert failing_cap.released is True
        assert len(factory.calls) >= 2  # reopened after exhausting read failures
        assert not out_q.empty()  # eventually recovered and produced a frame

    def test_stop_is_idempotent_and_releases_capture(self, monkeypatch):
        cap = FakeCapture(frames=[make_frame()], opened=True)
        monkeypatch.setattr(model_init.cv2, "VideoCapture", lambda *a, **k: cap)
        monkeypatch.setattr(CFG, "FRAME_INTERVAL_SEC", 0.001)

        worker = CameraWorker(cam_index=0, out_q=queue.Queue())
        worker.start()
        time.sleep(0.05)
        worker.stop()
        worker.stop()  # must not raise
        worker.join(timeout=2.0)
        assert worker.is_open is False


# ---------------------------------------------------------------------------
# ModelService — inference queueing without a real model or camera thread
# ---------------------------------------------------------------------------

class FakeVLM:
    """Stands in for NanoVLM without needing torch/transformers weights."""

    def __init__(self):
        self.paused = False
        self.queries = []

    def set_query(self, q):
        self.queries.append(q)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def infer(self, frame_bgr):
        return {"summary": "fake summary", "detections": []}


@pytest.fixture
def service():
    svc = ModelService()
    svc.model = FakeVLM()
    return svc


class TestModelServiceCameraHealth:
    def test_camera_health_reports_closed_camera_by_default(self, service):
        health = service.camera_health()
        assert health["camera_open"] is False
        assert health["camera_last_frame_age_sec"] is None
        assert health["frames_queued"] == 0

    def test_camera_health_reflects_open_state_and_queue_depth(self, service):
        service.cam_worker._set_state(opened=True, frame_ts=time.time())
        service.frames.put((1, time.time(), make_frame()))

        health = service.camera_health()
        assert health["camera_open"] is True
        assert health["camera_last_frame_age_sec"] >= 0
        assert health["frames_queued"] == 1


class TestModelServicePauseResume:
    def test_paused_setter_delegates_to_model(self, service):
        service.paused = True
        assert service.paused is True
        assert service.model.paused is True
        service.paused = False
        assert service.paused is False


class TestRunInferenceMany:
    def test_returns_empty_list_when_no_frame_arrives_before_timeout(self, service):
        result = service.run_inference_many("describe", num_frames=1, timeout_sec=0.1)
        assert result == []

    def test_clamps_num_frames_to_between_one_and_ten(self, service):
        for i in range(3):
            service.frames.put((i, time.time(), make_frame()))
        result = service.run_inference_many("describe", num_frames=0, timeout_sec=0.5)
        assert len(result) == 1  # clamped up to minimum of 1

    def test_collects_available_frames_and_runs_inference_on_each(self, service):
        for i in range(3):
            service.frames.put((i, time.time(), make_frame()))
        result = service.run_inference_many("describe", num_frames=3, timeout_sec=0.5)

        assert len(result) == 3
        assert all(r["results"] == "fake summary" for r in result)
        assert all("image" in r for r in result)
        assert service.model.queries == ["describe"]

    def test_stops_waiting_once_camera_reports_closed_with_partial_results(self, service):
        service.frames.put((1, time.time(), make_frame()))
        service.cam_worker._set_state(opened=False)  # simulate a dead camera

        result = service.run_inference_many("describe", num_frames=5, timeout_sec=0.3)
        assert len(result) == 1  # got the one queued frame, then gave up early


class TestRunInferenceOnVideo:
    def test_missing_video_file_returns_empty_list(self, service):
        result = service.run_inference_many(
            "describe", num_frames=2, video_path="does_not_exist.mp4"
        )
        assert result == []
