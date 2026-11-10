"""YouTube adapter: OAuth 2.0 (PKCE) + YouTube Data API v3 resumable upload.

Uses plain httpx (injectable) rather than Google's client libraries so the protocol is
explicit and testable without network. Scope is the minimum needed: youtube.upload.
Note: uploads from unaudited API projects are forced private by YouTube (docs/09 Q1).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from studio.core.errors import (
    AuthExpiredError,
    Issue,
    PermanentError,
    PlatformError,
    PolicyRejectedError,
    QuotaExceededError,
    RetryableError,
)
from studio.core.models import (
    Credential,
    MediaInfo,
    Platform,
    PublishRequest,
    PublishResult,
)
from studio.core.ports import ProgressSink

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)

CHUNK_SIZE = 8 * 1024 * 1024  # must be a multiple of 256 KiB
MAX_FAILURES = 8
MAX_TITLE = 100
SHORTS_MAX_SECONDS = 180  # verify against current YouTube Help before relying on it
MAX_DESCRIPTION_BYTES = 5000
DEFAULT_CATEGORY_ID = "22"  # People & Blogs

_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "uploadLimitExceeded"}
_POLICY_REASONS = {
    "forbidden", "insufficientPermissions", "youtubeSignupRequired", "accountClosed",
    "accountSuspended", "forbiddenPrivacySetting", "invalidMetadata",
}


def _error_info(response: httpx.Response) -> tuple[str, str]:
    try:
        err = response.json().get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        return reason, err.get("message", "") or response.text[:200]
    except (ValueError, AttributeError):
        return "", response.text[:200]


def raise_for_response(response: httpx.Response) -> None:
    """Translate a failed YouTube API response into the normalized taxonomy."""
    code = response.status_code
    reason, message = _error_info(response)
    detail = f"YouTube API {code}" + (f" ({reason})" if reason else "") + f": {message}"
    if code == 401:
        raise AuthExpiredError(detail)
    if code == 403 and reason in _QUOTA_REASONS:
        raise QuotaExceededError(detail)
    if code == 403 or reason in _POLICY_REASONS:
        raise PolicyRejectedError(detail)
    if code == 429 or code >= 500:
        raise RetryableError(detail)
    raise PermanentError(detail)


class YouTubeAdapter:
    platform = Platform.YOUTUBE
    redirect_host = "127.0.0.1"
    redirect_port = 0

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
        chunk_size: int = CHUNK_SIZE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0, read=300.0))
        self._chunk_size = chunk_size
        self._sleep = sleep

    # -- OAuth ------------------------------------------------------------------------
    def authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",  # request a refresh token
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> Credential:
        data = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            }
        )
        return self._to_credential(data, previous_refresh=None)

    def refresh(self, credential: Credential) -> Credential:
        if not credential.refresh_token:
            raise AuthExpiredError("No refresh token stored; re-authorize")
        data = self._token_request(
            {"grant_type": "refresh_token", "refresh_token": credential.refresh_token}
        )
        return self._to_credential(data, previous_refresh=credential.refresh_token)

    def revoke(self, credential: Credential) -> None:
        token = credential.refresh_token or credential.access_token
        try:
            self._http.post(REVOKE_URL, data={"token": token})
        except httpx.HTTPError as exc:
            raise RetryableError(f"Could not reach Google to revoke token: {exc}") from exc

    def _token_request(self, fields: dict[str, str]) -> dict[str, Any]:
        body = {"client_id": self._client_id, "client_secret": self._client_secret, **fields}
        try:
            r = self._http.post(TOKEN_URL, data=body)
        except httpx.HTTPError as exc:
            raise RetryableError(f"Could not reach Google: {exc}") from exc
        if r.status_code == 200:
            data: dict[str, Any] = r.json()
            return data
        try:
            err = r.json()
        except ValueError:
            err = {}
        code = err.get("error", "")
        desc = err.get("error_description", r.text[:200])
        if code in {"invalid_grant", "invalid_client", "unauthorized_client"}:
            raise AuthExpiredError(f"Google rejected the credential ({code}): {desc}")
        if r.status_code >= 500:
            raise RetryableError(f"Google token endpoint {r.status_code}")
        raise PermanentError(f"Token request failed ({code}): {desc}")

    @staticmethod
    def _to_credential(data: dict[str, Any], previous_refresh: str | None) -> Credential:
        expires_in = int(data.get("expires_in", 3600))
        return Credential(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or previous_refresh,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scopes=tuple(str(data.get("scope", "")).split()),
        )

    # -- validation -------------------------------------------------------------------
    def validate(self, media: MediaInfo, request: PublishRequest) -> list[Issue]:
        issues: list[Issue] = []
        if not request.title.strip():
            issues.append(Issue("error", "A title is required (pass --title or write a caption)"))
        if len(request.title) > MAX_TITLE:
            issues.append(Issue("error", f"Title exceeds {MAX_TITLE} characters"))
        if len(request.caption.encode()) > MAX_DESCRIPTION_BYTES:
            issues.append(Issue("error", f"Caption exceeds {MAX_DESCRIPTION_BYTES} bytes"))
        if "<" in request.title + request.caption or ">" in request.title + request.caption:
            issues.append(Issue("error", "YouTube does not allow '<' or '>' in title/description"))
        if media.is_vertical is False:
            issues.append(
                Issue("warning", "Video is not vertical; YouTube will publish it as a normal "
                                 "video, not a Short")
            )
        elif (
            media.duration_seconds is not None and media.duration_seconds > SHORTS_MAX_SECONDS
        ):
            issues.append(
                Issue("warning", f"Video is longer than {SHORTS_MAX_SECONDS}s; "
                                 "it will not be a Short")
            )
        return issues

    # -- publishing -------------------------------------------------------------------
    def publish(
        self,
        media: MediaInfo,
        request: PublishRequest,
        credential: Credential,
        progress: ProgressSink,
    ) -> PublishResult:
        session_url = self._start_session(media, request, credential)
        video_id = self._upload(session_url, media, progress)
        return PublishResult(video_id, f"https://www.youtube.com/watch?v={video_id}")

    def _start_session(
        self, media: MediaInfo, request: PublishRequest, credential: Credential
    ) -> str:
        metadata = {
            "snippet": {
                "title": request.title,
                "description": request.caption,
                "categoryId": DEFAULT_CATEGORY_ID,
            },
            "status": {"privacyStatus": request.visibility.value},
        }
        headers = {
            "Authorization": f"Bearer {credential.access_token}",
            "X-Upload-Content-Length": str(media.size),
            "X-Upload-Content-Type": media.content_type,
        }
        try:
            r = self._http.post(
                UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                json=metadata,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise RetryableError(f"Could not reach YouTube: {exc}") from exc
        if r.status_code != 200:
            raise_for_response(r)
            raise PermanentError(f"Unexpected response starting upload: {r.status_code}")
        location = r.headers.get("Location")
        if not location:
            raise PermanentError("YouTube did not return an upload session URL")
        return location

    def _upload(self, session_url: str, media: MediaInfo, progress: ProgressSink) -> str:
        size = media.size
        offset = 0
        failures = 0
        progress(0, size)
        with media.path.open("rb") as f:
            while True:
                f.seek(offset)
                chunk = f.read(self._chunk_size)
                end = offset + len(chunk) - 1
                try:
                    r = self._http.put(
                        session_url,
                        content=chunk,
                        headers={"Content-Range": f"bytes {offset}-{end}/{size}"},
                    )
                except httpx.TransportError as exc:
                    failures = self._note_failure(failures, f"network error: {exc}")
                    offset, done = self._query_offset(session_url, size)
                    if done is not None:
                        return self._video_id(done, progress, size)
                    continue

                if r.status_code in (200, 201):
                    return self._video_id(r, progress, size)
                if r.status_code == 308:
                    offset = self._offset_from_range(r)
                    failures = 0
                    progress(offset, size)
                    continue
                if r.status_code in (500, 502, 503, 504):
                    failures = self._note_failure(failures, f"HTTP {r.status_code}")
                    offset, done = self._query_offset(session_url, size)
                    if done is not None:
                        return self._video_id(done, progress, size)
                    continue
                raise_for_response(r)
                raise PermanentError(f"Unexpected upload response: {r.status_code}")

    def _note_failure(self, failures: int, what: str) -> int:
        failures += 1
        if failures > MAX_FAILURES:
            raise RetryableError(f"Upload failed after {MAX_FAILURES} retries ({what})")
        self._sleep(min(2**failures, 30))
        return failures

    def _query_offset(self, session_url: str, size: int) -> tuple[int, httpx.Response | None]:
        """Ask YouTube how much it has. Returns (next_offset, completed_response_or_None)."""
        try:
            r = self._http.put(
                session_url, content=b"", headers={"Content-Range": f"bytes */{size}"}
            )
        except httpx.TransportError:
            return 0, None  # unknown; restarting from 0 is always safe for a resumable session
        if r.status_code in (200, 201):
            return size, r
        if r.status_code == 308:
            return self._offset_from_range(r), None
        raise_for_response(r)
        raise PermanentError(f"Unexpected status query response: {r.status_code}")

    @staticmethod
    def _offset_from_range(r: httpx.Response) -> int:
        rng = r.headers.get("Range")  # e.g. "bytes=0-8388607"
        if not rng:
            return 0
        return int(rng.rsplit("-", 1)[1]) + 1

    @staticmethod
    def _video_id(r: httpx.Response, progress: ProgressSink, size: int) -> str:
        try:
            video_id = r.json()["id"]
        except (ValueError, KeyError) as exc:
            raise PlatformError("Upload finished but YouTube returned no video id") from exc
        progress(size, size)
        return str(video_id)
