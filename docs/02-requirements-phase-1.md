# 02 — Requirements: Phase 1 (Web Application)

**Goal:** a creator can sign up, connect accounts, publish one video to selected destinations immediately, and understand and recover from outcomes.

## Functional requirements
| ID | Area | Requirement |
|---|---|---|
| P1-F1 | Identity | Register with email + password; verify email; log in/out; reset password. |
| P1-F2 | Identity | Delete account and all associated data. |
| P1-F3 | Accounts | Connect a social account through the platform's official OAuth flow. |
| P1-F4 | Accounts | List connected accounts with status (active / needs re-auth / revoked) and disconnect them (revoking at the platform where possible). |
| P1-F5 | Media | Upload a video (MP4), see upload progress, resume/retry a failed upload. |
| P1-F6 | Media | List, rename, and delete uploaded videos. |
| P1-F7 | Content | Create a post: select a video, write/edit caption (per-destination overrides allowed), choose destinations. |
| P1-F8 | Content | Per-destination validation (caption length, file limits, account eligibility) shown before publishing. |
| P1-F9 | Preview | Preview the video and the caption as they will be sent per destination (approximate rendering; not a pixel-exact platform replica). |
| P1-F10 | Publish | "Publish now" to all selected destinations. Each destination progresses independently. |
| P1-F11 | History | View list of posts and per-destination status, timestamps, platform link, and error details. |
| P1-F12 | Failure | Failed destinations can be retried individually without re-publishing successful ones. Retry never creates duplicates when the platform lets us detect prior success. |
| P1-F13 | Failure | Automatic limited retry for transient errors (bounded attempts, backoff); user-visible. |

## Non-functional requirements
- Single-region, single-database deployment; runs locally with Docker-free setup possible (SQLite acceptable for dev, PostgreSQL for deployed).
- Tokens encrypted at rest; passwords hashed with Argon2/bcrypt.
- Uploads of at least [TBD, see open questions] GB supported via chunked upload.
- Every publish state change persisted; UI survives page refresh and server restart (in-flight jobs recovered or marked failed — never lost silently).
- Core engine shared with the CLI; no duplicated publishing logic.
- Basic accessibility (keyboard navigation, labels) and responsive layout.

## Content format
Vertical short-form video (Shorts, Reels). Upload validation reads dimensions/duration and shows per-destination eligibility (e.g. "Eligible as a Short", "Too long for Facebook Reels (max 90 s)") before publishing.

## Platform scope
YouTube first, then Facebook, then Instagram — each included in Phase 1 **only if** feasibility and app-review requirements (see `09-open-questions.md`) are satisfied. Phase 1 may legitimately ship with YouTube only.

## Out of scope (not Phase 1)
Scheduling/calendars, n8n, AI generation/optimization, agentic research, analytics/social listening, additional platforms, teams/roles, billing, mobile apps, video editing.

## Acceptance criteria
1. New user registers, verifies email, logs in.
2. User connects a YouTube account and sees it as active; disconnecting removes stored tokens.
3. User uploads an MP4, writes a caption, selects one or more connected destinations, previews, and publishes; each destination shows a final status.
4. Forcing one destination to fail leaves the other's success intact; retrying the failed one succeeds without duplicating the successful one.
5. Expired/revoked token surfaces as "needs re-auth" with a reconnect action; no silent failure.
6. History persists across restart; an interrupted publish is shown as failed/needs-attention, not stuck "in progress" forever.
7. Deleting the account removes media, tokens, and records.
8. No feature from the future-features list is reachable in the UI or API.
