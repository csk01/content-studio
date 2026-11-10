# 10 — YouTube setup (Phase 0)

One-time steps *you* perform in Google Cloud. Nothing here is automated, and no secrets go in the repo.

## 1. Google Cloud project
> Free. Do **not** enable billing; none is required for OAuth or the YouTube Data API (ADR 0002).

1. Open <https://console.cloud.google.com/> and create a project (e.g. `content-studio-dev`).
2. **APIs & Services → Library →** enable **YouTube Data API v3**.

## 2. OAuth consent screen
1. **APIs & Services → OAuth consent screen** (Google Auth platform in newer consoles).
2. User type **External**, app name, your email as support/developer contact.
3. Scopes: add `https://www.googleapis.com/auth/youtube.upload` (only this one).
4. Publishing status **Testing**; add your own Google account under **Test users**.
   - Testing mode refresh tokens expire after ~7 days — expect to run `studio auth` again weekly (docs/09 Q2).

## 3. OAuth client
1. **Credentials → Create credentials → OAuth client ID → Desktop app.**
2. Download the JSON. Save it **outside the repo** (or as `client_secret*.json`, which is git-ignored).

## 4. Configure and run
```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
$env:STUDIO_YT_CLIENT_SECRETS_FILE = "C:\path\to\client_secret.json"

.\.venv\Scripts\studio auth youtube
.\.venv\Scripts\studio publish .\clip.mp4 --caption "My first test" --title "Studio test"
.\.venv\Scripts\studio history
.\.venv\Scripts\studio logout youtube
```
Default visibility is **private**. Because this API project is unaudited, YouTube forces API uploads to private regardless (docs/09 Q1); that is expected, and the video is visible in YouTube Studio.

## 5. Known facts / findings (M0.1)
- Scope: `youtube.upload` (upload only; cannot read channel info, so the CLI does not show the channel name).
- Protocol: resumable upload (`uploadType=resumable`), implemented in `adapters/youtube.py`.
- Unaudited API projects (created after 2020-07-28): uploads locked private until a compliance audit.
- Quota: one fetch of Google's quota docs reported `videos.insert` at 1 unit with a default of 100 calls/day. **Unconfirmed** — check the Quotas page of your project.
- Tokens are stored in the OS keyring (Windows Credential Manager), not in files.
