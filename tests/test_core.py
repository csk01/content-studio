from __future__ import annotations

from pathlib import Path

import pytest

from studio.auth.tokens import InMemoryTokenStore
from studio.core.errors import (
    AuthExpiredError,
    InvalidTransitionError,
    Issue,
    NotAuthorizedError,
    QuotaExceededError,
    ValidationFailedError,
)
from studio.core.models import (
    Credential,
    MediaInfo,
    Platform,
    PublishRequest,
    PublishResult,
    TargetStatus,
)
from studio.core.service import PublishService
from studio.core.state import ensure_transition
from studio.core.validation import derive_title, inspect_media

CRED = Credential("tok", "ref", None)


class FakeAdapter:
    platform = Platform.YOUTUBE
    redirect_host = "127.0.0.1"
    redirect_port = 0

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published = 0
        self.refreshed = 0

    def authorization_url(self, state, code_challenge, redirect_uri):  # type: ignore[no-untyped-def]
        return "http://x"

    def exchange_code(self, code, code_verifier, redirect_uri):  # type: ignore[no-untyped-def]
        return CRED

    def refresh(self, credential):  # type: ignore[no-untyped-def]
        self.refreshed += 1
        return CRED

    def revoke(self, credential):  # type: ignore[no-untyped-def]
        return None

    def validate(self, media: MediaInfo, request: PublishRequest) -> list[Issue]:
        return []

    def publish(self, media, request, credential, progress):  # type: ignore[no-untyped-def]
        if self.error:
            raise self.error
        self.published += 1
        progress(media.size, media.size)
        return PublishResult("abc123", "https://youtu.be/abc123")


def make_service(repo, adapter=None, with_token=True):  # type: ignore[no-untyped-def]
    tokens = InMemoryTokenStore()
    if with_token:
        tokens.save(Platform.YOUTUBE, CRED)
    adapter = adapter or FakeAdapter()
    return PublishService({Platform.YOUTUBE: adapter}, tokens, repo), adapter


def test_state_machine_rejects_illegal_transition() -> None:
    ensure_transition(TargetStatus.QUEUED, TargetStatus.UPLOADING)
    with pytest.raises(InvalidTransitionError):
        ensure_transition(TargetStatus.PUBLISHED, TargetStatus.QUEUED)
    with pytest.raises(InvalidTransitionError):
        ensure_transition(TargetStatus.DRAFT, TargetStatus.PUBLISHED)


def test_derive_title() -> None:
    assert derive_title("\n  Hello world \nmore") == "Hello world"
    assert len(derive_title("x" * 300)) == 100


def test_inspect_media_rules(tmp_path: Path, mp4: Path) -> None:
    media, issues = inspect_media(mp4)
    assert media and not issues
    _, issues = inspect_media(tmp_path / "missing.mp4")
    assert issues[0].severity == "error"
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video at all")
    assert any("ftyp" in i.message for i in inspect_media(fake)[1])
    mov = tmp_path / "a.mov"
    mov.write_bytes(b"\x00\x00\x00\x18ftypqt  ")
    assert any("mp4" in i.message for i in inspect_media(mov)[1])
    empty = tmp_path / "e.mp4"
    empty.write_bytes(b"")
    assert any("empty" in i.message for i in inspect_media(empty)[1])


def test_publish_success_records_history(repo, mp4: Path) -> None:  # type: ignore[no-untyped-def]
    svc, adapter = make_service(repo)
    out = svc.publish(mp4, Platform.YOUTUBE, "My caption\nbody")
    assert out.status is TargetStatus.PUBLISHED and out.url
    assert adapter.published == 1
    rows = svc.history()
    assert rows[0].status is TargetStatus.PUBLISHED and rows[0].title == "My caption"


def test_invalid_file_fails_before_any_side_effect(repo, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    svc, adapter = make_service(repo)
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"junk")
    with pytest.raises(ValidationFailedError):
        svc.publish(bad, Platform.YOUTUBE, "c")
    assert adapter.published == 0 and svc.history() == []


def test_no_credential(repo, mp4: Path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make_service(repo, with_token=False)
    with pytest.raises(NotAuthorizedError):
        svc.publish(mp4, Platform.YOUTUBE, "c")


def test_auth_error_sets_needs_reauth(repo, mp4: Path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make_service(repo, FakeAdapter(AuthExpiredError("revoked")))
    out = svc.publish(mp4, Platform.YOUTUBE, "c")
    assert out.status is TargetStatus.NEEDS_REAUTH
    assert svc.history()[0].error == "revoked"


def test_platform_error_marks_failed_not_published(repo, mp4: Path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make_service(repo, FakeAdapter(QuotaExceededError("quota")))
    out = svc.publish(mp4, Platform.YOUTUBE, "c")
    assert out.status is TargetStatus.FAILED and out.url is None


def test_unexpected_error_never_leaves_target_stuck(repo, mp4: Path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make_service(repo, FakeAdapter(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        svc.publish(mp4, Platform.YOUTUBE, "c")
    assert svc.history()[0].status is TargetStatus.FAILED


def test_disconnect_deletes_credential(repo) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make_service(repo)
    svc.disconnect(Platform.YOUTUBE)
    assert svc._tokens.load(Platform.YOUTUBE) is None  # noqa: SLF001
