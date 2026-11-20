# Steps 6 and 7 — MongoDB pooling and health-aware routing

Changes:
- Cluster-mode MONGO_MAX_POOL bounded to 1..5 per node per cluster; Motor minPoolSize=0 to avoid idle socket reservations.
- Worker heartbeats now advertise live reserved processing slots.
- Router excludes stale workers and workers reporting all processing slots reserved.
- Periodic healthz probes run concurrently with a four-second per-node timeout instead of sequential thirty-second waits.

Verification:
- Python compileall: PASS.
- Targeted tests: test_pool_health.py, test_distinct_user_slots.py, test_capacity_guard.py, test_retry_affinity.py PASS.
- Legacy test_multiserver.py FAIL (dispatch expects acknowledgement under old semantics).
- Legacy test_mongo_router.py FAIL (expects daily_usage routed to hot instead of core).
- No real MongoDB, Telegram, Cloudflare, 50-server, or 500-user performance test.

Caveats:
- MaxPoolSize limits pool connections per node/cluster, not aggregate sockets across all apps or monitoring sockets.
- A full worker may be skipped until next heartbeat refresh (10s beat, 5s refresh).
- No guarantee of strict global 10-user cap across process restarts or duplicate node IDs.
- This is not production certification.
