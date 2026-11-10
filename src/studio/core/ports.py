"""Interfaces the engine depends on. Implementations live outside `core`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from studio.core.errors import Issue
from studio.core.models import (
    Credential,
    HistoryRow,
    MediaInfo,
    Platform,
    PublishRequest,
    PublishResult,
    TargetStatus,
)

# (bytes_sent, bytes_total)
ProgressSink = Callable[[int, int], None]


class PlatformAdapter(Protocol):
    platform: Platform
    redirect_host: str  # host used in the loopback redirect URI
    redirect_port: int  # 0 = any free port; some platforms require a fixed, pre-registered port

    def authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str: ...

    def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> Credential: ...

    def refresh(self, credential: Credential) -> Credential: ...

    def revoke(self, credential: Credential) -> None: ...

    def validate(self, media: MediaInfo, request: PublishRequest) -> list[Issue]: ...

    def publish(
        self,
        media: MediaInfo,
        request: PublishRequest,
        credential: Credential,
        progress: ProgressSink,
    ) -> PublishResult: ...


class TokenStore(Protocol):
    def load(self, platform: Platform) -> Credential | None: ...

    def save(self, platform: Platform, credential: Credential) -> None: ...

    def delete(self, platform: Platform) -> None: ...


class Repository(Protocol):
    def ensure_account(self, platform: Platform) -> str:
        """Return the id of the (single, Phase 0) connected account for the platform."""
        ...

    def create_post(self, title: str, caption: str, media: MediaInfo) -> str: ...

    def create_target(self, post_id: str, account_id: str) -> str: ...

    def set_status(
        self,
        target_id: str,
        status: TargetStatus,
        *,
        platform_post_id: str | None = None,
        url: str | None = None,
    ) -> None: ...

    def get_status(self, target_id: str) -> TargetStatus: ...

    def start_attempt(self, target_id: str) -> str: ...

    def finish_attempt(
        self,
        attempt_id: str,
        outcome: str,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def list_history(self, limit: int) -> list[HistoryRow]: ...

    def set_account_status(self, platform: Platform, status: str) -> None: ...


Clock = Callable[[], datetime]
