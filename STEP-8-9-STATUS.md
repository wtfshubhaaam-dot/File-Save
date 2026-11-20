# Step 8+9 — Overload and Cloudflare Worker routing
Changes:
- Worker tries at most three origins per request, not all 50.
- Explicit 429/503 can try another origin; HTTP 5xx and network timeouts stop retries to prevent DB/stream amplification.
- Existing per-server 10-slot admission and HTTP 503 backpressure retained.
- This is conservative: a transient network failure can cause a 503 even when another origin is healthy. Client should retry after delay.

Verification:
- Node.js mocked Worker tests: 3 passed (50-origin 503 cap, HTTP 500 stop, network-error stop).
- Python compileall passed; targeted distinct-user admission test passed.
- Real Cloudflare, Telegram, MongoDB, and 500-user load tests not run.
- Full legacy multi-server and MongoDB regression suites remain unresolved.
- NOT production-ready.
