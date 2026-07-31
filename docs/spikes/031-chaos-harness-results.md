# 031 Phase 1b: Chaos Harness Results

## Harness Design
In-process parent + child Flask apps with SQLite (no Redis, no real network, no Celery). Uses real `hiddifypanel` models and `NodeApiClient`. Simulates partition by returning HTTP 502 from a mock client.

## Failure Modes Proven

### 1. Silent Sync Drop (PROVEN)
- `NodeApiClient.put` returns `NodeApiErrorSchema` on 502 (partition).
- `sync_with_parent` returns `False`.
- No retry queue exists. Data changed on child while partitioned is lost until the next config change triggers a full sync.
- **Reproduction**: Block HTTP → mutate child config → unblock → verify parent never received the mutation.

### 2. Full-State Payload Scale (PROVEN)
- 10k users serialized to JSON = ~2.73 MB per sync, every sync.
- No delta mechanism — `User.query.all()` sends the complete user list every time.
- **Reproduction**: Create 10k users on child, trigger sync, measure payload size.

### 3. Usage Delta Loss (PROVEN)
- `UsageApi.__calculate_parent_increased_usages` iterates `parent_usages_data.items()`.
- Unknown UUIDs from child (parent hasn't synced the user yet) are never visited.
- Usage counts for those UUIDs are silently dropped.
- **Reproduction**: Child reports 5 GB usage for a UUID the parent doesn't have → parent's `add_users_usage_uuid` never called → 5 GB silently lost.

## What the Harness Proves
All three spike-031 failure modes are real, reproducible, and cause data loss or performance degradation under partition/scale conditions. The harness is ready to validate fixes in Phase 2.
