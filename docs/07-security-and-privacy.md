# 07 — Security and Privacy

## Assets
OAuth tokens (highest value: can post as the creator), user credentials, uploaded videos (possibly unreleased), account/channel metadata.

## Threat model (summary)
| Threat | Mitigation |
|---|---|
| Token theft from DB/backup | Encrypt at rest (Phase 1); key outside DB; minimal scopes; revoke on disconnect. |
| Token leakage via logs/errors | Redaction filter; never log request headers/bodies containing auth; tests assert this. |
| OAuth CSRF / code injection | Signed, single-use `state`; PKCE; strict redirect URI allow-list. |
| Cross-user data access | `user_id` scoping in every query; cross-user tests. |
| Malicious upload | Container/MIME sniffing, size caps, server-generated storage keys, no execution, no path traversal. |
| Credential stuffing | Argon2/bcrypt, rate limiting, generic error messages, optional lockout. |
| Session theft/CSRF/XSS | HttpOnly+Secure+SameSite cookies, CSRF tokens, CSP, output escaping. |
| Supply chain | Pinned/locked dependencies, dependency audit in CI, minimal dependencies. |
| Unwanted publishing | Publishing only on explicit creator action; (future) AI-modified content requires approval. |

## Authentication rules
- Official OAuth only; no platform passwords, no scraping, no browser automation.
- Least-privilege scopes, each justified in an ADR or here once chosen.
- Phase 0: token in OS keyring (preferred) or file with owner-only permissions; documented tradeoff.
- Phase 1: encrypted columns; key via env/secret manager; rotation procedure documented before launch.

## Secrets management
Platform client IDs/secrets and encryption keys come from environment. `.env` ignored by git; `.env.example` lists names only. Never commit secrets; rotate on suspected exposure.

## Privacy
- Data minimization: store only what's needed to publish and show history. Do not fetch followers, DMs, or analytics.
- Captions and video belong to the creator; not used for any other purpose (no model training, no sharing).
- Account deletion removes user, tokens, media files, and history. Disconnecting revokes platform tokens where supported.
- Retention: media may be deleted by the user at any time; define automatic cleanup policy for published media (open question).
- Comply with each platform's developer policy, including data deletion callbacks (Meta requires a data-deletion URL/instructions) and privacy-policy URL for app review.
- Prepare a privacy policy and terms before any external user (needed for app review).
- Regulatory (GDPR/CCPA-style): lawful basis, export and deletion on request. Scope depends on launch geography (open question).

## Logging
Structured; IDs not content; no tokens; no full captions at INFO level.

## Incident basics
Token-compromise runbook: revoke at platform, rotate encryption key, notify affected users. Written before public launch.

## Security checks in the workflow
Linting for secrets (pre-commit), dependency audit, tests for authz boundaries and log redaction.
