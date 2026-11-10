# 00 — Product Brief

## Problem
Independent creators record one video and then repeat the same chore on every platform: upload, re-enter the caption, fix per-platform settings, check it went live. It is tedious, error-prone, and gives no single record of what was published where.

## Product
**Personalized Content Studio** lets an individual creator publish a video and caption to their own social accounts through official platform APIs, and see an honest status for each destination.

## Vision
A small, reliable, creator-controlled publishing tool that can later grow (scheduling, automation, AI assistance, analytics) on the same core without a rewrite.

## Target user
Solo creators / personal brands who:
- own channels/pages/accounts on YouTube, Facebook, Instagram;
- post video regularly;
- want control, not an agency suite.

Not targeted: teams, agencies, enterprises, brands with approval workflows.

## Content format
Vertical (9:16) short-form video only: **YouTube Shorts, Facebook Reels, Instagram Reels**. Creators supply finished vertical MP4s; the app does not edit, crop, or transcode (those would be new scope). Landscape and long-form are not targeted.

## Principles
1. **Reliable over featureful.** A publish either succeeded, failed, or is in a known in-between state. Never ambiguous.
2. **Creator control.** Nothing is published without the creator's explicit action; AI-modified content (future) requires approval.
3. **Official APIs only.** No scraping, no password sharing.
4. **Small core, thin shells.** One publishing engine; CLI and web are callers.
5. **Validate before committing.** Platform feasibility is checked early (Phase 0).
6. **Free and open source.** Built only from free/open-source software; publishing costs nothing (ADR 0002).

## Scope summary
| Phase | Deliverable | Status |
|---|---|---|
| 0 | CLI proof of concept — publish MP4 + caption to one platform | Planned |
| 1 | Web app — accounts, uploads, captions, destinations, preview, publish now, history, retries | Planned |
| Later | Scheduling, n8n, AI, agentic research, analytics, more platforms | **Out of scope; not committed** |

## Platform priority
1. YouTube 2. Facebook 3. Instagram — each subject to feasibility validation (see `09-open-questions.md`).

## Success measures (initial)
- Phase 0: a real video is published to YouTube via the CLI end to end; failure modes and quota/review constraints documented.
- Phase 1: a creator can register, connect accounts, publish one video to multiple destinations, and understand the result of each, including recovering from a failure.

## Key risks (summary; detail in `08` and `09`)
Platform app-review and API restrictions; token expiry/revocation; large-file upload reliability; Instagram's account-type and media-URL requirements; scope creep toward future features.

## Document map
See `README.md` for the index.
