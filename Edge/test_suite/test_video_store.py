"""
Unit tests for Edge/video_store.py — the edge device's video directory.

video_dir()/ensure_video_dir()/list_videos()/resolve_video() are pure
filesystem logic with no camera or network involvement, so they are
tested directly against a temporary directory (via the VICA_VIDEO_DIR
env override) rather than the real edge deployment path.
"""

from pathlib import Path

import pytest

import video_store


@pytest.fixture
def store(tmp_path, monkeypatch):
    """video_store with VICA_VIDEO_DIR pointed at an isolated tmp dir.

    video_dir() reads the env var fresh on every call, so no module reload
    is needed for the override to take effect.
    """
    monkeypatch.setenv("VICA_VIDEO_DIR", str(tmp_path))
    yield video_store


class TestVideoDir:
    def test_uses_env_override_when_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VICA_VIDEO_DIR", str(tmp_path))
        assert video_store.video_dir() == tmp_path

    def test_defaults_to_repo_videos_dir_without_override(self, monkeypatch):
        monkeypatch.delenv("VICA_VIDEO_DIR", raising=False)
        expected = Path(video_store.__file__).resolve().parent.parent / "videos"
        assert video_store.video_dir() == expected

    def test_blank_env_override_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("VICA_VIDEO_DIR", "   ")
        expected = Path(video_store.__file__).resolve().parent.parent / "videos"
        assert video_store.video_dir() == expected


class TestEnsureVideoDir:
    def test_creates_root_and_camera_subdirs(self, tmp_path, monkeypatch):
        target = tmp_path / "videos"  # does not exist yet — created_now should be True
        monkeypatch.setenv("VICA_VIDEO_DIR", str(target))

        path, created = video_store.ensure_video_dir()

        assert path == target
        assert created is True
        for cam in video_store.CAMERA_SUBDIRS:
            assert (target / cam).is_dir()

    def test_second_call_reports_not_created(self, store):
        store.ensure_video_dir()
        _path, created_again = store.ensure_video_dir()
        assert created_again is False

    def test_pre_existing_root_reports_not_created_but_backfills_subdirs(self, store, tmp_path):
        # tmp_path already exists (pytest creates it), so the root itself
        # isn't "newly created" even though the per-camera subfolders are.
        path, created = store.ensure_video_dir()
        assert created is False
        assert (path / "cam3").is_dir()


class TestListVideos:
    def test_empty_when_dir_missing(self, store):
        assert store.list_videos() == []

    def test_lists_loose_and_nested_clips_newest_first(self, store, tmp_path):
        store.ensure_video_dir()
        import time

        old = tmp_path / "loose.mp4"
        old.write_bytes(b"x")
        time.sleep(0.02)
        newer = tmp_path / "cam1" / "clip.mkv"
        newer.write_bytes(b"y")

        names = store.list_videos()
        assert names[0] == "cam1/clip.mkv"
        assert "loose.mp4" in names

    def test_ignores_non_video_extensions(self, store, tmp_path):
        store.ensure_video_dir()
        (tmp_path / "notes.txt").write_bytes(b"x")
        (tmp_path / "clip.mp4").write_bytes(b"y")

        assert store.list_videos() == ["clip.mp4"]

    @pytest.mark.parametrize("ext", [".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"])
    def test_recognizes_every_supported_extension(self, store, tmp_path, ext):
        store.ensure_video_dir()
        (tmp_path / f"clip{ext}").write_bytes(b"x")
        assert store.list_videos() == [f"clip{ext}"]


class TestResolveVideo:
    def test_none_and_empty_name_return_none(self, store):
        assert store.resolve_video(None) is None
        assert store.resolve_video("") is None
        assert store.resolve_video("   ") is None

    def test_resolves_existing_loose_clip(self, store, tmp_path):
        store.ensure_video_dir()
        clip = tmp_path / "loose.mp4"
        clip.write_bytes(b"x")
        assert store.resolve_video("loose.mp4") == clip.resolve()

    def test_resolves_existing_nested_clip(self, store, tmp_path):
        store.ensure_video_dir()
        clip = tmp_path / "cam2" / "clip.mp4"
        clip.write_bytes(b"x")
        assert store.resolve_video("cam2/clip.mp4") == clip.resolve()

    def test_missing_file_returns_none(self, store):
        store.ensure_video_dir()
        assert store.resolve_video("cam1/does_not_exist.mp4") is None

    def test_absolute_path_rejected(self, store, tmp_path):
        store.ensure_video_dir()
        outside = tmp_path.parent / "outside.mp4"
        outside.write_bytes(b"x")
        assert store.resolve_video(str(outside)) is None

    def test_directory_traversal_rejected(self, store, tmp_path):
        store.ensure_video_dir()
        outside = tmp_path.parent / "secret.mp4"
        outside.write_bytes(b"x")
        assert store.resolve_video("../secret.mp4") is None

    def test_unrecognized_extension_rejected(self, store, tmp_path):
        store.ensure_video_dir()
        (tmp_path / "clip.txt").write_bytes(b"x")
        assert store.resolve_video("clip.txt") is None

    def test_uppercase_extension_still_resolves(self, store, tmp_path):
        store.ensure_video_dir()
        clip = tmp_path / "clip.MP4"
        clip.write_bytes(b"x")
        assert store.resolve_video("clip.MP4") == clip.resolve()
