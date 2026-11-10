"""PublishService: the single entry point shells (CLI, API) call."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from studio.core.errors import (
    AuthExpiredError,
    Issue,
    NotAuthorizedError,
    PlatformError,
    PlatformNotConfiguredError,
    StudioError,
    ValidationFailedError,
)
from studio.core.models import (
    Credential,
    HistoryRow,
    Platform,
    PublishOutcome,
    PublishRequest,
    TargetStatus,
    Visibility,
)
from studio.core.ports import PlatformAdapter, ProgressSink, Repository, TokenStore
from studio.core.state import ensure_transition
from studio.core.validation import derive_title, has_errors, inspect_media


def _no_progress(_sent: int, _total: int) -> None:
    return None


class PublishService:
    def __init__(
        self,
        adapters: Mapping[Platform, PlatformAdapter],
        tokens: TokenStore,
        repo: Repository,
    ) -> None:
        self._adapters = adapters
        self._tokens = tokens
        self._repo = repo

    def adapter(self, platform: Platform) -> PlatformAdapter:
        try:
            return self._adapters[platform]
        except KeyError:
            raise PlatformNotConfiguredError(
                f"{platform.value} is not configured. See docs/ for its setup guide."
            ) from None

    # -- credentials ------------------------------------------------------------------
    def connect(self, platform: Platform, credential: Credential) -> None:
        self._tokens.save(platform, credential)
        self._repo.ensure_account(platform)
        self._repo.set_account_status(platform, "active")

    def disconnect(self, platform: Platform) -> None:
        """Best-effort revoke at the platform, then always delete the local credential."""
        credential = self._tokens.load(platform)
        if credential is not None:
            try:
                self.adapter(platform).revoke(credential)
            except StudioError:
                pass
        self._tokens.delete(platform)
        self._repo.set_account_status(platform, "revoked")

    # -- publishing -------------------------------------------------------------------
    def check(
        self, video: Path, platform: Platform, caption: str, title: str | None,
        visibility: Visibility = Visibility.PRIVATE,
    ) -> list[Issue]:
        """Validate without touching network or DB."""
        media, issues = inspect_media(video)
        if media is None:
            return issues
        request = PublishRequest(title or derive_title(caption), caption, visibility)
        return issues + self.adapter(platform).validate(media, request)

    def publish(
        self,
        video: Path,
        platform: Platform,
        caption: str,
        *,
        title: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        progress: ProgressSink = _no_progress,
    ) -> PublishOutcome:
        issues = self.check(video, platform, caption, title, visibility)
        if has_errors(issues):
            raise ValidationFailedError(issues)
        media, _ = inspect_media(video)
        assert media is not None  # check() would have reported otherwise

        adapter = self.adapter(platform)
        credential = self._tokens.load(platform)
        if credential is None:
            raise NotAuthorizedError(
                f"Not authorized for {platform.value}. Run: studio auth {platform.value}"
            )

        request = PublishRequest(title or derive_title(caption), caption, visibility)
        account_id = self._repo.ensure_account(platform)
        post_id = self._repo.create_post(request.title, caption, media)
        target_id = self._repo.create_target(post_id, account_id)
        self._transition(target_id, TargetStatus.QUEUED)
        attempt_id = self._repo.start_attempt(target_id)

        try:
            if credential.is_expired():
                credential = adapter.refresh(credential)
                self._tokens.save(platform, credential)
            self._transition(target_id, TargetStatus.UPLOADING)
            result = adapter.publish(media, request, credential, progress)
            self._transition(target_id, TargetStatus.PROCESSING)
            self._repo.set_status(
                target_id,
                TargetStatus.PUBLISHED,
                platform_post_id=result.platform_post_id,
                url=result.url,
            )
            self._repo.finish_attempt(attempt_id, "published")
            return PublishOutcome(
                target_id, TargetStatus.PUBLISHED, result.platform_post_id, result.url
            )
        except AuthExpiredError as exc:
            self._repo.set_account_status(platform, "needs_reauth")
            return self._fail(target_id, attempt_id, TargetStatus.NEEDS_REAUTH, exc)
        except PlatformError as exc:
            return self._fail(target_id, attempt_id, TargetStatus.FAILED, exc)
        except Exception as exc:  # unexpected: never leave a target stuck "uploading"
            self._fail(target_id, attempt_id, TargetStatus.FAILED, exc)
            raise

    def history(self, limit: int = 20) -> list[HistoryRow]:
        return self._repo.list_history(limit)

    # -- internals --------------------------------------------------------------------
    def _transition(self, target_id: str, new: TargetStatus) -> None:
        ensure_transition(self._repo.get_status(target_id), new)
        self._repo.set_status(target_id, new)

    def _fail(
        self, target_id: str, attempt_id: str, status: TargetStatus, exc: Exception
    ) -> PublishOutcome:
        self._transition(target_id, status)
        self._repo.finish_attempt(attempt_id, status.value, type(exc).__name__, str(exc))
        return PublishOutcome(target_id, status, error=str(exc))
