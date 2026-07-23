"""
video_store.py — the edge device's video directory.

Single source of truth for *where* recorded video lives on an edge device
(Jetson Thor), so the camera writer, the handler's status packets, and query
playback all agree on one path.

Layout on the edge
──────────────────
    <LAS-VICA>/videos/            ← working directory (env override: VICA_VIDEO_DIR)
        cam1/  cam2/  cam3/  cam4/ ← per-camera recordings
        *.mp4                      ← loose clips may also sit at the root

Video *names* handed to the Host are directory-relative POSIX paths, e.g.
``cam1/clip.mp4`` or ``loose.mp4``. ``resolve_video`` maps such a name back to
a file, refusing anything that escapes the videos directory.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

VIDEO_DIR_ENV = "VICA_VIDEO_DIR"
# Per-camera subfolders that live under the videos directory.
CAMERA_SUBDIRS = ("cam1", "cam2", "cam3", "cam4")

# Extensions the edge advertises to the Host as selectable query sources.
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v")


def video_dir() -> Path:
    """Resolve the videos directory path (does not create it).

    Defaults to ``<repo>/videos`` (this file lives in ``<repo>/Edge/``); override
    with ``VICA_VIDEO_DIR`` when the deployment puts it elsewhere.
    """
    override = (os.environ.get(VIDEO_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent / "videos"


def ensure_video_dir() -> Tuple[Path, bool]:
    """Create the videos directory (and per-camera subfolders) if missing.

    Returns ``(path, created_now)`` — ``created_now`` is True only when this
    call actually made the root directory, which is what the GUI prompt reports.
    """
    path = video_dir()
    existed = path.is_dir()
    path.mkdir(parents=True, exist_ok=True)
    # Ensure each camera has a place to record into. Never flips created_now —
    # that flag is specifically about the videos root the user is told about.
    for cam in CAMERA_SUBDIRS:
        (path / cam).mkdir(parents=True, exist_ok=True)
    return path, not existed


def list_videos() -> List[str]:
    """Directory-relative names of every video, newest first.

    Covers loose clips at the videos root *and* everything inside the per-camera
    subfolders. Names are POSIX-style relative paths (``cam1/clip.mp4``) — the
    Host never receives absolute edge paths.
    """
    root = video_dir()
    if not root.is_dir():
        return []

    found: list[Path] = []
    try:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                found.append(p)
    except OSError:
        return []

    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.relative_to(root).as_posix() for p in found]


def resolve_video(name: Optional[str]) -> Optional[Path]:
    """Map a video *name* from a query_request back to a file on disk.

    Accepts a directory-relative name, optionally inside a subfolder
    (``cam2/clip.mp4``). Returns None for anything that is absolute, escapes the
    videos directory, is not a recognised video type, or does not exist — a
    query packet must not be able to reach arbitrary paths.
    """
    name = str(name or "").strip()
    if not name:
        return None

    rel = Path(name)
    if rel.is_absolute():
        return None
    if rel.suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    root = video_dir()
    try:
        resolved = (root / rel).resolve()
        root_resolved = root.resolve()
    except OSError:
        return None

    # Must stay inside the videos directory (blocks ``..`` traversal).
    if resolved != root_resolved and root_resolved not in resolved.parents:
        return None
    if not resolved.is_file():
        return None
    return resolved
