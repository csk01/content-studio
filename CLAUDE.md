# CLAUDE.md — Personalized Content Studio

Persistent instructions for Claude working in this repository. Read this first, every session.

## 1. What this is

**Personalized Content Studio** is a social publishing platform for **individual creators**. A creator brings a finished video and a caption, picks destinations (YouTube, Facebook, Instagram), and the app publishes it through each platform's **official API and OAuth flow**, then reports honest per-destination status.

**Vision:** a small, reliable, trustworthy publishing tool that creators control completely, and that can later grow (scheduling, automation, AI assistance) *without a rewrite*. Reliability and creator control come before features.

**Target audience:** solo creators and small personal brands who post the same video to several platforms by hand today. Not agencies, teams, or enterprises (no multi-user workspaces, roles, or approval chains in scope).

## 2. Scope

### Phase 0 — CLI proof of concept
User supplies an MP4 + caption, selects one supported platform, authorizes via the official platform mechanism, the app publishes, and reports success or failure. Purpose: **validate the publishing workflow and platform constraints**, not build a product.

### Phase 1 — Web application
Individual registration/authentication; connect/manage social accounts; upload/manage videos; write/edit captions; select destinations; preview; publish immediately; publishing history and status; failure handling and retries.

### Content format
The product targets **vertical (9:16) short-form video**: YouTube Shorts, Facebook Reels, Instagram Reels. All creator MP4s are assumed vertical. The engine reads dimensions and duration from the MP4 header (`core/mp4.py`, no external tools) and adapters validate against each platform's short-form rules (Facebook Reels: 9:16, 3-90 s; YouTube Shorts: vertical/square, up to ~3 min, verify). Landscape/long-form support is not a goal; if a video is not Short-eligible, warn the creator rather than silently publish it as a normal video.

### Platform priority
1. YouTube  2. Facebook  3. Instagram
**Validate official API capabilities, permissions, account eligibility, and app-review requirements before committing to each integration** (see `docs/09-open-questions.md`). Do not assume an integration is feasible.

### Explicitly OUT of scope (do not build, do not scaffold, do not add "hooks" for)
- Scheduling and content calendars
- n8n automation
- AI content creation/optimization
- Agentic research and intelligence
- Analytics and social listening
- Additional platforms beyond the three above
- Teams, workspaces, roles, billing

Future features are documented only as *extension points* in `docs/04-architecture-overview.md`. If a request drifts into these, flag it and ask before proceeding. **Rule that must hold when AI arrives later: AI-modified content requires explicit creator approval before publishing.**

## 3. Consult docs before deciding

Before any implementation or design decision, read the relevant documents under `docs/`:

| Need | Read |
|---|---|
| Why / who | `docs/00-product-brief.md` |
| What Phase 0 must do | `docs/01-requirements-phase-0.md` |
| What Phase 1 must do | `docs/02-requirements-phase-1.md` |
| UX, journeys | `docs/03-product-design.md` |
| System shape, domain model, adapters | `docs/04-architecture-overview.md` |
| Phase-specific design | `docs/05-…phase-0.md`, `docs/06-…phase-1.md` |
| Auth, tokens, privacy | `docs/07-security-and-privacy.md` |
| Milestones, acceptance | `docs/08-roadmap-and-acceptance.md` |
| Unresolved decisions | `docs/09-open-questions.md` |
| Dependencies and costs | `docs/11-dependencies-and-costs.md` |
| Past decisions | `docs/adr/` |

If the docs conflict with a request, say so; don't silently pick. If the docs are silent on a major question, record it in `09-open-questions.md` with a recommendation rather than deciding quietly.

## 4. Architecture principles

- **Modular monolith.** One deployable backend, clear internal module boundaries.
- **The publishing engine is a standalone Python package/module** with no imports from the CLI, web layer, n8n, or any AI provider. CLI, FastAPI, and future automation are thin *callers* of it.
- **Platform adapters** behind one interface (`PlatformAdapter`); platform quirks never leak into the core.
- **Storage abstraction** (`MediaStore`): local filesystem first; cloud later behind the same interface.
- **Explicit publishing state machine**; every state transition is persisted. Publishing is idempotent where the platform allows, and retries never silently double-post.
- **Proposed stack (proposals, not irreversible):** Python; Typer (CLI); FastAPI; Next.js + TypeScript; SQLite (Phase 0) → PostgreSQL (Phase 1); SQLAlchemy + Alembic; local media storage. Changing any of these requires an ADR.
- **Avoid premature complexity.** No microservices, Kubernetes, Redis, message brokers, service meshes, or cloud-specific infrastructure unless an ADR shows a measured need. Background work in Phase 1 starts with the simplest thing that works (e.g. in-process worker + DB-backed job table). GCP/GCS are optional, never prerequisites.
- Prefer boring, well-understood solutions. Build the smallest thing that satisfies the current phase's acceptance criteria.

## 4a. Cost and licensing policy (hard constraint)

The product must be buildable, runnable, and usable at **zero monetary cost**, using only free and open-source software.

- **Dependencies:** only OSI-approved open-source licenses (MIT, BSD, Apache-2.0, PSF, MPL-2.0, and similar permissive/weak-copyleft). Before adding a dependency, check its license. Never add proprietary, source-available (BUSL, SSPL, Elastic), or "free tier only" SDKs. Record each new direct dependency's license in `docs/11-dependencies-and-costs.md`.
- **Publishing must cost nothing:** use only the official platform APIs that are free to call within their default quotas (YouTube Data API v3; Meta Graph API). Do not adopt paid third-party posting services or aggregators (e.g. Ayrshare, Buffer/Hootsuite APIs).
- **Cloud accounts:** do not enable billing on Google Cloud (or any provider). The OAuth client and YouTube Data API need no billing account. If a feature would require a billing account, stop and ask.
- **No paid infrastructure by default:** the app must run locally/self-hosted. Hosting a public Phase 1 deployment, a domain, or a transactional email provider may cost money; treat them as optional and ask before assuming them. GCP/GCS stay optional.
- **No paid AI/LLM APIs** are in scope now (AI is a future feature anyway).
- If a free quota or terms change and publishing would start costing money, record it in `docs/09-open-questions.md` and stop.

See `docs/adr/0002-free-and-open-source-only.md`.

## 5. Coding standards

- Python 3.12+, type hints everywhere, `mypy --strict` on the core package; `ruff` for lint/format.
- TypeScript `strict` mode; ESLint + Prettier.
- `pytest` for tests. The core engine must be testable **without network**: adapters use injectable HTTP clients; real-platform tests are separate, opt-in, and clearly marked.
- Small modules, explicit dependencies (constructor injection), no global mutable state, no business logic in CLI/route handlers.
- Pydantic models at boundaries; SQLAlchemy models stay inside the persistence module.
- Schema changes only via Alembic migrations.
- Errors: typed domain exceptions; map platform errors into a normalized error taxonomy (retryable / auth-expired / policy-rejected / permanent).
- Logging: structured, never contains tokens, captions-in-bulk, or personal data beyond IDs.
- Commit small, conventional messages. No dead code, no speculative abstractions beyond the ones named in this file.

## 6. Security and privacy expectations

- Use **only official OAuth 2.0 flows** (PKCE where supported). Never ask for or store platform passwords. No scraping, no unofficial APIs, no browser automation of platforms.
- Request **least-privilege scopes**; document why each is needed.
- OAuth tokens are secrets: encrypted at rest (Phase 1), never logged, never in URLs, never committed. Phase 0 stores them in a local file with restrictive permissions, or the OS keyring, and documents the tradeoff.
- Secrets (client IDs/secrets, encryption keys) come from environment/config, never from source. `.env` is git-ignored; provide `.env.example`.
- Users can disconnect an account and delete their data; disconnect revokes the token at the platform where possible.
- Validate and limit uploads (type, size, container sniffing), never trust filenames.
- Phase 1 web: password hashing with Argon2/bcrypt, CSRF/session protections, rate-limited auth, HTTPS in any non-local deployment.
- Follow each platform's developer policies and data-deletion requirements. Details: `docs/07-security-and-privacy.md`.

## 7. Documentation and ADR maintenance

- Docs are part of the product. Any change to behavior, scope, or architecture updates the relevant doc **in the same change**.
- Keep Phase 0 and Phase 1 content separated; never move future-feature items into committed scope without explicit user approval.
- Record significant decisions as ADRs in `docs/adr/NNNN-short-title.md` (template in `docs/adr/README.md`): context, decision, alternatives, consequences, status (proposed/accepted/superseded). Supersede, don't rewrite history.
- Resolved open questions move from `09-open-questions.md` into an ADR and are marked resolved with a link.
- README status section is updated when a milestone completes.

## 8. Working agreements

- Current status: **Phase 0 implementation in progress** (started 2026-11-07). YouTube and Facebook (Reels to Pages) adapters exist; an Instagram adapter exists (mock-tested; live feasibility unconfirmed, see docs/13-instagram-setup.md). Do not create external accounts or provision infrastructure; the user supplies Google Cloud credentials. Run `pytest`, `ruff check`, and `mypy` before finishing a change.
- When uncertain about a major product or architecture question: recommend, record, ask. Don't decide silently.
- Be pragmatic: small, reliable, evolvable.
