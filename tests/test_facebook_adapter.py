from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from studio.adapters.facebook import FacebookAdapter
from studio.core.errors import (
    AuthExpiredError,
    PermanentError,
    PolicyRejectedError,
    QuotaExceededError,
    RetryableError,
)
from studio.core.models import Credential, MediaInfo, PublishRequest, Visibility

CRED = Credential("page-tok", None, None, account_id="PAGE1", account_name="My Page")
UPLOAD = "https://rupload.facebook.com/video-upload/v23.0/VID9"
REQ = PublishRequest("Title", "Caption", Visibility.PUBLIC)


def adapter(handler, **kw):  # type: ignore[no-untyped-def]
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FacebookAdapter("app", "secret", http=http, sleep=lambda _s: None, **kw)


def vertical(path: Path, seconds: float = 30, w: int = 1080, h: int = 1920) -> MediaInfo:
    return MediaInfo(path, path.stat().st_size, width=w, height=h, duration_seconds=seconds)


def err(status: int, code: int, msg: str = "m") -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": msg, "code": code}})


def test_authorization_url() -> None:
    a = adapter(lambda r: httpx.Response(200))
    url = a.authorization_url("st", "ignored", "http://localhost:8765/callback")
    q = parse_qs(urlparse(url).query)
    assert "facebook.com/v23.0/dialog/oauth" in url and q["state"] == ["st"]
    assert q["scope"] == ["pages_show_list,pages_read_engagement,pages_manage_posts"]
    assert "code_challenge" not in q and a.redirect_port == 8765


def test_config_id_replaces_scope() -> None:
    a = adapter(lambda r: httpx.Response(200), config_id="CFG1")
    q = parse_qs(urlparse(a.authorization_url("st", "x", "http://localhost:8765/callback")).query)
    assert q["config_id"] == ["CFG1"] and "scope" not in q and q["response_type"] == ["code"]


def token_handler(pages):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        path = r.url.path
        calls.append(path)
        assert "secret" not in str(r.url) and "page-tok" not in str(r.url)  # never in URLs
        if path.endswith("/oauth/access_token"):
            body = r.content.decode()
            token = "long" if "fb_exchange_token" in body else "short"
            return httpx.Response(200, json={"access_token": token})
        if path.endswith("/me/accounts"):
            assert r.headers["authorization"] == "OAuth long"
            return httpx.Response(200, json={"data": pages})
        return httpx.Response(404)

    return handler, calls


PAGE_A = {"id": "A", "name": "Page A", "access_token": "ta", "tasks": ["CREATE_CONTENT"]}
PAGE_B = {"id": "B", "name": "Page B", "access_token": "tb", "tasks": ["CREATE_CONTENT"]}


def test_exchange_code_single_page() -> None:
    handler, calls = token_handler([PAGE_A])
    cred = adapter(handler).exchange_code("code", "v", "http://localhost:8765/callback")
    assert (cred.access_token, cred.account_id, cred.account_name) == ("ta", "A", "Page A")
    assert cred.refresh_token is None and not cred.is_expired()
    assert len([c for c in calls if c.endswith("access_token")]) == 2


def test_multiple_pages_requires_choice_then_selects() -> None:
    handler, _ = token_handler([PAGE_A, PAGE_B])
    with pytest.raises(PermanentError, match="STUDIO_FB_PAGE_ID"):
        adapter(handler).exchange_code("c", "v", "u")
    handler, _ = token_handler([PAGE_A, PAGE_B])
    assert adapter(handler, page_id="B").exchange_code("c", "v", "u").account_id == "B"


def test_no_eligible_page() -> None:
    no_task = {"id": "A", "name": "A", "access_token": "t", "tasks": ["ANALYZE"]}
    handler, _ = token_handler([no_task])
    with pytest.raises(PolicyRejectedError):
        adapter(handler).exchange_code("c", "v", "u")


def publish_handler(video_size: int, *, fail_first_upload: bool = False, status_body=None):  # type: ignore[no-untyped-def]
    state = {"uploads": 0, "offsets": [], "finish": None}

    def handler(r: httpx.Request) -> httpx.Response:
        url = str(r.url)
        if r.url.path.endswith("/PAGE1/video_reels"):
            assert r.headers["authorization"] == "OAuth page-tok"
            form = parse_qs(r.content.decode())
            if form["upload_phase"] == ["start"]:
                return httpx.Response(200, json={"video_id": "VID9", "upload_url": UPLOAD})
            state["finish"] = form
            return httpx.Response(200, json={"success": True})
        if url == UPLOAD:
            state["uploads"] += 1
            state["offsets"].append(int(r.headers["offset"]))
            assert r.headers["file_size"] == str(video_size)
            if fail_first_upload and state["uploads"] == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"success": True})
        if r.url.path.endswith("/VID9"):
            fields = r.url.params.get("fields")
            if fields == "status":  # resume query
                return httpx.Response(
                    200, json={"status": {"uploading_phase": {"bytes_transfered": 1000}}}
                )
            body = status_body or {
                "status": {"publishing_phase": {"status": "complete"}},
                "permalink_url": "/reel/VID9/",
            }
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return handler, state


def test_publish_happy_path(mp4: Path) -> None:
    media = vertical(mp4)
    handler, state = publish_handler(media.size)
    seen: list[tuple[int, int]] = []
    res = adapter(handler).publish(media, REQ, CRED, lambda s, t: seen.append((s, t)))
    assert res.platform_post_id == "VID9" and res.url == "https://www.facebook.com/reel/VID9/"
    assert state["finish"]["video_state"] == ["PUBLISHED"]
    assert state["finish"]["description"] == ["Caption"] and state["finish"]["title"] == ["Title"]
    assert seen[-1] == (media.size, media.size)


def test_upload_resumes_from_reported_offset(mp4: Path) -> None:
    media = vertical(mp4)
    handler, state = publish_handler(media.size, fail_first_upload=True)
    adapter(handler).publish(media, REQ, CRED, lambda s, t: None)
    assert state["offsets"] == [0, 1000]


def test_processing_error_is_reported_not_swallowed(mp4: Path) -> None:
    media = vertical(mp4)
    body = {"status": {"processing_phase": {"status": "error", "errors": [{"message": "bad"}]}}}
    handler, _ = publish_handler(media.size, status_body=body)
    with pytest.raises(PermanentError, match="processing phase failed"):
        adapter(handler).publish(media, REQ, CRED, lambda s, t: None)


def test_still_processing_after_polling_returns_success(mp4: Path) -> None:
    media = vertical(mp4)
    body = {"status": {"video_status": "processing"}}
    handler, _ = publish_handler(media.size, status_body=body)
    res = adapter(handler, poll_attempts=2).publish(media, REQ, CRED, lambda s, t: None)
    assert res.url.endswith("/reel/VID9")


def test_publish_requires_page_in_credential(mp4: Path) -> None:
    with pytest.raises(AuthExpiredError):
        adapter(lambda r: httpx.Response(200)).publish(
            vertical(mp4), REQ, Credential("t", None, None), lambda s, t: None
        )


@pytest.mark.parametrize(
    ("status", "code", "exc"),
    [
        (400, 190, AuthExpiredError),
        (400, 4, QuotaExceededError),
        (403, 200, PolicyRejectedError),
        (400, 368, PolicyRejectedError),
        (500, 2, RetryableError),
        (400, 100, PermanentError),
    ],
)
def test_error_mapping(mp4: Path, status: int, code: int, exc: type) -> None:
    a = adapter(lambda r: err(status, code))
    with pytest.raises(exc):
        a.publish(vertical(mp4), REQ, CRED, lambda s, t: None)


def test_validate_reels_rules(tmp_path: Path) -> None:
    a = adapter(lambda r: httpx.Response(200))
    p = tmp_path / "x.mp4"

    def msgs(w: int | None, h: int | None, secs: float | None, req: PublishRequest = REQ):  # type: ignore[no-untyped-def]
        media = MediaInfo(p, 1, width=w, height=h, duration_seconds=secs)
        return [(i.severity, i.message) for i in a.validate(media, req)]

    def has(found, word: str, severity: str = "error") -> bool:  # type: ignore[no-untyped-def]
        return any(s == severity and word in m for s, m in found)

    assert msgs(1080, 1920, 30) == []
    assert has(msgs(1920, 1080, 30), "vertical")
    assert has(msgs(360, 640, 30), "minimum")
    assert has(msgs(1080, 1920, 120), "Duration")
    assert has(msgs(1080, 1920, 1), "Duration")
    private = PublishRequest("t", "c", Visibility.PRIVATE)
    assert has(msgs(1080, 1920, 30, private), "publicly")
    assert has(msgs(None, None, None), "Could not read", "warning")  # unknown: warn, don't block
    assert has(msgs(1080, 1400, 30), "Aspect", "warning")
