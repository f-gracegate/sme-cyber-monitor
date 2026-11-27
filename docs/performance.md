# Performance testing (Phase 7)

Targets from the product plan: API p95 below 500 ms for normal requests, the dashboard usable
within 3 seconds, and 95% of eligible events turned into alerts within 2 minutes.

## How to run

```bash
docker compose up -d
docker compose exec backend python -m app.ops.loadtest --users 20 --seconds 60 --agents 20 --batches 5
```

The harness creates a throwaway organisation and runs three tests:

1. **Dashboard API:** concurrent users cycling through `/overview`, `/alerts`, `/incidents`,
   `/assets`, `/findings` and `/remediation-tasks`.
2. **Ingestion burst (security scenario 8):** many enrolled agents send full 500-event batches
   at the same time.
3. **Alert delivery:** a brute-force burst, then the time until the alert is visible.

It is for development and staging only: it uses the development mailbox and sets the test
organisation's plan directly.

## Results (27 November 2026, development stack)

Development stack: a single uvicorn process with auto-reload, on a laptop in Docker. Production
runs several API workers, so these are lower bounds.

| Test | Result | Target |
| --- | --- | --- |
| Dashboard API, 20 concurrent users for 30 s | 8,593 requests (286/s), **p95 132 ms** (overview p95 151 ms, lists ~76 ms), 0 errors | p95 < 500 ms ✅ |
| Ingestion: 20 agents × 5 batches × 500 events | 50,000 events accepted, **~2,600 events/s**, 0 server errors, batch p95 4.2 s under full contention | no 5xx ✅ |
| Alert delivery | Brute-force alert visible **0.03 s** after the events | < 2 min ✅ |

## Back-pressure

- **Per agent:** 120 event batches per 5 minutes (up to 60,000 events). Further batches get
  `429`, and the agents buffer and retry.
- **Per collector:** 600 batches per 5 minutes. **Wazuh:** 600 requests per minute per key.
- **Requests:** body sizes are capped. Events are idempotent by `event_id`, so retries never
  duplicate.
- **Enrolment:** limited to 120 per IP per 10 minutes. This was raised from 30 after the load
  test showed an office rolling out many laptops behind one IP would be throttled.

## Scaling beyond the pilot

The API and monitor workers scale horizontally (`API_WORKERS`, `MONITOR_WORKERS`). Checks are
claimed with `FOR UPDATE SKIP LOCKED`, so extra workers never run the same check twice. When
raw event volume outgrows PostgreSQL (millions of events a day), move `security_events` to an
indexed event store (OpenSearch evaluation, see the roadmap) and keep PostgreSQL for business
records.
