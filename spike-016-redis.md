# Spike Report: Dropping Redis on Single-Node Installs (Plan 016)

## Findings

1. **Cross-Process Cache Invalidation Exists:**
   - The Celery background tasks worker (specifically `update_local_usage_not_lock` -> `hiddify.quick_apply_users()`) eventually triggers `cache.invalidate_all_cached_functions()` via `SettingAdmin.py` or similar flows, which invalidates cached configurations used by the web workers.
   - Other instances include domains and proxies being invalidated.

2. **Impact on Caching Correctness:**
   - Because Celery runs in a separate process from the web workers (uwsgi/Flask), an in-process LRU cache (like a simple dictionary in the Flask app) would **break cache coherence**. The Celery worker would invalidate its own local cache, leaving the web workers serving stale configurations.

## Escalate Condition Met

Per the plan's escalate conditions:
> The spike finds cross-process cache invalidation (web worker ↔ celery/ background tasks) — an in-process cache would serve stale data. STOP; this must be sequenced with plan 020 (fold Celery in) or solved another way.

## Next Steps
This spike is complete and execution must STOP here. Phase 2 (implementation) cannot proceed safely without either:
- A cross-process signaling mechanism (e.g., file-based signaling or IPC).
- Folding Celery into the main process first (Plan 020).
