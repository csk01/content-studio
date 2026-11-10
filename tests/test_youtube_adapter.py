from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from studio.adapters.youtube import UPLOAD_URL, YouTubeAdapter
from studio.auth.loopback import make_pkce
from studio.core.errors import (
    AuthExpiredError,
    PolicyRejectedError,
    QuotaExceededError,
    RetryableError,
)
from studio.core.models import Credential, MediaInfo, PublishRequest

SESSION = "https://upload.example/session/1"
CRED = Credential("tok", "ref", None)
CHUNK = 256 * 1024


def adapter(handler, chunk=CHUNK):  # type: ignore[no-untyped-def]
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return YouTubeAdapter("cid", "csecret", http=http, chunk_size=chunk, sleep=lambda _s: None)


def media_of(path: Path) -> MediaInfo:
    return MediaInfo(path, path.stat().st_size)


REQ = PublishRequest("T", "caption")


def test_authorization_url_has_pkce_and_minimal_scope() -> None:
    a = adapter(lambda r: httpx.Response(200))
    _, challenge = make_pkce()
    q = parse_qs(urlparse(a.authorization_url("st", challenge, "http://127.0.0.1:1/callback")).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["https://www.googleapis.com/auth/youtube.upload"]
    assert q["access_type"] == ["offline"] and q["state"] == ["st"]


def test_refresh_keeps_refresh_token() -> None:
    a = adapter(lambda r: httpx.Response(200, json={"access_token": "new", "expires_in": 3600}))
    c = a.refresh(CRED)
    assert c.access_token == "new" and c.refresh_token == "ref" and c.expires_at


def test_refresh_invalid_grant_is_auth_expired() -> None:
    a = adapter(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(AuthExpiredError):
        a.refresh(CRED)


def test_upload_multi_chunk_success(mp4: Path) -> None:
    media = media_of(mp4)
    ranges: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        if str(r.url).startswith(UPLOAD_URL):
            assert r.headers["authorization"] == "Bearer tok"
            assert r.headers["x-upload-content-length"] == str(media.size)
            return httpx.Response(200, headers={"Location": SESSION})
        cr = r.headers["content-range"]
        ranges.append(cr)
        end = int(cr.split(" ")[1].split("-")[1].split("/")[0])
        if end + 1 >= media.size:
            return httpx.Response(200, json={"id": "VID1"})
        return httpx.Response(308, headers={"Range": f"bytes=0-{end}"})

    seen: list[tuple[int, int]] = []
    res = adapter(handler).publish(media, REQ, CRED, lambda s, t: seen.append((s, t)))
    assert res.platform_post_id == "VID1" and res.url.endswith("VID1")
    assert len(ranges) > 1 and seen[-1] == (media.size, media.size)


def test_upload_resumes_after_server_error(mp4: Path) -> None:
    media = media_of(mp4)
    state = {"failed": False}

    def handler(r: httpx.Request) -> httpx.Response:
        if str(r.url).startswith(UPLOAD_URL):
            return httpx.Response(200, headers={"Location": SESSION})
        cr = r.headers["content-range"]
        if cr.startswith("bytes */"):  # status query: server has the first chunk
            return httpx.Response(308, headers={"Range": f"bytes=0-{CHUNK - 1}"})
        start = int(cr.split(" ")[1].split("-")[0])
        end = int(cr.split("-")[1].split("/")[0])
        if start == CHUNK and not state["failed"]:
            state["failed"] = True
            return httpx.Response(503)
        if end + 1 >= media.size:
            return httpx.Response(200, json={"id": "VID2"})
        return httpx.Response(308, headers={"Range": f"bytes=0-{end}"})

    assert adapter(handler).publish(media, REQ, CRED, lambda s, t: None).platform_post_id == "VID2"
    assert state["failed"]


def test_upload_gives_up_with_retryable_error(mp4: Path) -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        if str(r.url).startswith(UPLOAD_URL):
            return httpx.Response(200, headers={"Location": SESSION})
        if r.headers["content-range"].startswith("bytes */"):
            return httpx.Response(308)
        return httpx.Response(503)

    with pytest.raises(RetryableError):
        adapter(handler).publish(media_of(mp4), REQ, CRED, lambda s, t: None)


@pytest.mark.parametrize(
    ("status", "reason", "exc"),
    [
        (401, "authError", AuthExpiredError),
        (403, "quotaExceeded", QuotaExceededError),
        (403, "forbidden", PolicyRejectedError),
    ],
)
def test_start_session_error_mapping(mp4: Path, status: int, reason: str, exc: type) -> None:
    body = {"error": {"message": "m", "errors": [{"reason": reason}]}}
    a = adapter(lambda r: httpx.Response(status, json=body))
    with pytest.raises(exc):
        a.publish(media_of(mp4), REQ, CRED, lambda s, t: None)


def test_validate_title_and_caption() -> None:
    a = adapter(lambda r: httpx.Response(200))
    m = MediaInfo(Path("x.mp4"), 10)
    assert a.validate(m, PublishRequest("ok", "fine")) == []
    assert a.validate(m, PublishRequest("", "fine"))
    assert a.validate(m, PublishRequest("x" * 101, "fine"))
    assert a.validate(m, PublishRequest("ok", "bad <tag>"))
    assert a.validate(m, PublishRequest("ok", "x" * 5001))
