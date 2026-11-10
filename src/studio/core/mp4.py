"""Minimal MP4 header reader (pure Python, no external tools).

Extracts display width/height (rotation-aware) and duration from the `moov` box.
Returns None when the file cannot be understood; callers must treat that as "unknown",
never as invalid.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_MAX_MOOV = 64 * 1024 * 1024


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration_seconds: float | None


def _top_level(f: BinaryIO, end: int) -> Iterator[tuple[bytes, int, int]]:
    pos = 0
    while pos + 8 <= end:
        f.seek(pos)
        hdr = f.read(8)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack(">I4s", hdr)
        header = 8
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return
            size = struct.unpack(">Q", ext)[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield typ, pos + header, pos + size
        pos += size


def _children(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    pos = 0
    while pos + 8 <= len(data):
        size, typ = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > len(data):
                return
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = len(data) - pos
        if size < header or pos + size > len(data):
            return
        yield typ, data[pos + header : pos + size]
        pos += size


def _parse_mvhd(p: bytes) -> float | None:
    if not p:
        return None
    if p[0] == 1 and len(p) >= 32:
        timescale = struct.unpack(">I", p[20:24])[0]
        duration = struct.unpack(">Q", p[24:32])[0]
    elif p[0] == 0 and len(p) >= 20:
        timescale, duration = struct.unpack(">II", p[12:20])
    else:
        return None
    return duration / timescale if timescale else None


def _parse_tkhd(p: bytes) -> tuple[int, int] | None:
    """Return display (width, height) in pixels, accounting for 90/270 degree rotation."""
    if not p:
        return None
    matrix_off = 52 if p[0] == 1 else 40
    if len(p) < matrix_off + 36 + 8:
        return None
    a, b, _u, c, d = struct.unpack(">iiiii", p[matrix_off : matrix_off + 20])
    w, h = struct.unpack(">II", p[matrix_off + 36 : matrix_off + 44])
    w, h = w >> 16, h >> 16
    if w <= 0 or h <= 0:
        return None  # audio/other track
    if a == 0 and d == 0 and b != 0 and c != 0:
        w, h = h, w
    return w, h


def read_video_info(path: Path) -> VideoInfo | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            for typ, start, end in _top_level(f, size):
                if typ != b"moov":
                    continue
                if end - start > _MAX_MOOV:
                    return None
                f.seek(start)
                moov = f.read(end - start)
                break
            else:
                return None
    except OSError:
        return None

    duration: float | None = None
    dims: tuple[int, int] | None = None
    for typ, payload in _children(moov):
        if typ == b"mvhd":
            duration = _parse_mvhd(payload)
        elif typ == b"trak" and dims is None:
            for ctyp, cpayload in _children(payload):
                if ctyp == b"tkhd":
                    dims = _parse_tkhd(cpayload)
    if dims is None:
        return None
    return VideoInfo(dims[0], dims[1], duration)
