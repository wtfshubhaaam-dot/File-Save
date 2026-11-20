# Step 10 + 11: gateway job shutdown and internal request hardening

Changes:
- Gateway demotion now awaits cancellation of gateway-only asyncio tasks before returning.
- /internal/update rejects bodies larger than 1 MiB, checking Content-Length before reading and actual size after reading.
- Existing cluster HMAC signature verification and 10-slot admission remain unchanged.

Verified in this environment:
- tests/test_gateway_hardening.py: 2 checks PASS.
- tests/test_distinct_user_slots.py PASS.
- tests/test_capacity_guard.py PASS.
- tests/test_retry_affinity.py PASS.
- tests/test_pool_health.py PASS.
- tests/test_worker_overload.mjs: 3 checks PASS.
- Python compileall PASS.

Limitations:
- Awaiting cancellation is cooperative; a task that suppresses cancellation could delay demotion.
- The 1 MiB limit is application-side; reverse proxy/aiohttp server should also enforce request body size.
- Existing full test_multiserver.py and test_mongo_router.py failures are not resolved.
- No real Telegram, MongoDB, Cloudflare, or 500-user integration benchmark was run.
- NOT production-ready.
