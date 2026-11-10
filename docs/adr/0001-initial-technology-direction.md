# 0001 — Initial technology direction
- Status: proposed
- Date: 2026-11-07

## Context
Solo-creator publishing tool, small team, must stay simple and evolve without a rewrite. Phase 0 is a CLI PoC; Phase 1 a web app.

## Decision (proposed)
Modular monolith in Python; independent publishing engine; Typer CLI; FastAPI; Next.js + TypeScript; SQLite (Phase 0) → PostgreSQL (Phase 1); SQLAlchemy + Alembic; local media storage behind a `MediaStore` abstraction; DB-backed job table instead of a broker.

## Alternatives considered
- Microservices / Kubernetes / Redis / message broker: unjustified operational cost at this scale.
- Full-stack TypeScript: viable, but the engine, CLI and API benefit from one Python codebase; Next.js remains for UI.
- Cloud-managed storage/DB from day one: adds accounts and lock-in before need is proven.

## Consequences
Two languages (Python, TypeScript). Simple ops. Engine reusable by CLI, API, and future automation. Revisit via a new ADR if measured needs (scale, latency) demand it.
