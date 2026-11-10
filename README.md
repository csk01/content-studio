# Personalized Content Studio

A social publishing platform for individual creators: bring a video and a caption, choose destinations, and publish through official platform APIs with honest per-destination status.

## Current status
**Phase 0 in progress.** The core engine, YouTube adapter (OAuth PKCE + resumable upload), SQLite persistence and the `studio` CLI are implemented and unit-tested (43 tests, no network). The first real YouTube publish has **not** been run yet: it needs your Google Cloud OAuth client (see `docs/10-youtube-setup.md`). A Facebook Reels adapter is implemented and mock-tested but has not been run against a real Page (see `docs/12-facebook-setup.md`). Instagram is not started.

## Scope
**Phase 0 — CLI proof of concept:** MP4 + caption → pick a platform → official OAuth → publish → report success/failure.

**Phase 1 — Web app:** registration/login, connect and manage social accounts, upload/manage videos, edit captions, select destinations, preview, publish immediately, publishing history/status, failure handling and retries.

**Platform priority:** YouTube → Facebook → Instagram (each gated on feasibility/app-review validation).

**Not in scope (future):** scheduling/calendars, n8n automation, AI content creation, agentic research, analytics/social listening, additional platforms. AI-modified content will require creator approval before publishing.

## Cost policy
Everything used is free and open source, and publishing costs nothing (official free APIs only; no billing accounts). See `docs/11-dependencies-and-costs.md` and `docs/adr/0002-free-and-open-source-only.md`. Public hosting for Phase 1 is the one area that may cost money and is optional.

## Proposed technology (proposals, not final)
Python · Typer · FastAPI · Next.js + TypeScript · SQLite (Phase 0) → PostgreSQL (Phase 1) · SQLAlchemy + Alembic · local media storage behind an abstraction. Modular monolith; no microservices/Kubernetes/Redis.

## Documentation index
| Doc | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Persistent instructions for Claude |
| [00 Product brief](docs/00-product-brief.md) | Vision, audience, principles |
| [01 Phase 0 requirements](docs/01-requirements-phase-0.md) | CLI PoC |
| [02 Phase 1 requirements](docs/02-requirements-phase-1.md) | Web app |
| [03 Product design](docs/03-product-design.md) | Journeys, screens, UX rules |
| [04 Architecture overview](docs/04-architecture-overview.md) | Components, domain, lifecycle, adapters |
| [05 Phase 0 architecture](docs/05-architecture-phase-0.md) | CLI design |
| [06 Phase 1 architecture](docs/06-architecture-phase-1.md) | Web design |
| [07 Security & privacy](docs/07-security-and-privacy.md) | Threats, tokens, privacy |
| [08 Roadmap & acceptance](docs/08-roadmap-and-acceptance.md) | Milestones, risks |
| [09 Open questions](docs/09-open-questions.md) | Unresolved decisions |
| [10 YouTube setup](docs/10-youtube-setup.md) | Google Cloud steps and findings |
| [11 Dependencies & costs](docs/11-dependencies-and-costs.md) | Licenses and cost policy |
| [12 Facebook setup](docs/12-facebook-setup.md) | Meta app steps and findings |
| [adr/](docs/adr/README.md) | Decision records |

## Getting started
```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
```
To publish for real, follow `docs/10-youtube-setup.md` (`studio auth youtube`, then `studio publish clip.mp4 --caption "..."`) or `docs/12-facebook-setup.md` (`--platform facebook --visibility public`). Use vertical clips such as `samples/test_vertical.mp4`.

Background reading:
1. Read `docs/00-product-brief.md`, then `docs/01-requirements-phase-0.md`.
2. Review and answer `docs/09-open-questions.md` (especially Q1, Q2, Q15, Q16).
3. Confirm or amend `docs/adr/0001-initial-technology-direction.md`.
4. Implementation begins with Phase 0 milestone M0.1 (feasibility) followed by M0.2 (core skeleton), per `docs/08-roadmap-and-acceptance.md`.

Requires Python 3.12+.
