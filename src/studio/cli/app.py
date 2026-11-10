from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from studio.auth.loopback import run_authorization
from studio.bootstrap import build_service
from studio.config import ConfigError, load_settings
from studio.core.errors import (
    NotAuthorizedError,
    PlatformError,
    PlatformNotConfiguredError,
    StudioError,
    ValidationFailedError,
)
from studio.core.models import Platform, TargetStatus, Visibility
from studio.core.service import PublishService

app = typer.Typer(help="Personalized Content Studio - Phase 0 CLI", no_args_is_help=True)

EXIT_FAILED = 1
EXIT_INVALID = 2
EXIT_REAUTH = 3

PlatformOpt = Annotated[Platform, typer.Argument(help="Target platform")]


def _service() -> PublishService:
    try:
        return build_service(load_settings())
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc


@app.command()
def auth(platform: PlatformOpt = Platform.YOUTUBE) -> None:
    """Authorize the app with the platform's official OAuth flow."""
    svc = _service()
    try:
        credential = run_authorization(svc.adapter(platform), announce=typer.echo)
    except PlatformNotConfiguredError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc
    except StudioError as exc:
        typer.secho(f"Authorization failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_FAILED) from exc
    svc.connect(platform, credential)
    where = f" ({credential.account_name})" if credential.account_name else ""
    typer.secho(f"Connected to {platform.value}{where}.", fg=typer.colors.GREEN)
    if credential.refresh_token is None:
        typer.secho(
            "Warning: no refresh token received; you may need to re-authorize soon.",
            fg=typer.colors.YELLOW,
        )


@app.command()
def publish(
    video: Annotated[Path, typer.Argument(help="Path to an MP4 file")],
    platform: Annotated[Platform, typer.Option("--platform", "-p")] = Platform.YOUTUBE,
    caption: Annotated[str | None, typer.Option("--caption", "-c")] = None,
    caption_file: Annotated[Path | None, typer.Option("--caption-file")] = None,
    title: Annotated[str | None, typer.Option(help="Defaults to the caption's first line")] = None,
    visibility: Annotated[
        Visibility, typer.Option(help="Defaults to private (see docs/09 Q16)")
    ] = Visibility.PRIVATE,
) -> None:
    """Publish VIDEO with a caption to PLATFORM."""
    if (caption is None) == (caption_file is None):
        typer.secho(
            "Provide exactly one of --caption or --caption-file.", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(EXIT_INVALID)
    text = caption if caption is not None else (caption_file or Path()).read_text(encoding="utf-8")

    svc = _service()
    try:
        issues = svc.check(video, platform, text, title, visibility)
    except PlatformNotConfiguredError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc
    for issue in issues:
        if issue.severity == "warning":
            typer.secho(f"  warning: {issue.message}", fg=typer.colors.YELLOW, err=True)
    bar_state = {"last": -1}

    def progress(sent: int, total: int) -> None:
        pct = int(sent * 100 / total) if total else 100
        if pct != bar_state["last"]:
            bar_state["last"] = pct
            typer.echo(f"\rUploading... {pct:3d}%", nl=False)

    try:
        outcome = svc.publish(
            video, platform, text, title=title, visibility=visibility, progress=progress
        )
    except ValidationFailedError as exc:
        for issue in exc.issues:
            typer.secho(f"  {issue.severity}: {issue.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc
    except PlatformNotConfiguredError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc
    except NotAuthorizedError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_REAUTH) from exc
    except PlatformError as exc:  # raised before a target exists (e.g. refresh at start)
        typer.secho(f"Publish failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_FAILED) from exc
    typer.echo("")

    if outcome.status is TargetStatus.PUBLISHED:
        typer.secho(f"Published ({visibility.value}): {outcome.url}", fg=typer.colors.GREEN)
        return
    typer.secho(f"Publish {outcome.status.value}: {outcome.error}", fg=typer.colors.RED, err=True)
    if outcome.status is TargetStatus.NEEDS_REAUTH:
        typer.echo(f"Run: studio auth {platform.value}", err=True)
        raise typer.Exit(EXIT_REAUTH)
    raise typer.Exit(EXIT_FAILED)


@app.command()
def check(
    video: Annotated[Path, typer.Argument(help="Path to an MP4 file")],
    platform: Annotated[Platform, typer.Option("--platform", "-p")] = Platform.YOUTUBE,
    caption: Annotated[str, typer.Option("--caption", "-c")] = "check",
    visibility: Annotated[Visibility, typer.Option()] = Visibility.PUBLIC,
) -> None:
    """Dry run: validate VIDEO against PLATFORM's rules. No login, no network, no upload."""
    svc = _service()
    try:
        issues = svc.check(video, platform, caption, None, visibility)
    except PlatformNotConfiguredError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_INVALID) from exc
    for issue in issues:
        colour = typer.colors.RED if issue.severity == "error" else typer.colors.YELLOW
        typer.secho(f"  {issue.severity}: {issue.message}", fg=colour)
    if any(i.severity == "error" for i in issues):
        raise typer.Exit(EXIT_INVALID)
    typer.secho(f"OK for {platform.value}.", fg=typer.colors.GREEN)


@app.command()
def history(limit: Annotated[int, typer.Option("--limit", "-n")] = 20) -> None:
    """List recent publish attempts."""
    rows = _service().history(limit)
    if not rows:
        typer.echo("No publish attempts yet.")
        return
    for r in rows:
        when = r.created_at.strftime("%Y-%m-%d %H:%M")
        detail = r.url or r.error or ""
        typer.echo(
            f"{when}  {r.platform.value:<9} {r.status.value:<13} {r.title[:40]:<40} {detail}"
        )


@app.command()
def logout(platform: PlatformOpt = Platform.YOUTUBE) -> None:
    """Revoke (best effort) and delete the stored credential."""
    _service().disconnect(platform)
    typer.echo(f"Disconnected from {platform.value}.")


if __name__ == "__main__":
    app()
