"""Instagram adapter: Reels via the Instagram Content Publishing API (Facebook Login).

Reuses the Facebook Login + Page-token plumbing: an Instagram *professional* (Business/Creator)
account must be linked to a Facebook Page, and the Page token authorizes publishing to it.

Flow (verify against current Meta docs):
  1. container: POST /{ig-user-id}/media  media_type=REELS, upload_type=resumable -> id, uri
  2. upload:    POST uri (rupload.facebook.com) with `offset` and `file_size` headers
  3. wait:      GET  /{container-id}?fields=status_code   until FINISHED
  4. publish:   POST /{ig-user-id}/media_publish  creation_id=<container-id> -> media id
  5. link:      GET  /{media-id}?fields=permalink

media_publish consumes the container, so retrying it can never double-post.
"""

from __future__ import annotations

import re

from studio.adapters.facebook import FacebookAdapter
from studio.core.errors import (
    AuthExpiredError,
    Issue,
    PermanentError,
    PlatformError,
    PolicyRejectedError,
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

SCOPES = (
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
)

MIN_SECONDS, MAX_SECONDS = 3.0, 90.0  # conservative; Meta has been raising the Reels limit
PORTRAIT_RATIO = 9 / 16
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
_HASHTAG = re.compile(r"(?<!\w)#\w+")


class InstagramAdapter(FacebookAdapter):
    platform = Platform.INSTAGRAM
    scopes = SCOPES
    page_fields = "id,name,access_token,tasks,instagram_business_account{id,username}"

    # -- OAuth (inherited login flow; credential targets the linked Instagram account) -------
    def _page_credential(self, user_token: str) -> Credential:
        pages = self._eligible_pages(user_token)
        linked = [p for p in pages if p.get("instagram_business_account")]
        if not linked:
            raise PolicyRejectedError(
                "No Instagram professional account is linked to your Page(s). Convert the "
                "Instagram account to Business/Creator and link it to the Page "
                "(docs/13-instagram-setup.md)."
            )
        page = self._choose_page(linked)
        ig = page["instagram_business_account"]
        return Credential(
            access_token=page["access_token"],
            refresh_token=None,
            expires_at=None,
            scopes=self.scopes,
            account_id=str(ig["id"]),
            account_name=ig.get("username") or page.get("name"),
        )

    # -- validation -------------------------------------------------------------------
    def validate(self, media: MediaInfo, request: PublishRequest) -> list[Issue]:
        issues: list[Issue] = []
        if request.visibility is not Visibility.PUBLIC:
            issues.append(
                Issue("error", "Instagram Reels publish publicly only; pass --visibility public")
            )
        caption = request.caption
        if not caption.strip():
            issues.append(Issue("error", "A caption is required"))
        if len(caption) > MAX_CAPTION:
            issues.append(Issue("error", f"Caption is {len(caption)} characters; "
                                         f"Instagram allows {MAX_CAPTION}"))
        if len(_HASHTAG.findall(caption)) > MAX_HASHTAGS:
            issues.append(Issue("error", f"Instagram allows at most {MAX_HASHTAGS} hashtags"))

        w, h, d = media.width, media.height, media.duration_seconds
        if w is None or h is None:
            issues.append(Issue("warning", "Could not read video dimensions; unable to verify "
                                           "Reels requirements (vertical 9:16)"))
        elif h <= w:
            issues.append(Issue("error", f"Reels must be vertical 9:16; video is {w}x{h}"))
        elif abs(w / h - PORTRAIT_RATIO) > 0.02:
            issues.append(Issue("warning", f"Aspect ratio is not 9:16 ({w}x{h}); "
                                           "Instagram may crop it"))
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
        token, ig_id = credential.access_token, credential.account_id
        if not ig_id:
            raise AuthExpiredError("Stored Instagram credential has no account; re-authorize")

        container = self._json(
            self._request(
                "POST", f"{self._graph}/{ig_id}/media", token=token,
                data={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": request.caption,
                },
            )
        )
        container_id, upload_url = container.get("id"), container.get("uri")
        if not container_id or not upload_url:
            raise PermanentError("Instagram did not return an upload session")
        container_id = str(container_id)

        self._upload(upload_url, container_id, media, token, progress)
        self._wait_for_container(container_id, token)

        published = self._json(
            self._request(
                "POST", f"{self._graph}/{ig_id}/media_publish", token=token,
                data={"creation_id": container_id},
            )
        )
        media_id = published.get("id")
        if not media_id:
            raise PermanentError("Instagram did not confirm the publish")
        media_id = str(media_id)
        return PublishResult(media_id, self._permalink(media_id, token))

    def _bytes_transferred(self, video_id: str, token: str) -> int:
        """Instagram exposes no resume offset; restart the upload from the beginning."""
        return 0

    def _wait_for_container(self, container_id: str, token: str) -> None:
        for attempt in range(self._poll_attempts):
            data = self._json(
                self._request(
                    "GET", f"{self._graph}/{container_id}", token=token,
                    params={"fields": "status_code,status"},
                )
            )
            code = data.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise PermanentError(
                    f"Instagram could not process the video ({code}): "
                    f"{data.get('status') or 'no detail given'}"
                )
            if attempt < self._poll_attempts - 1:
                self._sleep(3)
        raise RetryableError(
            "Instagram is still processing the video; nothing was published. Try again shortly."
        )

    def _permalink(self, media_id: str, token: str) -> str:
        """Best effort: the post is already live, so a failed lookup must not fail the publish."""
        try:
            data = self._json(
                self._request(
                    "GET", f"{self._graph}/{media_id}", token=token,
                    params={"fields": "permalink"},
                )
            )
        except PlatformError:
            return f"https://www.instagram.com/reel/{media_id}/"
        link = data.get("permalink")
        return str(link) if link else f"https://www.instagram.com/reel/{media_id}/"
