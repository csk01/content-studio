# 0002 — Free and open-source only; publishing must cost nothing
- Status: accepted
- Date: 2026-11-07

## Context
The product is for individual creators and is built by a small team with no budget commitment. Cost must never gate the ability to build, run, or use it.

## Decision
1. Every dependency and tool is free and OSI open source (permissive or weak copyleft).
2. Publishing uses only official platform APIs that are free to call within default quotas. No paid posting aggregators or SDKs.
3. No cloud billing account is required or enabled. Local/self-hosted operation is the default.
4. Anything that could incur cost (public hosting, domain, email provider, quota increases that require billing, paid AI APIs) is optional, explicitly flagged, and needs approval before adoption.

## Alternatives considered
- Paid social-posting aggregators: simpler integration, but recurring cost and vendor lock-in; rejected.
- Cloud-managed DB/storage: convenient but needs billing; deferred (local storage + SQLite/PostgreSQL instead).

## Consequences
- Constrained by default API quotas (e.g. YouTube daily upload limits), which are acceptable for individual creators.
- Public hosting for Phase 1 is the main place cost can appear; it is not part of the zero-cost guarantee (see `docs/09-open-questions.md` Q12).
- Platform terms can change; free-tier status must be re-verified before each platform integration.
