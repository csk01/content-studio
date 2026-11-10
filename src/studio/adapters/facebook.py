"""Facebook adapter: Facebook Login (OAuth code flow) + Reels publishing to a Page.

Flow (Meta Reels Publishing API, verify against current docs):
  1. start:  POST /{page-id}/video_reels  upload_phase=start  -> video_id, upload_url
  2. upload: POST upload_url (rupload.facebook.com) with `offset` and `file_size` headers
  3. finish: POST /{page-id}/video_reels  upload_phase=finish, video_state=PUBLISHED

The credential is a *Page access token* (derived from a long-lived user token, so it does not
expire while the user's grant stays valid). Tokens go in the Authorization header, never in URLs.
Facebook Login does not support PKCE; the `state` parameter still protects against CSRF.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from studio.core.errors import (
    AuthExpiredError,
    Issue,
    PermanentError,
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
    Visibility,
)
from studio.core.ports import ProgressSink

GRAPH_VERSION = "v23.0"  # verify: Meta retires versions roughly every 2 years
SCOPES = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")

MIN_WIDTH, MIN_HEIGHT = 540, 960
MIN_SECONDS, MAX_SECONDS = 3.0, 90.0
PORTRAIT_RATIO = 9 / 16
STREAM_CHUNK = 1024 * 1024
MAX_FAILURES = 8

_QUOTA_CODES = {4, 17, 32, 341, 613}
_AUTH_CODES = {102, 190}
_RETRY_CODES = {1, 2}


def raise_for_response(response: httpx.Response) -> None:
    """Translate a failed Graph API response into the normalized taxonomy (always raises)."""
    status = response.status_code
    try:
        err = response.json().get("error", {})
    except (ValueError, AttributeError):
        err = {}
    code = err.get("code")
    message = err.get("message") or response.text[:200]
    detail = f"Facebook API {status}" + (f" (code {code})" if code else "") + f": {message}"
    if status == 401 or code in _AUTH_CODES:
        raise AuthExpiredError(detail)
    if code in _QUOTA_CODES:
        raise QuotaExceededError(detail)
    is_permission_code = isinstance(code, int) and (code in {10, 368} or 200 <= code < 300)
    if status == 403 or is_permission_code:
        raise PolicyRejectedError(detail)
    if status == 429 or status >= 500 or code in _RETRY_CODES:
        raise RetryableError(detail)
    raise PermanentError(detail)


class FacebookAdapter:
    platform = Platform.FACEBOOK
    redirect_host = "localhost"
    scopes: tuple[str, ...] = SCOPES
    page_fields = "id,name,access_token,tasks"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        page_id: str | None = None,
        config_id: str | None = None,
        redirect_port: int = 8765,
        http: httpx.Client | None = None,
        graph_version: str = GRAPH_VERSION,
        sleep: Callable[[float], None] = time.sleep,
        poll_attempts: int = 10,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._page_id = page_id
        self._config_id = config_id
        self.redirect_port = redirect_port
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0, read=300.0))
        self._graph = f"https://graph.facebook.com/{graph_version}"
        self._dialog = f"https://www.facebook.com/{graph_version}/dialog/oauth"
        self._sleep = sleep
        self._poll_attempts = poll_attempts

    # -- HTTP helper --------------------------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        content: Any = None,
    ) -> httpx.Response:
        hdrs = dict(headers or {})
        if token:
            hdrs["Authorization"] = f"OAuth {token}"
        try:
            r = self._http.request(
                method, url, data=data, params=params, headers=hdrs, content=content
            )
        except httpx.TransportError as exc:
            raise RetryableError(f"Could not reach Facebook: {exc}") from exc
        if not r.is_success:
            raise_for_response(r)
        return r

    def _json(self, r: httpx.Response) -> dict[str, Any]:
        try:
            data: dict[str, Any] = r.json()
        except ValueError as exc:
            raise PermanentError("Facebook returned a non-JSON response") from exc
        return data

    # -- OAuth ------------------------------------------------------------------------
    def authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str:
        del code_challenge  # Facebook Login has no PKCE
        params = {
            "client_id": self._app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
        }
        if self._config_id:
            # Facebook Login for Business: permissions come from a saved configuration.
            params["config_id"] = self._config_id
        else:
            params["scope"] = ",".join(self.scopes)
        return f"{self._dialog}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> Credential:
        del code_verifier
        short = self._token_call(
            {"redirect_uri": redirect_uri, "code": code}
        )["access_token"]
        long_lived = self._token_call(
            {"grant_type": "fb_exchange_token", "fb_exchange_token": short}
        )["access_token"]
        return self._page_credential(long_lived)

    def _token_call(self, fields: dict[str, str]) -> dict[str, Any]:
        body = {"client_id": self._app_id, "client_secret": self._app_secret, **fields}
        try:
            r = self._http.post(f"{self._graph}/oauth/access_token", data=body)
        except httpx.TransportError as exc:
            raise RetryableError(f"Could not reach Facebook: {exc}") from exc
        if not r.is_success:
            raise_for_response(r)
        data = self._json(r)
        if "access_token" not in data:
            raise PermanentError("Facebook did not return an access token")
        return data

    def _eligible_pages(self, user_token: str) -> list[dict[str, Any]]:
        r = self._request(
            "GET", f"{self._graph}/me/accounts", token=user_token,
            params={"fields": self.page_fields, "limit": "100"},
        )
        pages = [
            p for p in self._json(r).get("data", [])
            if "access_token" in p and ("tasks" not in p or "CREATE_CONTENT" in p["tasks"])
        ]
        if not pages:
            raise PolicyRejectedError(
                "No Facebook Page found where you can create content. You must be an admin or "
                "editor of a Page, and must select that Page during consent."
            )
        return pages

    def _choose_page(self, pages: list[dict[str, Any]]) -> dict[str, Any]:
        if self._page_id:
            pages = [p for p in pages if p["id"] == self._page_id]
            if not pages:
                raise PolicyRejectedError(
                    f"Page {self._page_id} is not available to this login "
                    "(was it selected during consent?)"
                )
        elif len(pages) > 1:
            listing = ", ".join(f"{p['name']} ({p['id']})" for p in pages)
            raise PermanentError(
                f"Multiple Pages available: {listing}. Set STUDIO_FB_PAGE_ID to choose one."
            )
        return pages[0]

    def _page_credential(self, user_token: str) -> Credential:
        page = self._choose_page(self._eligible_pages(user_token))
        return Credential(
            access_token=page["access_token"],
            refresh_token=None,
            expires_at=None,
            scopes=self.scopes,
            account_id=str(page["id"]),
            account_name=page.get("name"),
        )

    def refresh(self, credential: Credential) -> Credential:
        # Page tokens derived from a long-lived user token do not expire on a timer.
        raise AuthExpiredError("Facebook token is no longer valid; re-authorize")

    def revoke(self, credential: Credential) -> None:
        """No-op: only a user token can revoke the grant, and we keep only the Page token.

        The local credential is deleted by the caller. To fully revoke, remove the app under
        Facebook Settings > Business Integrations.
        """
        return None

    # -- validation -------------------------------------------------------------------
    def validate(self, media: MediaInfo, request: PublishRequest) -> list[Issue]:
        issues: list[Issue] = []
        if request.visibility is not Visibility.PUBLIC:
            issues.append(
                Issue("error", "Facebook Reels publish publicly only; pass --visibility public")
            )
        if not request.caption.strip():
            issues.append(Issue("error", "A caption is required"))

        w, h, d = media.width, media.height, media.duration_seconds
        if w is None or h is None:
            issues.append(Issue("warning", "Could not read video dimensions; unable to verify "
                                           "Reels requirements (9:16, at least 540x960)"))
        else:
            if h <= w:
                issues.append(Issue("error", f"Reels must be vertical 9:16; video is {w}x{h}"))
            else:
                if abs(w / h - PORTRAIT_RATIO) > 0.02:
                    issues.append(Issue("warning", f"Aspect ratio is not 9:16 ({w}x{h}); "
                                                   "Facebook may crop or reject it"))
                if w < MIN_WIDTH or h < MIN_HEIGHT:
                    issues.append(Issue("error", f"Resolution {w}x{h} is below the Reels "
                                                 f"minimum {MIN_WIDTH}x{MIN_HEIGHT}"))
        if d is not None and not (MIN_SECONDS <= d <= MAX_SECONDS):
            issues.append(Issue("error", f"Duration {d:.1f}s is outside the Reels range "
                                         f"{MIN_SECONDS:.0f}-{MAX_SECONDS:.0f}s"))
        return issues

    # -- publishing -------------------------------------------------------------------
    def publish(
        self,
        media: MediaInfo,
        request: PublishRequest,
        credential: Credential,
        progress: ProgressSink,
    ) -> PublishResult:
        token, page_id = credential.access_token, credential.account_id
        if not page_id:
            raise AuthExpiredError("Stored Facebook credential has no Page; re-authorize")
        reels = f"{self._graph}/{page_id}/video_reels"

        start = self._json(
            self._request("POST", reels, token=token, data={"upload_phase": "start"})
        )
        video_id, upload_url = start.get("video_id"), start.get("upload_url")
        if not video_id or not upload_url:
            raise PermanentError("Facebook did not return an upload session")
        video_id = str(video_id)

        self._upload(upload_url, video_id, media, token, progress)

        finish = self._json(
            self._request(
                "POST", reels, token=token,
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "description": request.caption,
                    "title": request.title,
                },
            )
        )
        if finish.get("success") is False:
            raise PermanentError("Facebook rejected the publish request")

        permalink = self._wait_until_published(video_id, token)
        return PublishResult(video_id, permalink or f"https://www.facebook.com/reel/{video_id}")

    def _upload(
        self, upload_url: str, video_id: str, media: MediaInfo, token: str, progress: ProgressSink
    ) -> None:
        size = media.size
        offset = 0
        failures = 0
        progress(0, size)
        while True:
            headers = {
                "Authorization": f"OAuth {token}",
                "offset": str(offset),
                "file_size": str(size),
                "Content-Length": str(size - offset),
            }
            try:
                r = self._http.post(
                    upload_url, headers=headers,
                    content=self._stream(media.path, offset, size, progress),
                )
            except httpx.TransportError as exc:
                failures = self._note_failure(failures, f"network error: {exc}")
                offset = self._bytes_transferred(video_id, token)
                continue
            if r.is_success:
                progress(size, size)
                return
            if r.status_code >= 500:
                failures = self._note_failure(failures, f"HTTP {r.status_code}")
                offset = self._bytes_transferred(video_id, token)
                continue
            raise_for_response(r)

    @staticmethod
    def _stream(path: Path, offset: int, size: int, progress: ProgressSink) -> Iterator[bytes]:
        sent = offset
        with path.open("rb") as f:
            f.seek(offset)
            while chunk := f.read(STREAM_CHUNK):
                sent += len(chunk)
                progress(sent, size)
                yield chunk

    def _note_failure(self, failures: int, what: str) -> int:
        failures += 1
        if failures > MAX_FAILURES:
            raise RetryableError(f"Upload failed after {MAX_FAILURES} retries ({what})")
        self._sleep(min(2**failures, 30))
        return failures

    def _bytes_transferred(self, video_id: str, token: str) -> int:
        """Ask Facebook how many bytes it has; 0 (restart) if unknown."""
        try:
            r = self._http.get(
                f"{self._graph}/{video_id}", params={"fields": "status"},
                headers={"Authorization": f"OAuth {token}"},
            )
            phase = r.json().get("status", {}).get("uploading_phase", {})
            # Meta's field name is spelled "bytes_transfered" in its docs; accept both.
            value = phase.get("bytes_transfered", phase.get("bytes_transferred", 0))
            return int(value)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return 0

    def _wait_until_published(self, video_id: str, token: str) -> str | None:
        """Poll briefly for a definite error or completion. Returns a permalink if known.

        If still processing when polling ends, the publish call was already accepted, so we
        report success; Phase 1 reconciliation (check_status) covers late failures.
        """
        permalink: str | None = None
        for attempt in range(self._poll_attempts):
            r = self._request(
                "GET", f"{self._graph}/{video_id}", token=token,
                params={"fields": "status,permalink_url"},
            )
            data = self._json(r)
            link = data.get("permalink_url")
            if link:
                permalink = link if link.startswith("http") else f"https://www.facebook.com{link}"
            status = data.get("status", {}) or {}
            for phase_name in ("uploading_phase", "processing_phase", "publishing_phase"):
                phase = status.get(phase_name) or {}
                if phase.get("status") == "error":
                    raise PermanentError(
                        f"Facebook {phase_name.replace('_', ' ')} failed: "
                        f"{phase.get('errors') or 'unknown error'}"
                    )
            if status.get("video_status") == "error":
                raise PermanentError("Facebook failed to process the video")
            publishing = status.get("publishing_phase") or {}
            if publishing.get("status") == "complete" or status.get("video_status") == "ready":
                return permalink
            if attempt < self._poll_attempts - 1:
                self._sleep(3)
        return permalink
