# 09 — Open Questions and Recommendations

Nothing here is decided. Each item has a recommendation; confirm or override, then move the result into an ADR and mark it resolved.

Platform facts below come from general knowledge and **must be verified against current official documentation** before relying on them (policies change often). No integration work has started.

| # | Question | Recommendation | Needed by |
|---|---|---|---|
| Q1 | **YouTube:** Does the Data API `videos.insert` (resumable upload) work for our use? What is the quota cost per upload and default daily quota? Do uploads from unaudited API projects get forced to private? | Verify first in Phase 0. If unverified apps are restricted, plan the compliance audit early and use test channel(s) meanwhile. | M0.1 |
| Q2 | **YouTube OAuth consent:** Sensitive scopes require Google OAuth app verification; "Testing" mode limits users and expires refresh tokens (~7 days). | Use Testing mode with the developer's own account for Phase 0; begin verification before Phase 1 external users. | M0.3 |
| Q3 | **Facebook:** Which publishing API for video/Reels to Pages? Required permissions (e.g. page posting permissions), Business Verification, App Review, Page-role requirements? Can personal profiles be posted to? | Assume **Pages only**; personal-profile posting is likely unavailable. Validate before committing. | Before M1.7 |
| Q4 | **Instagram:** Content Publishing requires professional (Business/Creator) account, usually linked to a Facebook Page; Reels constraints (length, aspect, codec). | Document eligibility; fail early in connect flow with explanatory message. Validate. | Before M1.8 |
| Q5 | **Meta media ingestion:** Does the flow require a publicly accessible video URL, or is direct/resumable upload supported? | Prefer resumable direct upload if offered; otherwise short-lived signed URL from our own server. Decide via ADR. | Before M1.7 |
| Q6 | **Client secret in a distributed CLI** | Phase 0 is for the developer; use env-provided credentials. Revisit if the CLI is distributed. | M0.3 |
| Q7 | Tech confirmation: Typer/FastAPI/Next.js/SQLAlchemy/Alembic | Accept as proposed. ADR 0001 captures it as *proposed*. | Start of coding |
| Q8 | Web session mechanism (server-side session vs JWT) | Server-side sessions in HttpOnly cookies. | M1.1 |
| Q9 | Email delivery for verification/reset (provider?) | Must respect the zero-cost policy (ADR 0002): self-hosted SMTP or a free-tier provider only after approval; console logging in dev. | M1.1 |
| Q10 | Max video size/duration to support in Phase 1 | Start with the strictest common limit among enabled platforms; measure. | M1.3 |
| Q11 | Media retention after successful publish | Keep until user deletes; revisit for storage cost. | M1.3 |
| Q12 | Hosting for Phase 1 (VM vs PaaS; region) | Default to local/self-hosted (free). Public hosting may cost money and is outside the zero-cost guarantee; ask before adopting. GCP/GCS optional. | M1.6 |
| Q13 | Launch geography / legal (privacy policy, terms, GDPR) | Get minimal legal review before inviting external users. | M1.6 |
| Q14 | Should Phase 1 ship YouTube-only if FB/IG review is slow? | Yes — decouple release from review timelines. | M1.6 |
| Q15 | Does Phase 1 allow per-destination caption/title overrides? YouTube needs a title; where does it come from? | Add an explicit optional title field (defaults to caption's first line, truncated). Needs user confirmation. | M0.2 |
| Q16 | Default YouTube privacy status for Phase 0 publishes | Default `private`/unlisted until user opts into public. | M0.4 |
| Q18 | Which open-source license should this project itself use? | Permissive (MIT or Apache-2.0) for maximum adoption; AGPL-3.0 if modifications to hosted forks should be shared back. No LICENSE file is added until you choose. | Before publishing the repo |
| Q17 | Is Phase 0 a throwaway or the seed of the codebase? | Seed: engine/adapter kept; CLI remains as a dev tool. | M0.2 |

## Resolved (provisionally, in Phase 0 code)
- Q15: `--title` optional; defaults to the caption's first line, max 100 chars.
- Q16: default visibility `private`.
- Q1 (partly): unaudited projects force uploads private (confirmed by Google's Videos resource docs); quota figures still to confirm in Cloud Console.
- Q6: Phase 0 reads the client from env or the downloaded JSON; revisit before distributing the CLI.

## Findings log
### 2026-11-07 — Content format decision (from the user)
All creator videos are vertical short-form (Shorts, Facebook Reels, Instagram Reels). Common-denominator rules to design around: 9:16, <= 90 s for Facebook Reels (the strictest known); Instagram Reels limits still to be verified; YouTube Shorts length limit (believed ~3 min) to be verified. Recommendation: treat 9:16 and <= 90 s as the default "safe for all three" profile and show per-platform eligibility.
### 2026-11-07 — Facebook feasibility (from Meta's Reels Publishing docs; re-verify before building)
- Endpoint: `POST /{page-id}/video_reels` with `upload_phase=start|finish`; bytes go to `rupload.facebook.com/video-upload/{video-id}` (resumable via `offset`). **Local file upload works; no public URL needed** (Q5: resolved for Facebook; Instagram still open).
- Permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`; needs a Page access token from a user who can create content on the Page. **Pages only, public only** (Q3: personal profiles not possible).
- Reel specs: 9:16, 540x960 min (1080x1920 recommended), 3-90 s, 24-60 fps fixed, AAC audio. A 16:9 clip will be rejected, so adapter validation must check this.
- Limit: 30 API-published posts per 24 h per Page.
- **Unconfirmed:** whether App Review / Business Verification is needed, and whether a development-mode app can publish only for app admins/testers. Test with our own Page first.
### 2026-11-07 — YouTube public visibility
- Google's reference: unaudited projects (created after 2020-07-28) are forced private; `privacyStatus=public` does not override it. Only a project-level compliance audit (YouTube API Services Audit and Quota Extension form) lifts it. Individually locked videos cannot be appealed. Turnaround unknown. Quota cost per upload conflicts across sources (1 vs 1,600 units); check the Cloud Console.
- **Facebook status 2026-11-07:** adapter implemented (`src/studio/adapters/facebook.py`) with mocked tests: Page-token flow, fixed loopback redirect port, public-only and Reels validation. Real-account verification pending (see `docs/12-facebook-setup.md` section 4).
### 2026-11-10 — Instagram adapter built (feasibility still to be confirmed by a real run)
- Chosen path: Instagram Content Publishing API via Facebook Login (Page token + linked professional account); resumable upload to `rupload.facebook.com`, so **no public video URL needed** (Q5 resolved for Instagram, unverified live). Setup and unknowns: `docs/13-instagram-setup.md`.
- Q4 stays open until a real Reel publishes from a Development-mode app. Limits in code (3-90 s, 9:16) are conservative assumptions.
