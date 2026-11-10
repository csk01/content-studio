from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from studio.core.models import HistoryRow, MediaInfo, Platform, TargetStatus
from studio.persistence.models import (
    ConnectedAccount,
    Post,
    PublishAttempt,
    PublishTarget,
)


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class SqlRepository:
    """Implements studio.core.ports.Repository."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_account(self, platform: Platform) -> str:
        with Session(self._engine) as s, s.begin():
            acct = s.scalar(
                select(ConnectedAccount).where(
                    ConnectedAccount.platform == platform.value,
                    ConnectedAccount.account_key == "default",
                )
            )
            if acct is None:
                acct = ConnectedAccount(id=_id(), platform=platform.value, account_key="default")
                s.add(acct)
            return acct.id

    def set_account_status(self, platform: Platform, status: str) -> None:
        with Session(self._engine) as s, s.begin():
            acct = s.scalar(
                select(ConnectedAccount).where(ConnectedAccount.platform == platform.value)
            )
            if acct is not None:
                acct.status = status

    def create_post(self, title: str, caption: str, media: MediaInfo) -> str:
        with Session(self._engine) as s, s.begin():
            post = Post(
                id=_id(), title=title, caption=caption,
                media_path=str(media.path), media_size=media.size,
            )
            s.add(post)
            return post.id

    def create_target(self, post_id: str, account_id: str) -> str:
        with Session(self._engine) as s, s.begin():
            t = PublishTarget(id=_id(), post_id=post_id, account_id=account_id, status="draft")
            s.add(t)
            return t.id

    def set_status(
        self,
        target_id: str,
        status: TargetStatus,
        *,
        platform_post_id: str | None = None,
        url: str | None = None,
    ) -> None:
        with Session(self._engine) as s, s.begin():
            t = s.get(PublishTarget, target_id)
            assert t is not None
            t.status = status.value
            t.updated_at = _now()
            if platform_post_id is not None:
                t.platform_post_id = platform_post_id
            if url is not None:
                t.url = url

    def get_status(self, target_id: str) -> TargetStatus:
        with Session(self._engine) as s:
            t = s.get(PublishTarget, target_id)
            assert t is not None
            return TargetStatus(t.status)

    def start_attempt(self, target_id: str) -> str:
        with Session(self._engine) as s, s.begin():
            a = PublishAttempt(id=_id(), target_id=target_id)
            s.add(a)
            return a.id

    def finish_attempt(
        self,
        attempt_id: str,
        outcome: str,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with Session(self._engine) as s, s.begin():
            a = s.get(PublishAttempt, attempt_id)
            assert a is not None
            a.finished_at = _now()
            a.outcome = outcome
            a.error_kind = error_kind
            a.error_message = error_message

    def list_history(self, limit: int) -> list[HistoryRow]:
        rows: list[HistoryRow] = []
        with Session(self._engine) as s:
            stmt = (
                select(PublishTarget, Post, ConnectedAccount)
                .join(Post, PublishTarget.post_id == Post.id)
                .join(ConnectedAccount, PublishTarget.account_id == ConnectedAccount.id)
                .order_by(PublishTarget.created_at.desc())
                .limit(limit)
            )
            for target, post, acct in s.execute(stmt):
                attempt = s.scalar(
                    select(PublishAttempt)
                    .where(PublishAttempt.target_id == target.id)
                    .order_by(PublishAttempt.started_at.desc())
                    .limit(1)
                )
                rows.append(
                    HistoryRow(
                        target_id=target.id,
                        platform=Platform(acct.platform),
                        title=post.title,
                        status=TargetStatus(target.status),
                        url=target.url,
                        error=attempt.error_message if attempt else None,
                        created_at=target.created_at,
                    )
                )
        return rows
