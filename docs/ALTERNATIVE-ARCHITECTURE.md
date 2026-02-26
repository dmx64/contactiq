# ContactIQ Alternative Architecture (Nightly Draft)

## Context
Current ContactIQ backend is a single Flask service with many provider integrations inside one runtime. This works for speed, but makes provider failures, rate limits, and long-running OSINT jobs harder to isolate.

## Target Outcomes
- Better reliability when one provider is down
- Clear cost controls per provider and per workflow
- Faster response times for interactive mobile screens
- Safer incremental migration (no big-bang rewrite)

## Option A — Conservative (Modular Monolith + Queue)
Keep Flask, split into internal modules with strict boundaries:
- `api-gateway` (auth, request validation, rate limits)
- `enrichment-service` (email/domain/person enrichment)
- `osint-worker` (async CLI tools via task queue)
- `monitoring-service` (news/sanctions polling + alerts)
- shared cache (Redis) + Postgres for normalized results

### Pros
- Lowest migration risk
- Reuses most existing code
- Fastest time to production hardening

### Cons
- Still one deployable unit for API layer
- Scaling boundaries are logical, not full service isolation

## Option B — Aggressive (Event-Driven Microservices)
Extract provider domains into independent services:
- `contact-api` (public API + auth)
- `identity-service` (person/company/entity graph)
- `osint-service` (tool orchestration)
- `callerid-service` (real-time phone intel)
- `compliance-service` (sanctions/PEP)
- message bus for async orchestration + audit events

### Pros
- Strong isolation and independent scaling
- Better for enterprise multi-tenant roadmap
- Clear ownership per domain

### Cons
- Higher complexity and infra cost
- Longer migration and observability setup

## Recommendation (Now)
Adopt **Option A** immediately, while designing interfaces that can later become Option B services.

## Vertical Slice for Next Iteration
1. ✅ Add provider adapter interface + fallback chain for enrichment APIs (`provider_adapters.py`)
2. Move OSINT CLI execution to background queue worker with job status endpoint
3. Add structured request tracing (request id + provider latency logs)

### Implemented Scaffold (2026-02-25)
- Added `provider_adapters.py` with:
  - `ProviderAdapter` contract
  - `ProviderFallbackChain` orchestration
  - per-attempt telemetry (provider/status/latency/error/fallback)
  - first chain `person_enrichment`: GitHub → Wikidata fallback
- Added unit tests: `test_provider_adapters.py`
- Notes:
  - This is intentionally additive and non-breaking.
  - Existing pipeline remains default until route-level integration is enabled.

## Migration Phases
1. Baseline metrics (latency/error per endpoint/provider)
2. Extract enrichment module behind adapter contract
3. Introduce async OSINT job queue
4. Add compatibility layer for existing mobile API responses
5. Roll out by endpoint flag + rollback toggle
