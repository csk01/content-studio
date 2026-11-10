from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from test_mp4 import make_mp4

from studio.adapters.instagram import InstagramAdapter
from studio.auth.tokens import InMemoryTokenStore
from studio.core.errors import (
    AuthExpiredError,
    PermanentError,
    PolicyRejectedError,
    RetryableError,
)
from studio.core.models import (
    Credential,
    MediaInfo,
    Platform,
    PublishRequest,
    TargetStatus,
    Visibility,
)
from studio.core.service import PublishService
from studio.persistence.repo import SqlRepository

CRED = Credential("page-tok", None, None, account_id="IG1", account_name="me_ig")
UPLOAD = "https://rupload.facebook.com/ig-api-upload/v23.0/CONT1"
REQ = PublishRequest("Title", "Caption #one", Visibility.PUBLIC)


def adapter(handler, **kw):  # type: ignore[no-untyped-def]
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return InstagramAdapter("app", "secret", http=http, sleep=lambda _s: None, **kw)


def vertical(path: Path, seconds: float = 30, w: int = 1080, h: int = 1920) -> MediaInfo:
    return MediaInfo(path, path.stat().st_size, width=w, height=h, duration_seconds=seconds)


def test_authorization_url_uses_instagram_scopes() -> None:
    a = adapter(lambda r: httpx.Response(200))
    q = parse_qs(urlparse(a.authorization_url("st", "x", "http://localhost:8765/callback")).query)
    assert q["scope"] == [
        "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"
    ]
    assert a.platform is Platform.INSTAGRAM


def accounts_handler(pages):  # type: ignore[no-untyped-def]
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.path.endswith("/oauth/access_token"):
            token = "long" if "fb_exchange_token" in r.content.decode() else "short"
            return httpx.Response(200, json={"access_token": token})
        if r.url.path.endswith("/me/accounts"):
            assert "instagram_business_account" in r.url.params["fields"]
            return httpx.Response(200, json={"data": pages})
        return httpx.Response(404)

    return handler


IG_PAGE = {
    "id": "P1", "name": "Page", "access_token": "pt", "tasks": ["CREATE_CONTENT"],
    "instagram_business_account": {"id": "IG1", "username": "me_ig"},
}
PLAIN_PAGE = {"id": "P2", "name": "NoIG", "access_token": "pt2", "tasks": ["CREATE_CONTENT"]}


def test_exchange_code_returns_instagram_account() -> None:
    cred = adapter(accounts_handler([PLAIN_PAGE, IG_PAGE])).exchange_code("c", "v", "u")
    assert (cred.access_token, cred.account_id, cred.account_name) == ("pt", "IG1", "me_ig")


def test_no_linked_instagram_account() -> None:
    with pytest.raises(PolicyRejectedError, match="professional account"):
        adapter(accounts_handler([PLAIN_PAGE])).exchange_code("c", "v", "u")


def publish_handler(*, statuses=("FINISHED",), upload_status=200, publish_body=None):  # type: ignore[no-untyped-def]
    state: dict = {"calls": [], "container": None, "publish": None, "uploads": 0}
    polls = iter(statuses)

    def handler(r: httpx.Request) -> httpx.Response:
        path, url = r.url.path, str(r.url)
        state["calls"].append((r.method, path))
        if path.endswith("/IG1/media"):
            assert r.headers["authorization"] == "OAuth page-tok"
            state["container"] = parse_qs(r.content.decode())
            return httpx.Response(200, json={"id": "CONT1", "uri": UPLOAD})
        if url == UPLOAD:
            state["uploads"] += 1
            assert r.headers["offset"] == "0" and "file_size" in r.headers
            return httpx.Response(upload_status, json={"success": True})
        if path.endswith("/CONT1"):
            return httpx.Response(200, json={"status_code": next(polls, statuses[-1])})
        if path.endswith("/IG1/media_publish"):
            state["publish"] = parse_qs(r.content.decode())
            return httpx.Response(200, json=publish_body or {"id": "MEDIA7"})
        if path.endswith("/MEDIA7"):
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/AbC/"})
        return httpx.Response(404)

    return handler, state


def test_publish_happy_path(mp4: Path) -> None:
    handler, state = publish_handler(statuses=("IN_PROGRESS", "IN_PROGRESS", "FINISHED"))
    media = vertical(mp4)
    seen: list[tuple[int, int]] = []
    res = adapter(handler).publish(media, REQ, CRED, lambda s, t: seen.append((s, t)))
    assert res.platform_post_id == "MEDIA7"
    assert res.url == "https://www.instagram.com/reel/AbC/"
    assert state["container"]["media_type"] == ["REELS"]
    assert state["container"]["upload_type"] == ["resumable"]
    assert state["container"]["caption"] == ["Caption #one"]
    assert state["publish"]["creation_id"] == ["CONT1"]
    assert seen[-1] == (media.size, media.size)
    order = [p.rsplit("/", 1)[-1] for _m, p in state["calls"]]
    assert order.index("media_publish") > max(i for i, p in enumerate(order) if p == "CONT1")


def test_processing_error_blocks_publish(mp4: Path) -> None:
    handler, state = publish_handler(statuses=("ERROR",))
    with pytest.raises(PermanentError, match="ERROR"):
        adapter(handler).publish(vertical(mp4), REQ, CRED, lambda s, t: None)
    assert state["publish"] is None


def test_still_processing_is_retryable_and_publishes_nothing(mp4: Path) -> None:
    handler, state = publish_handler(statuses=("IN_PROGRESS",))
    with pytest.raises(RetryableError, match="nothing was published"):
        adapter(handler, poll_attempts=3).publish(vertical(mp4), REQ, CRED, lambda s, t: None)
    assert state["publish"] is None


def test_upload_failure_restarts_from_zero(mp4: Path) -> None:
    handler, state = publish_handler()
    inner = handler
    calls = {"n": 0}

    def flaky(r: httpx.Request) -> httpx.Response:
        if str(r.url) == UPLOAD:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503)
        return inner(r)

    adapter(flaky).publish(vertical(mp4), REQ, CRED, lambda s, t: None)
    assert state["uploads"] == 1 and calls["n"] == 2  # second attempt succeeded, offset 0


def test_permalink_failure_does_not_fail_publish(mp4: Path) -> None:
    handler, _ = publish_handler()

    def no_link(r: httpx.Request) -> httpx.Response:
        if r.url.path.endswith("/MEDIA7"):
            return httpx.Response(500)
        return handler(r)

    res = adapter(no_link).publish(vertical(mp4), REQ, CRED, lambda s, t: None)
    assert res.platform_post_id == "MEDIA7" and res.url.endswith("/reel/MEDIA7/")


def test_publish_requires_account(mp4: Path) -> None:
    with pytest.raises(AuthExpiredError):
        adapter(lambda r: httpx.Response(200)).publish(
            vertical(mp4), REQ, Credential("t", None, None), lambda s, t: None
        )


def test_validate_rules(tmp_path: Path) -> None:
    a = adapter(lambda r: httpx.Response(200))
    p = tmp_path / "x.mp4"

    def found(w, h, secs, req=REQ):  # type: ignore[no-untyped-def]
        media = MediaInfo(p, 1, width=w, height=h, duration_seconds=secs)
        return [(i.severity, i.message) for i in a.validate(media, req)]

    def has(items, word, severity="error"):  # type: ignore[no-untyped-def]
        return any(s == severity and word in m for s, m in items)

    assert found(1080, 1920, 30) == []
    assert has(found(1920, 1080, 30), "vertical")
    assert has(found(1080, 1920, 200), "Duration")
    assert has(found(1080, 1920, 1), "Duration")
    assert has(found(1080, 1400, 30), "Aspect", "warning")
    assert has(found(None, None, None), "Could not read", "warning")
    assert has(found(1080, 1920, 30, PublishRequest("t", "c", Visibility.PRIVATE)), "publicly")
    assert has(found(1080, 1920, 30, PublishRequest("t", " ", Visibility.PUBLIC)), "caption")
    assert has(found(1080, 1920, 30, PublishRequest("t", "x" * 2201, Visibility.PUBLIC)), "2200")
    tags = " ".join(f"#t{i}" for i in range(31))
    assert has(found(1080, 1920, 30, PublishRequest("t", tags, Visibility.PUBLIC)), "hashtags")


def test_end_to_end_through_publish_service(repo: SqlRepository, tmp_path: Path) -> None:
    """Engine + persistence + adapter together, network mocked."""
    video = make_mp4(tmp_path / "v.mp4", 1080, 1920, 10)
    handler, state = publish_handler()
    tokens = InMemoryTokenStore()
    svc = PublishService({Platform.INSTAGRAM: adapter(handler)}, tokens, repo)
    svc.connect(Platform.INSTAGRAM, CRED)
    outcome = svc.publish(video, Platform.INSTAGRAM, "Hello #reel", visibility=Visibility.PUBLIC)
    assert outcome.status is TargetStatus.PUBLISHED and outcome.platform_post_id == "MEDIA7"
    row = svc.history(5)[0]
    assert row.platform is Platform.INSTAGRAM and row.status is TargetStatus.PUBLISHED
    assert state["publish"] is not None
