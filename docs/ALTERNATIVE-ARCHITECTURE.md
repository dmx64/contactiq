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
3. ✅ Add structured request tracing (request id + provider latency logs)

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

### Route Integration (2026-02-26)
- Added feature-flagged endpoint `POST /api/v1/enrichment/person` in `server.py`.
- Added `enrichment_router.py` to isolate rollout logic:
  - default mode: `legacy_pipeline`
  - adapter mode when `CONTACTIQ_ENABLE_ADAPTER_CHAIN=true`
  - request-level override via `force_adapter_chain` (true/false)
- Added tests: `test_enrichment_router.py`

### Tracing + Telemetry Persistence (2026-02-27)
- Endpoint now emits `request_id` for every `/api/v1/enrichment/person` request.
- Adapter-chain mode response includes telemetry summary:
  - attempt count
  - failed attempt count
  - total provider latency
  - provider path and selected provider
- Added persistence table `enrichment_telemetry` in SQLite with request-level chain telemetry.
- Added unit tests for telemetry helpers: `test_enrichment_telemetry.py`.

### Telemetry Read Endpoint (2026-02-28)
- Added `GET /api/v1/enrichment/telemetry` (API-key protected).
- Supports filters:
  - `since_hours` (default 24, max 336)
  - `limit` (default 20, max 100)
  - `chain` (optional)
- Returns:
  - windowed overview (total requests, fallback rate, success rate, avg attempts, avg latency)
  - top selected providers
  - recent request-level telemetry entries

### Telemetry Rollout Metrics Upgrade (2026-03-01)
- Added `latency_p95_ms` to overview for tail-latency monitoring.
- Added `provider_error_breakdown` (top providers by failed adapter attempts).
- Added helper coverage in `test_enrichment_telemetry.py`:
  - percentile calculation
  - provider error breakdown parsing/counting

### Hourly Trend Slice (2026-03-01, late)
- Extended `GET /api/v1/enrichment/telemetry` overview with `hourly_trends`.
- `hourly_trends` includes per-hour:
  - `total_requests`
  - `fallback_rate_pct`
  - `error_rate_pct`
  - `latency_p95_ms`
- Added helper `build_hourly_trends` + unit coverage for mixed timestamp formats and fallback/error math.

### Trend Guardrails (2026-03-02, nightly)
- Added anomaly detection for rollout guardrails via `trend_alerts` in telemetry overview.
- Alert types:
  - `fallback_spike` (fallback rate jump vs recent baseline)
  - `error_spike` (error-rate jump vs recent baseline)
  - `latency_p95_regression` (tail-latency regression vs moving baseline)
- Detection is based on moving hourly baselines (windowed prior points) to reduce one-off noise.
- Added helper `build_hourly_trend_alerts` and unit coverage for spike/regression scenarios.

## Migration Phases
1. Baseline metrics (latency/error per endpoint/provider)
2. Extract enrichment module behind adapter contract
3. Introduce async OSINT job queue
4. Add compatibility layer for existing mobile API responses
5. Roll out by endpoint flag + rollback toggle
