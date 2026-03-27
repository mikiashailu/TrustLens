"""Best-effort video/audio metrics (OpenCV, mutagen) for trust heuristics."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def probe_video(path: Path) -> dict[str, Any] | None:
    """Width, height, frame count, fps, duration (s). None if OpenCV missing or open fails."""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = (n / fps) if fps > 0 else None
        return {"width": w, "height": h, "fps": fps, "frames": n, "duration": duration}
    finally:
        cap.release()


def probe_audio(path: Path) -> dict[str, Any] | None:
    """Duration (s) and bitrate when mutagen can read the file."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None
    try:
        audio = MutagenFile(str(path))
        if audio is None or not hasattr(audio, "info") or audio.info is None:
            return None
        info = audio.info
        duration = getattr(info, "length", None)
        if duration is None:
            return None
        bitrate = getattr(info, "bitrate", None)
        return {"duration": float(duration), "bitrate": int(bitrate) if bitrate else None}
    except Exception:
        return None
