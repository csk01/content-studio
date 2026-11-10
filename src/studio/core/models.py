"""Plain domain types. No framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class Platform(StrEnum):
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


class Visibility(StrEnum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class TargetStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    NEEDS_REAUTH = "needs_reauth"


@dataclass(frozen=True)
class Credential:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: tuple[str, ...] = ()
    account_id: str | None = None  # e.g. Facebook Page id
    account_name: str | None = None

    def is_expired(self, skew_seconds: int = 60) -> bool:
        if self.expires_at is None:
            return False
        return (self.expires_at - datetime.now(UTC)).total_seconds() <= skew_seconds


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    size: int
    content_type: str = "video/mp4"
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None

    @property
    def is_vertical(self) -> bool | None:
        """True for portrait video; None when dimensions are unknown."""
        if self.width is None or self.height is None:
            return None
        return self.height > self.width


@dataclass(frozen=True)
class PublishRequest:
    title: str
    caption: str
    visibility: Visibility = Visibility.PRIVATE


@dataclass(frozen=True)
class PublishResult:
    platform_post_id: str
    url: str


@dataclass(frozen=True)
class PublishOutcome:
    target_id: str
    status: TargetStatus
    platform_post_id: str | None = None
    url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class HistoryRow:
    target_id: str
    platform: Platform
    title: str
    status: TargetStatus
    url: str | None
    error: str | None
    created_at: datetime
