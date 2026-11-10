# 13 — Instagram setup (Phase 0)

One-time steps *you* perform. Free (ADR 0002). Instagram publishing goes through the **same Meta app** as Facebook (docs/12) using Facebook Login; no separate app or secret.

## What you need
- Everything from docs/12 (Meta app in Development mode, `STUDIO_FB_APP_ID` / `STUDIO_FB_APP_SECRET`, redirect URI `http://localhost:8765/callback`).
- An **Instagram Business or Creator account** (Instagram app → Settings → Account type) **linked to your Facebook Page** (Page → Settings → Linked accounts → Instagram). Personal Instagram accounts cannot publish via the API.
- Vertical test clip `samples/test_vertical.mp4`.

## Permissions
`instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`. In Development mode these work for app admins/testers without App Review. If login says "Invalid Scopes", add the Instagram use case to the app, or create a Facebook Login for Business configuration with these permissions and set `STUDIO_IG_CONFIG_ID`.

## Run
```bat
.venv\Scripts\studio auth instagram
.venv\Scripts\studio check samples\test_vertical.mp4 -p instagram
.venv\Scripts\studio publish samples\test_vertical.mp4 -p instagram --visibility public --caption "Studio test reel #test"
.venv\Scripts\studio history
```
During consent select the Page **and** the linked Instagram account. Delete the test Reel afterwards.

## What the code does
Create a REELS container with `upload_type=resumable` → upload bytes to `rupload.facebook.com` → poll `status_code` until `FINISHED` → `media_publish`. If processing is not finished in time, it reports a retryable error and publishes nothing. `media_publish` consumes the container, so a retry cannot double-post. A failed upload restarts from byte 0 (Instagram exposes no resume offset).

## Known unknowns (verify on first real run; also docs/09 Q4)
- Reels length/size limits: code enforces a conservative 3–90 s, 9:16, caption <= 2200 chars, <= 30 hashtags. Meta has been raising limits.
- Whether Development-mode Reels are publicly visible or only to app roles.
- Limit: ~100 API-published posts per account per 24 h.
- Graph version `v23.0` is shared with the Facebook adapter.

## If it fails
| Message | Likely cause |
|---|---|
| `No Instagram professional account is linked` | Account is personal, not linked to the Page, or not selected in consent |
| `Invalid Scopes` | See Permissions above |
| `code 190` | Token revoked/expired: `studio auth instagram` again |
| `could not process the video (ERROR)` | Codec/aspect/length rejected: re-encode H.264 + AAC, 9:16 |
| `still processing; nothing was published` | Retry in a minute; safe |
