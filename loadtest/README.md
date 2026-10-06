# Load tests

Scripts that check the service-level objectives (SLOs) of each milestone. They are run on
demand against a production-like stack (`compose.yaml`) — never against production.

## Tools

* [k6](https://k6.io/) for scenarios with thresholds (the run fails when an SLO is missed).
* [oha](https://github.com/hatoo/oha) for quick single-endpoint checks.

## M1 — identity platform

Start the stack with the load-test overlay (API on `127.0.0.1:8080`, quotas raised):

```sh
docker compose -f compose.yaml -f loadtest/compose.loadtest.yaml up -d --build
k6 run -e BASE_URL=http://127.0.0.1:8080 loadtest/m1-auth-and-reads.js
```

| Scenario | Load | SLO |
|---|---|---|
| `GET /api/v1/me` (JWT verify, Valkey revocation check, GCRA, PostgreSQL read, compression) | 500 req/s | p95 < 25 ms, p99 < 75 ms |
| Same with `If-None-Match` → `304` | 200 req/s | p95 < 20 ms, p99 < 60 ms |
| `POST /api/v1/auth/login` (Argon2id 19 MiB, t = 2) | 10 req/s | p95 < 250 ms, p99 < 500 ms |
| All scenarios | — | errors < 0.1 % |

Reference resources: API container limited to 2 vCPU / 512 MiB (`compose.yaml`).
Login latency is dominated by password hashing on purpose; its throughput is bounded by
`DZ_AUTH__MAX_CONCURRENT_HASHES` (default: number of CPUs).

Quick checks with oha:

```sh
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"load@example.test","password":"load test passphrase 2026"}' | jq -r .tokens.access_token)
oha -z 30s -c 64 -H "authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v1/me
oha -z 30s -c 64 http://127.0.0.1:8080/health/live
```

While a test runs, watch the API metrics on port 9090 (`dz_http_requests_total`,
`dz_http_request_duration_seconds`, `dz_http_rate_limited_total`) and PostgreSQL with
`pg_stat_statements`.

## Next milestones

* **M3 (real-time):** driver location ingest (100 updates/min per driver, 2 000 buses),
  WebSocket fan-out latency (p95 < 500 ms position-to-subscriber), connection soak (10 000
  sockets per API replica).
* **M2/M4:** catalogue and journey-planning reads with PostGIS (`EXPLAIN (ANALYZE, BUFFERS)`
  plans recorded next to each index in the migrations).
