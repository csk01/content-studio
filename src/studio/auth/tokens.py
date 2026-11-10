"""Token stores. Tokens are secrets: never logged, never printed."""

from __future__ import annotations

import json
from datetime import datetime

import keyring
from keyring.errors import PasswordDeleteError

from studio.core.models import Credential, Platform

SERVICE_NAME = "content-studio"


def _dump(c: Credential) -> str:
    return json.dumps(
        {
            "access_token": c.access_token,
            "refresh_token": c.refresh_token,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "scopes": list(c.scopes),
            "account_id": c.account_id,
            "account_name": c.account_name,
        }
    )


def _load(raw: str) -> Credential:
    d = json.loads(raw)
    return Credential(
        access_token=d["access_token"],
        refresh_token=d.get("refresh_token"),
        expires_at=datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None,
        scopes=tuple(d.get("scopes", ())),
        account_id=d.get("account_id"),
        account_name=d.get("account_name"),
    )


class KeyringTokenStore:
    """Stores credentials in the OS keyring (Windows Credential Manager, macOS Keychain, ...)."""

    def load(self, platform: Platform) -> Credential | None:
        raw = keyring.get_password(SERVICE_NAME, platform.value)
        return _load(raw) if raw else None

    def save(self, platform: Platform, credential: Credential) -> None:
        keyring.set_password(SERVICE_NAME, platform.value, _dump(credential))

    def delete(self, platform: Platform) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, platform.value)
        except PasswordDeleteError:
            pass


class InMemoryTokenStore:
    """For tests."""

    def __init__(self) -> None:
        self._data: dict[Platform, Credential] = {}

    def load(self, platform: Platform) -> Credential | None:
        return self._data.get(platform)

    def save(self, platform: Platform, credential: Credential) -> None:
        self._data[platform] = credential

    def delete(self, platform: Platform) -> None:
        self._data.pop(platform, None)
