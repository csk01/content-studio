# 12 — Facebook setup (Phase 0)

One-time steps *you* perform. Everything here is free (ADR 0002). Meta's console layout changes often, so labels may differ; the concepts do not.

## What you need
- A personal Facebook account.
- A **Facebook Page** that you administer (Reels publish to Pages only; personal profiles are not supported).
- A vertical test clip: `samples/test_vertical.mp4` (1080x1920, 5 s; Reels need 9:16, 3-90 s, at least 540x960).

## 1. Create the Meta app
1. Go to <https://developers.facebook.com/>, register as a developer (free), and **Create app**.
2. Pick the use case for managing a Page / "Other" → **Business** type, whichever offers **Facebook Login** and the Page permissions.
3. Add the **Facebook Login** product.
4. **Facebook Login → Settings → Valid OAuth Redirect URIs:** add exactly
   `http://localhost:8765/callback`
   (the port must match `STUDIO_FB_REDIRECT_PORT`, default 8765). Keep strict mode on.
5. **App settings → Basic:** copy the **App ID** and **App Secret**.
6. Leave the app in **Development mode**. You, as the app admin, can use it without App Review. Do not switch it Live.

### If login says "Invalid Scopes"
Facebook is rejecting the permission list because your app doesn't have the Page permissions. Either:
- **Add the Page use case:** Use cases -> Add use case -> "Manage everything on your Page", then Customize and add `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`. If it isn't offered, the app type is wrong; create a new **Business**-type app.
- **Or use Facebook Login for Business:** add that product, create a **Configuration** (token type: *User access token*; permissions: the three above), and set `STUDIO_FB_CONFIG_ID` to its id. The adapter then sends `config_id` instead of the permission list.

## 2. Configure and run (Command Prompt)
```bat
set STUDIO_FB_APP_ID=your_app_id
set STUDIO_FB_APP_SECRET=your_app_secret
rem optional, only if you manage several Pages:
set STUDIO_FB_PAGE_ID=1234567890

.venv\Scripts\studio auth facebook
.venv\Scripts\studio publish samples\test_vertical.mp4 --platform facebook --visibility public --caption "Studio test reel" --title "Studio test"
.venv\Scripts\studio history
```
- During consent, **select the Page** you want to publish to and grant all three permissions.
- Facebook posts are **public only**, so `--visibility public` is required. The CLI refuses otherwise. Delete the test Reel afterwards.
- If you administer several Pages and don't set `STUDIO_FB_PAGE_ID`, `studio auth` lists them and asks you to set it.

## 3. What the code does
- Login: standard OAuth code flow (Facebook has no PKCE; `state` protects against CSRF) → long-lived user token → **Page access token** via `/me/accounts`. Only the Page token is stored (OS keyring).
- Publish: `video_reels` start → resumable upload to `rupload.facebook.com` → finish with `video_state=PUBLISHED`, then a short status poll. Tokens travel in the `Authorization` header, never in URLs.
- Validation (before any upload): vertical, >= 540x960, 3-90 s, public visibility, non-empty caption.
- Logout deletes the local token. It cannot revoke at Facebook (only the user token could); remove the app under **Facebook Settings → Business Integrations** to fully revoke.

## 4. Known unknowns (verify with your first real run)
- Graph API version `v23.0` is pinned in `adapters/facebook.py`; bump it when Meta retires it.
- Whether the three permissions work in Development mode without App Review for an app admin (expected yes, unconfirmed).
- Whether Reels created by a Development-mode app are visible to the public or only to app roles. If only to you, that is expected until the app is reviewed and Live.
- Exact status-poll field names (`status.publishing_phase.status`). The code tolerates missing fields and reports success once Facebook has accepted the finish call; late processing failures are not detected until Phase 1 reconciliation.
- Limit: 30 API-published posts per Page per 24 h.

## 5. If it fails
| Message | Likely cause |
|---|---|
| Redirect URI error in browser | URI not whitelisted exactly, or the port differs |
| `No Facebook Page found...` | You didn't select a Page during consent, or lack content-creation rights |
| `code 190` / "re-authorize" | Token invalid or revoked: run `studio auth facebook` again |
| `code 200`-range / policy rejected | Missing permission or Page role, or Development-mode restriction |
| `code 368` | Facebook temporarily blocked the action for policy reasons |
| `Reels must be vertical` / `Duration ... outside` | Fails local validation before upload |
