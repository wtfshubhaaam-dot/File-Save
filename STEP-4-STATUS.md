# Step 4 — Distinct in-flight user admission
- Added per-user in-flight reservation counts; maximum 10 distinct users and 10 admitted updates per server.
- Duplicate update IDs do not consume extra slots.
- Spawn failure rolls back user and update reservations.
- Hardened NODE_HARD_TASKS to <= 10 in cluster mode even if environment sets higher.
- Targeted tests: test_distinct_user_slots.py (3 assertions groups), test_capacity_guard.py (2), test_retry_affinity.py (2): PASS.
- Python compilation: PASS.
- Existing full tests: test_multiserver.py fails at legacy dispatch acknowledgement expectation; test_mongo_router.py fails at outdated hot daily_usage routing expectation.
- Scope: in-flight admitted operations, not a persistent ten-user session cap or a distributed cross-node admission guarantee.
- Not production ready. No real MongoDB/Telegram or 500-user load tests run.
