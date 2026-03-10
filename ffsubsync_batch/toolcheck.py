from __future__ import annotations

import shutil


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def check_ffsubsync() -> bool:
    """Return True if ffsubsync is importable."""
    try:
        from ffsubsync.ffsubsync import make_parser, run  # noqa: F401

        return True
    except ImportError:
        return False
