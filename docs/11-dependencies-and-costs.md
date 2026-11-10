# 11 — Dependencies, Licenses, and Costs

Policy: `CLAUDE.md` section 4a and ADR 0002. Update this file whenever a direct dependency or external service is added.
Licenses below were read from installed package metadata (2026-11-07).

## Runtime dependencies (Phase 0)
| Package | License | Purpose |
|---|---|---|
| Python | PSF | Language |
| typer | MIT | CLI |
| httpx | BSD-3-Clause | HTTP client |
| SQLAlchemy | MIT | ORM |
| alembic | MIT | Migrations |
| keyring | MIT | OS credential storage |
| SQLite | Public domain | Phase 0 DB |

## Development tools
| Package | License |
|---|---|
| pytest | MIT |
| ruff | MIT |
| mypy | MIT |
| hatchling (build) | MIT |

## Planned (Phase 1; verify license when adding)
FastAPI (MIT), Next.js (MIT), PostgreSQL (PostgreSQL License). Confirm each at adoption time.

## External services and cost
| Service | Cost | Notes |
|---|---|---|
| Google Cloud project (OAuth client + YouTube Data API v3) | Free | **Do not enable billing.** No billing account is needed. Usage is limited by default quota. |
| YouTube API compliance audit (to lift private-upload lock) | Free | Process effort only; verify current terms. |
| Meta developer account / Graph API (Facebook Reels; Instagram later) | Free | Needs app review and possibly Business Verification (free, but effort). Verify at integration time. |
| Instagram professional account | Free | Required for API publishing. |
| Local run (Phase 0, and Phase 1 on your own machine) | Free | |
| **Public hosting, domain, TLS, email provider for Phase 1** | **May cost money** | Not covered by the zero-cost guarantee. Free/self-hosted options to evaluate; ask before adopting. |

## Not allowed
Paid posting aggregators, proprietary or source-available SDKs, paid AI APIs, any service requiring a credit card on file.
