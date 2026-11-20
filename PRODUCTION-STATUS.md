# Multi-server release status — NOT CERTIFIED FOR PRODUCTION

Target: 10 concurrent processing slots per node; 500 active users require at least 50 nodes plus headroom.

## This patch
- Added a bounded, process-local admission reservation (`live.reserved`) BEFORE accepting an internal update or locally dispatching an update. Waiting tasks count against the 10-slot cap; no unbounded local task queue is created by this path.
- Preserved prior HMAC forwarding, 503 backpressure and core-pinned quota/ad-session/delete state.
- Python compileall completed successfully.

## Release blockers
- Gateway/worker accepted updates are not durably queued: process crash can lose an acknowledged update.
- 10 *distinct active users* is NOT enforced atomically across gateway failover. The 10-slot processing cap is distinct from 10 active users.
- Router assignments and dedupe are in process memory, not durable or globally atomic.
- Secondary Mongo fallback for non-core collections can split data; never treat it as transactional failover.
- MongoDB secondary recovery, actual Atlas index behavior and 500-user load are untested.
- Existing tests still encode old routing expectations; they do not pass as shipped.
- 50 nodes x 5 MongoDB pool size may use 250 pooled connections per cluster, before monitoring and other clients. Atlas tier limits must be measured.

Do NOT deploy this build to production without resolving blockers and staging/load verification.
