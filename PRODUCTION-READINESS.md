# Multi-server 10-active-user cap: safety patch, NOT production certified

Changes in this patch:
- Gateway router no longer deliberately overflows active-user capacity.
- Gateway returns HTTP 503 when no capacity is available, allowing Telegram retries rather than acknowledging dropped updates.
- A gateway only marks an update as delivered after an acknowledged handoff. Ambiguous forwarding timeouts are NOT forwarded to another node immediately.
- Critical mutable collections (daily_usage, ad_sessions, pending_deletes) are pinned to core MongoDB to avoid split-brain data on secondary recovery. This is a correctness-versus-load tradeoff; core capacity MUST be benchmarked.

Known limitations requiring more engineering and staging verification:
- 10 distinct active users is not a globally atomic guarantee: router assignments are in gateway memory, worker task caps are not per-user quotas, and concurrent gateway takeover can briefly overlap assignment state.
- Telegram update processing is asynchronous after acknowledgement; a worker crash can lose accepted work. Durable inbox / queue with idempotent consumers is needed for stronger guarantees.
- Worker-to-worker request replay is time-bound by HMAC timestamp but not persisted as one-time nonce.
- Gateway dedupe is process-local and not durable across restarts.
- Other stateful collection routing overrides should be audited for data consistency.
- All 50+ server scaling claims require real MongoDB Atlas pool and throughput measurements; no live load test was run.
- Existing tests encode old overflow/fallback behavior and must be updated to new safety policy before release.

DO NOT deploy this patch as production certified. Run two-node staging, test 503/retry, forced worker crash, gateway takeover, hot Mongo outage/recovery, and 500 concurrent workload with realistic file sizes.
