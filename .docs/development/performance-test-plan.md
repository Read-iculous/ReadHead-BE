# Performance Test Plan (VT-13)

> **Status**: Plan document only — no code or test assets are delivered by this file.
> **Every quantitative threshold in this document is marked DRAFT — pending approval.**
> Per the SRS (NFR-PER-04, SYS-QLT-PER-006, §5 release checklist item 4), performance
> thresholds take effect **only after explicit approval**. Until approved, they are
> baseline targets for measurement and must **not** be used as acceptance criteria.

## 1. Objective & Traceability

This plan defines how latency, resource usage and load capacity of the ReadHead backend
and its browser extension client are measured.

| Reference | Requirement | How this plan addresses it |
|---|---|---|
| VT-13 | NFR-PER-01–06 — "Measure latency, resources and capacity according to **approved** performance thresholds" (T, A) | Scenarios in §4 + metric definitions in §2/§3 |
| NFR-PER-01–02 | Status feedback and async handling so waiting does not block the reading UI | SSE scenario S1 measures time-to-first-token and UI-visible feedback latency |
| NFR-PER-03 | No unintended duplicate request submission | Scenario S2 includes an idempotency check (duplicate submissions do not multiply load) |
| NFR-PER-04 | Target response times per task type, defined as **separate, approved** thresholds | §2 proposes per-task-type thresholds (DRAFT) |
| NFR-PER-05 | Evaluation must cover short content, long content and provider-error cases | S1/S4/S5 vary payload size; S6 covers degraded upstream/infra behavior |
| NFR-PER-06 | Browser and backend resource usage evaluated under an **approved** target load | S1/S7 measure memory/CPU; load levels here are proposals until approved |
| SYS-QLT-PER-001–002 | Responsiveness and honest waiting states | Measured via first-token latency and status-transition observations |
| SYS-QLT-PER-003 | Distinguish Extension/Backend/AI Service time from external provider/network wait | §3 method separates local-service latency from end-to-end (provider-inclusive) latency |
| SYS-QLT-PER-004 | Large-content handling or explicit limits | S4 (50 MB export) and S3 (10k tombstones) exercise large payloads |
| SYS-QLT-PER-005 | Capacity must be assessable/adjustable as user count and volume change | S1/S2 establish measured baselines at proposed load levels |
| SYS-QLT-PER-006 | MVP stage: measure **representative operations** to establish the baseline for future quantitative targets | This entire plan is a baseline-measurement plan; see principle below |

**Governing principle (SyRS §4.1 / SYS-QLT-PER-006)**: the MVP has no measured data
sufficient to fix quantitative performance thresholds. Representative MVP operations
(open the panel, submit an AI request, receive a response, sync history) are measured
first; the results are the baseline from which targets are set for the next iteration.
Consequently, **all numbers in §2 are proposals**, not approved limits.

## 2. Proposed Thresholds (DRAFT — pending approval)

> These values are **DRAFT — pending approval** by the project owner per NFR-PER-04
> and SRS §5 (release checklist item 4: "Phê duyệt các ngưỡng hiệu năng"). They are
> informed by existing documented budgets (e.g., FE-24 content-script budget) and by
> implemented behavior (e.g., the 2-streams-per-user admission limit), but none has
> been approved as an acceptance threshold.

| # | Metric | Proposed target (DRAFT) | Basis / rationale | Maps to |
|---|---|---|---|---|
| P-01 | SSE first-token latency (end-to-end, **including upstream provider**) | ≤ 2 s p50 / ≤ 5 s p95 | Covers the full user-visible wait from `POST /ai/stream` to the first text token; provider time is included because users cannot distinguish it (NFR-PER-01) | NFR-PER-01/04, SYS-QLT-PER-001 |
| P-02 | SSE token throughput | Baseline measurement only in MVP; provisional informational floor ≥ 10 tokens/s per active stream | Dominated by the external provider (SYS-QLT-PER-003); measuring baseline before fixing a target, per SYS-QLT-PER-006 | SYS-QLT-PER-003/006 |
| P-03 | Simple CRUD API latency | p95 ≤ 300 ms for single-entity endpoints: `GET/PATCH /users/me/settings`, `GET /reading/history`, `GET /conversations` (default page size) | Pure backend work (no AI, no provider); 300 ms leaves headroom for DB round-trips | NFR-PER-04 |
| P-04 | Health check latency | p95 ≤ 100 ms for `GET /api/v1/health/live`; readiness probe (`/health`, touches PostgreSQL/Redis) measured separately with proposed p95 ≤ 300 ms | Liveness is a trivial handler; readiness depends on infra round-trips | NFR-PER-04 |
| P-05 | SSE concurrent streams per user | 2 per user (existing functional limit, kept unchanged — the test verifies **stability at** this limit, it does not raise it) | Implemented admission control documented in `architecture/decisions.md` (ADR-011) and `development/implementation-status.md` | NFR-PER-02, SYS-QLT-PER-005 |
| P-06 | Extension content-script memory | ≤ 50 MB resident on an injected tab during normal reading assistance | Client-side resource bound so the content script does not degrade host pages | NFR-PER-06, SYS-QLT-PER-001 |
| P-07 | Extension bundle size | Content-script bundle < 150 KB gzip | Matches the existing FE-24 packaging budget in `ReadHead-FE/.docs/development/tasks.md` ([FE-24]) — cross-checked, not a new number | NFR-PER-06, NFR-CMP-01 |
| P-08 | Quiz generation end-to-end | p95 ≤ 15 s (including provider) for `POST /quiz/generate` | Single blocking request (no SSE); users tolerate a bounded wait but must not see a hanging request | NFR-PER-01/04 |

Rules:

- A metric marked **DRAFT** is reported as a measurement with comparison against the
  proposed value; it never produces a Pass/Fail acceptance verdict until approved.
- End-to-end (provider-inclusive) metrics (P-01, P-02, P-08) are reported alongside
  provider-excluded timings so SYS-QLT-PER-003's separation is preserved.

## 3. Method

### 3.1 Tools (proposed)

| Tool | Purpose |
|---|---|
| **k6** | HTTP load generation and SSE streaming scenarios (S1–S6). k6 supports streaming response consumption and per-check timing, suitable for first-token latency capture. |
| **pytest-benchmark** *or* **locust** | Micro-benchmarks of service-layer functions (sync diffing, privacy scan, export serialization) and Python-driven scenario glue. Choose pytest-benchmark for deterministic single-function measurement; locust if a Python-native load script is preferred over k6. |

Final tool selection is itself subject to approval; either combination satisfies the
measurement requirements below.

### 3.2 Environment

- **Baseline environment**: local `docker-compose` (PostgreSQL 15 + Redis 7 + Uvicorn)
  with a **staging-like profile**: production ASGI middleware stack, real Redis rate
  limits and admission control, production encryption configuration.
- **Provider mocking**: AI upstream calls use a **synthetic streaming provider fixture**
  (controlled token timing) so measurements are reproducible and cost-free. Runs
  against a real provider are permitted as *informational* supplements and are labeled
  as such; they are never mixed into baseline numbers (consistent with the test-fixture
  discipline in `implementation-status.md`).
- **Data seeding**: each scenario seeds its own data (users, conversations, tombstones,
  highlight rows) through the public API or a documented fixture script, so any run can
  be reproduced from an empty database.

### 3.3 Measurement & correlation

- Every request carries and records the `X-Request-ID` response header (implemented by
  the correlation middleware). Scenario harnesses log request ID → timestamps → result
  so any outlier can be traced to a single request in server logs without exposing
  sensitive content (respecting `FR-OPS-03` log hygiene).
- For each metric, record: environment profile, commit hash, data volume, p50/p95/max,
  and the number of samples. Raw timing dumps are kept with the run report.
- **Reproducibility**: each scenario below states its exact command shape. Harness
  scripts, once implemented, live outside this documentation task; until then the
  scenario descriptions are the executable specification.

## 4. Scenarios

| # | Scenario | Steps (summary) | Measured | Reproduction sketch |
|---|---|---|---|---|
| S1 | **50 concurrent SSE streams** | 50 virtual users, each authenticated with a distinct account + valid mock provider, hold a streaming `POST /ai/stream` session; steady-state arrival of one new stream per second until 50 concurrent | P-01 first-token latency distribution, P-02 token throughput, backend CPU/memory, admission behavior at the 2-streams-per-user boundary | k6 script: 50 VUs, HTTP stream consumer, synthetic provider fixture; report via `X-Request-ID` correlation |
| S2 | **200 rps simple CRUD** | Sustained 200 requests/s split across `GET/PATCH /users/me/settings`, `GET /reading/history`, `GET /conversations`; includes a deliberate duplicate-submission check (same request fired twice) to verify no duplicate side effects (NFR-PER-03) | P-03 p95 latency, error rate, rate-limit (`429`) incidence | k6 constant-arrival rate 200/s, duration 5 min, single seed user set |
| S3 | **Sync with 10k tombstones** | Seed one user with 10,000 tombstoned conversation/highlight rows (30-day retention window applies); run `POST /sync/pull` (full and incremental) and `POST /sync/push` batches | Pull latency p50/p95 vs payload size, push atomicity under load (conflict + rollback behavior must remain correct — correctness is functional, timing is informational) | Fixture script inserts 10k tombstones; k6 or pytest harness drives pull/push with recorded cursors |
| S4 | **50 MB export** | Seed an account whose GDPR export bundle approaches ~50 MB (the documented size-warning threshold of `GET /users/me/export`), then request the export at the dedicated 5/min rate limit | Export duration, memory during serialization, behavior at the rate limit | Seeded export scenario against local compose; measured via `X-Request-ID` + server timings |
| S5 | **Quiz generate burst** | 10–20 concurrent users each request `POST /quiz/generate` with a valid source text (≥ 20 words, per implemented minimum) against the mock provider with realistic latency | P-08 p95, queue/admission behavior, no timeout storm | k6 ramping arrival, mock provider fixture |
| S6 | **Redis degraded (latency injected)** | Inject 200–1000 ms added latency (and a full-outage case) into Redis calls via a proxy or fault-injection wrapper; exercise streams, rate limiting and rebinding | Behavior under the documented degraded-mode policy (e.g., `503 SERVICE_DEGRADED` on bind during outage), latency amplification, no event-loop blocking | Toxiproxy (or equivalent) between app and Redis; run S1/S2 subsets against it |
| S7 | **30-minute soak — memory leak check** | Moderate mixed traffic (streams + CRUD + sync) for 30 minutes against one long-lived process | Heap/RSS trend slope, GC behavior, fd/connection leak count; flat trend = no leak signal | k6 sustained low load + process metrics sampling every 10 s |

## 5. Out of Scope

- **Production APM / observability tooling** — deferred per `SYS-FUN-062`; this plan
  covers pre-production measurement only, not runtime monitoring dashboards.
- **Acceptance decisions** — thresholds marked DRAFT must not be used to accept or
  reject a release. Approval is tracked in the SRS release checklist (§5, item 4).
- **Real paid provider load runs** — never used for baseline or acceptance numbers;
  optional informational runs only (no automatic retries, per ADR-009 discipline).
- **Browser rendering performance** of host websites (out of backend scope; FE-24
  bundle budget P-07 is the only client packaging metric tracked here).
