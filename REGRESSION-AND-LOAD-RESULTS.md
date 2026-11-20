# Regression and load verification — 2026-11-20

## Confirmed passing
- `python tests/test_multiserver.py`: 74 assertions passed, 0 failed.
- `python tests/test_mongo_router.py`: 38 assertions passed, 0 failed.
- Targeted tests: retry affinity, capacity guard, distinct-user slots, core authority, pool health, gateway hardening: scripts exit 0.
- `python tests/test_500_user_routing_sim.py`: 500 assigned across 50 simulated nodes, 10 per node; 501st rejected.
- `python tests/test_500_http_load.py`: 500 real HTTP requests to one LOCAL aiohttp server simulating 50 independent node slot pools; 500 HTTP 200, peak 10 per simulated node, 0 rejected. This is NOT a real deployed 50-server test.
- Python compileall and Cloudflare Worker `node --check`: passed.

## Changes
- Updated outdated regression test expectations to match the implemented safe semantics: explicit 503 worker busy -> retryable failure, no immediate reroute; ambiguous forwarding failure -> retain affinity.
- MongoDB regression now checks critical collections pinned to core, and tests secondary failover with a genuinely non-critical collection (`vps_usage`).
- Added local synthetic HTTP concurrency benchmark.
- No production application code changed in this audit.

## Still not verified
- Real deployed 500 concurrent users through Telegram -> gateway -> 50 workers -> MongoDB, with actual ad gate and media delivery.
- Crash-durable acknowledgement (gateway/worker may acknowledge before work is durable).
- Correctness of cross-process 10 distinct user cap during restarts/failover.
- Real MongoDB throughput/connection budgets and Render or other host resource ceilings.
- Full integration tests with live infrastructure.

## Live staging load test prerequisites
- 50 isolated staging workers and a separate Telegram test bot.
- Test-only MongoDB databases, no production secrets or real user files.
- Metrics: successful unique updates, duplicate delivery, loss, 429/503, p50/p95/p99, max active users per node, MongoDB connections/ops, memory, CPU.
- Run gradually at 50, 100, 250, 500 concurrent users; test failure and recovery; ensure idempotent processing before declaring ready.
- Never send synthetic updates directly to production webhook.
