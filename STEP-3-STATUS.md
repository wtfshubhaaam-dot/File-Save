# Step 3: capacity guard correction
- Cap NODE_CAPACITY and NODE_MAX_TASKS at 10 even when env requests more.
- Internal update endpoint now checks completed update IDs before capacity rejection, so completed retries can be acknowledged when server is full.
- New updates are still rejected when all 10 reserved processing slots are occupied.
- tests/test_capacity_guard.py: 2 targeted checks pass using existing stubs.
- tests/test_retry_affinity.py: 2 targeted checks pass.
- Python compileall passes.
- Full test_multiserver.py still fails (old dispatch assumptions); test_mongo_router.py fails (old hot-route assumptions).
- Strict 10 distinct active users, crash-durable delivery, and real 500-user load test are NOT verified.
