"""Platform-independent input validation. Runs before any network or DB activity."""

from __future__ import annotations

from pathlib import Path

from studio.core.errors import Issue
from studio.core.models import MediaInfo
from studio.core.mp4 import read_video_info

MAX_TITLE_LEN = 100


def derive_title(caption: str) -> str:
    """Default title: first non-empty caption line, truncated (docs/09 Q15)."""
    for line in caption.splitlines():
        line = line.strip()
        if line:
            return line[:MAX_TITLE_LEN]
    return ""


def inspect_media(path: Path) -> tuple[MediaInfo | None, list[Issue]]:
    """Check that `path` is a readable, non-empty MP4. Never trusts the extension alone."""
    issues: list[Issue] = []
    if not path.exists():
        return None, [Issue("error", f"File not found: {path}")]
    if not path.is_file():
        return None, [Issue("error", f"Not a file: {path}")]
    if path.suffix.lower() != ".mp4":
        issues.append(Issue("error", "Only .mp4 files are supported"))
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            header = f.read(12)
    except OSError as exc:
        return None, [Issue("error", f"Cannot read file: {exc.strerror or exc}")]
    if size == 0:
        issues.append(Issue("error", "File is empty"))
    elif header[4:8] != b"ftyp":
        issues.append(Issue("error", "File does not look like an MP4 (missing 'ftyp' box)"))
    info = read_video_info(path) if not has_errors(issues) else None
    media = MediaInfo(
        path=path,
        size=size,
        width=info.width if info else None,
        height=info.height if info else None,
        duration_seconds=info.duration_seconds if info else None,
    )
    return media, issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
