# Step 5: MongoDB authoritative state consistency

Change: `daily_stats` is now core-only, joining `daily_usage`, `ad_sessions`, and `pending_deletes`. This prevents those four collections from being written to a secondary and then split between clusters during secondary outages and recovery. `MONGO_ROUTES` cannot override this safety rule.

Tests: `tests/test_core_authority.py` PASS with fake MongoDB. Previous targeted tests for distinct-user admission, capacity, retry affinity PASS. Python compilation PASS.

Trade-off: all four collections now load the core database; this is consistency-first, **not** an optimization for core DB throughput. Other secondary collections (`vps_usage`, `cluster_stats`) still have cross-cluster fallback and may split. Old MongoDB routing tests still expect the unsafe historical routing and must be updated, not blindly treated as passing. No real Atlas staging, concurrency benchmark, or 500-user load test has been performed.

Production status: NOT READY.
