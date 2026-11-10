"""Composition root: wires the engine to concrete implementations."""

from __future__ import annotations

from studio.adapters.facebook import FacebookAdapter
from studio.adapters.instagram import InstagramAdapter
from studio.adapters.youtube import YouTubeAdapter
from studio.auth.tokens import KeyringTokenStore
from studio.config import ConfigError, Settings
from studio.core.models import Platform
from studio.core.ports import PlatformAdapter
from studio.core.service import PublishService
from studio.persistence.db import make_engine, upgrade
from studio.persistence.repo import SqlRepository


def build_service(settings: Settings) -> PublishService:
    settings.home.mkdir(parents=True, exist_ok=True)
    upgrade(settings.database_url)
    repo = SqlRepository(make_engine(settings.database_url))
    adapters: dict[Platform, PlatformAdapter] = {}
    if settings.has_youtube:
        adapters[Platform.YOUTUBE] = YouTubeAdapter(
            settings.youtube_client_id or "", settings.youtube_client_secret or ""
        )
    if settings.has_facebook:
        adapters[Platform.FACEBOOK] = FacebookAdapter(
            settings.facebook_app_id or "",
            settings.facebook_app_secret or "",
            page_id=settings.facebook_page_id,
            config_id=settings.facebook_config_id,
            redirect_port=settings.facebook_redirect_port,
        )
    if settings.has_instagram:
        adapters[Platform.INSTAGRAM] = InstagramAdapter(
            settings.facebook_app_id or "",
            settings.facebook_app_secret or "",
            page_id=settings.facebook_page_id,
            config_id=settings.instagram_config_id,
            redirect_port=settings.facebook_redirect_port,
        )
    if not adapters:
        raise ConfigError(
            "No platform configured. YouTube: set STUDIO_YT_CLIENT_SECRETS_FILE "
            "(docs/10-youtube-setup.md). Facebook: set STUDIO_FB_APP_ID and "
            "STUDIO_FB_APP_SECRET (docs/12-facebook-setup.md)."
        )
    return PublishService(adapters, KeyringTokenStore(), repo)
