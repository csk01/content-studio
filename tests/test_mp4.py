from __future__ import annotations

import struct
from pathlib import Path

import httpx

from studio.adapters.youtube import YouTubeAdapter
from studio.core.models import MediaInfo, PublishRequest
from studio.core.mp4 import read_video_info
from studio.core.validation import inspect_media


def box(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), typ) + payload


def mvhd(timescale: int, duration: int) -> bytes:
    body = b"\x00" * 4 + struct.pack(">IIII", 0, 0, timescale, duration) + b"\x00" * 80
    return box(b"mvhd", body)


def tkhd(w: int, h: int, rotate90: bool = False) -> bytes:
    one = 0x00010000
    matrix = (0, one, 0, -one, 0, 0, 0, 0, 0x40000000) if rotate90 else (
        one, 0, 0, 0, one, 0, 0, 0, 0x40000000)
    body = b"\x00" * 4 + b"\x00" * 8 + struct.pack(">II", 1, 0) + struct.pack(">I", 0)
    body += b"\x00" * 8 + b"\x00" * 8 + struct.pack(">9i", *matrix)
    body += struct.pack(">II", w << 16, h << 16)
    return box(b"tkhd", body)


def make_mp4(path: Path, w: int, h: int, seconds: int, rotate90: bool = False) -> Path:
    audio = box(b"trak", tkhd(0, 0))
    video = box(b"trak", tkhd(w, h, rotate90))
    moov = box(b"moov", mvhd(1000, seconds * 1000) + audio + video)
    path.write_bytes(box(b"ftyp", b"mp42\x00\x00\x00\x00") + box(b"mdat", b"\x00" * 1000) + moov)
    return path


def test_reads_dimensions_and_duration(tmp_path: Path) -> None:
    info = read_video_info(make_mp4(tmp_path / "a.mp4", 1080, 1920, 30))
    assert info and (info.width, info.height, info.duration_seconds) == (1080, 1920, 30.0)


def test_rotation_swaps_dimensions(tmp_path: Path) -> None:
    # phone footage is often stored landscape with a 90-degree rotation matrix
    info = read_video_info(make_mp4(tmp_path / "r.mp4", 1920, 1080, 5, rotate90=True))
    assert info and (info.width, info.height) == (1080, 1920)


def test_unparseable_file_is_unknown_not_invalid(mp4: Path) -> None:
    assert read_video_info(mp4) is None
    media, issues = inspect_media(mp4)
    assert media and media.is_vertical is None and issues == []


def test_inspect_media_fills_video_info(tmp_path: Path) -> None:
    media, issues = inspect_media(make_mp4(tmp_path / "v.mp4", 1080, 1920, 20))
    assert not issues and media and media.is_vertical is True


def test_youtube_warns_when_not_a_short(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    a = YouTubeAdapter("c", "s", http=httpx.Client(transport=transport))
    req = PublishRequest("t", "c")
    landscape = MediaInfo(tmp_path / "x.mp4", 1, width=1920, height=1080, duration_seconds=10)
    long_v = MediaInfo(tmp_path / "x.mp4", 1, width=1080, height=1920, duration_seconds=400)
    short_v = MediaInfo(tmp_path / "x.mp4", 1, width=1080, height=1920, duration_seconds=30)
    assert [i.severity for i in a.validate(landscape, req)] == ["warning"]
    assert [i.severity for i in a.validate(long_v, req)] == ["warning"]
    assert a.validate(short_v, req) == []
