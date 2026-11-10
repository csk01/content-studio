"""Publishing lifecycle state machine (docs/04-architecture-overview.md)."""

from __future__ import annotations

from studio.core.errors import InvalidTransitionError
from studio.core.models import TargetStatus as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.QUEUED}),
    S.QUEUED: frozenset({S.UPLOADING, S.FAILED, S.NEEDS_REAUTH}),
    S.UPLOADING: frozenset({S.PROCESSING, S.FAILED, S.NEEDS_REAUTH}),
    S.PROCESSING: frozenset({S.PUBLISHED, S.FAILED}),
    S.PUBLISHED: frozenset(),
    S.FAILED: frozenset({S.QUEUED}),
    S.NEEDS_REAUTH: frozenset({S.QUEUED}),
}


def ensure_transition(current: S, new: S) -> None:
    if new not in TRANSITIONS[current]:
        raise InvalidTransitionError(f"Illegal transition {current.value} -> {new.value}")
