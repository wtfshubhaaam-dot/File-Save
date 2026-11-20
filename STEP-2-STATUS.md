# Step 2: retry affinity fix
- On ambiguous worker forwarding failures, keep the sticky user-to-worker assignment and return retryable failure. This reduces the chance that Telegram retries are delivered to a different worker.
- On explicit worker 503 (not accepted), clear the user assignment and temporarily mark worker busy, so retry can choose another.
- Added tests/test_retry_affinity.py: 2 targeted scenarios passed with stub dependencies.
- Python compileall passed.
- Legacy multi-server and MongoDB test suites remain failing due to old behavioral expectations; not certified.
- This is NOT durable deduplication or a guarantee against duplicates after process crashes. Real multi-server staging and load testing required.
