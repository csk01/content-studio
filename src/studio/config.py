"""Settings from environment. Secrets never come from source code."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    home: Path
    youtube_client_id: str | None
    youtube_client_secret: str | None
    facebook_app_id: str | None = None
    facebook_app_secret: str | None = None
    facebook_page_id: str | None = None
    facebook_config_id: str | None = None
    facebook_redirect_port: int = 8765
    instagram_config_id: str | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.home / 'studio.db').as_posix()}"

    @property
    def has_youtube(self) -> bool:
        return bool(self.youtube_client_id and self.youtube_client_secret)

    @property
    def has_facebook(self) -> bool:
        return bool(self.facebook_app_id and self.facebook_app_secret)

    @property
    def has_instagram(self) -> bool:
        # Instagram publishing logs in through the same Meta app as Facebook.
        return self.has_facebook


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env
    home = Path(env.get("STUDIO_HOME") or Path.home() / ".studio")
    client_id = env.get("STUDIO_YT_CLIENT_ID")
    client_secret = env.get("STUDIO_YT_CLIENT_SECRET")

    secrets_file = env.get("STUDIO_YT_CLIENT_SECRETS_FILE")
    if secrets_file and not (client_id and client_secret):
        try:
            data = json.loads(Path(secrets_file).read_text(encoding="utf-8"))
            block = data.get("installed") or data.get("web") or {}
            client_id, client_secret = block["client_id"], block["client_secret"]
        except (OSError, ValueError, KeyError) as exc:
            raise ConfigError(f"Cannot read STUDIO_YT_CLIENT_SECRETS_FILE: {exc}") from exc
    try:
        fb_port = int(env.get("STUDIO_FB_REDIRECT_PORT") or 8765)
    except ValueError as exc:
        raise ConfigError("STUDIO_FB_REDIRECT_PORT must be a number") from exc
    return Settings(
        home,
        client_id,
        client_secret,
        facebook_app_id=env.get("STUDIO_FB_APP_ID"),
        facebook_app_secret=env.get("STUDIO_FB_APP_SECRET"),
        facebook_page_id=env.get("STUDIO_FB_PAGE_ID"),
        facebook_config_id=env.get("STUDIO_FB_CONFIG_ID"),
        facebook_redirect_port=fb_port,
        instagram_config_id=env.get("STUDIO_IG_CONFIG_ID"),
    )
