# 031 Multi-Node Load Test - Phase 1 Spike

## Goal
Validate the existing parent/child multi-node sync behavior, identifying partition semantics, conflict resolution, and confirming the independent-DB premise needed for the SQLite migration (plan 015).

## Sync Model Discovery

### 1. Direction and Autonomy
- **Mode:** `PanelMode.child` and `PanelMode.parent`
- **Direction:** The sync goes `Child -> Parent`.
  - When domains, configs, or proxies change on the child, `run_node_op_in_bg(hutils.node.child.sync_with_parent, ...)` is triggered.
  - The child reads ALL its local records for that type and does an HTTP `PUT /api/v2/parent/sync/` to the parent.
- **Parent Handling:** The parent's `SyncApi` bulk registers the child's data into its DB, explicitly tagging them with `child.unique_id`.
- **Users:** The child *receives* the parent's user list in the sync response (`res.users`, `res.admin_users`) and *completely overwrites* its local copy of users/admins (`remove=True`).
- **Conclusion on Authority:**
  - Child is authoritative for its own configs, domains, and proxies.
  - Parent is authoritative for users and admin users.

### 2. Usage Sync
- **Trigger:** Child sends usage to parent via `sync_users_usage_with_parent` (`PUT /api/v2/parent/usage/`).
- **Parent Handling:** Parent (`UsageApi`) gets its own current usage, compares it to the child's reported usage, calculates the *increase* (delta), and applies the delta to its local user records using `add_users_usage_uuid`.
- **Conclusion:** Usage sync is explicitly built to handle deltas based on state comparisons. Concurrent usage syncs from multiple children update the total correctly.

### 3. Conflict & Partition Behavior
- **Conflicts:** "Last write wins". Because the child sends its *entire* list of proxies/domains every time, any parallel modification on the parent to the child's data (if allowed) would be instantly overwritten by the child. 
- **Partitions:** If the child is partitioned from the parent, local config changes queue? **No queue.** `run_node_op_in_bg` fires the sync in a thread, and if the API call fails, it just logs an error and aborts. The data remains locally out of sync until the *next* config change triggers another full state transmission.
- **User Updates on Partition:** Since the child pulls users on config syncs (and probably a cron schedule for usage), users created on the parent while partitioned won't exist on the child until the partition heals and a sync is triggered.

### 4. The Independent-DB Premise (Plan 015)
- **Confirmed:** YES. Each node reads and writes to its own local DB. The child makes `db.session.commit()` on its local database, and syncs via HTTP REST (`NodeApiClient`).
- There is NO shared database connection or shared DB host constraint between parent and child.
- This fully validates that the SQLite-per-node migration (plan 015) is architecturally sound and will not break multi-node. The architecture already treats them as independent state machines.

## Risk List / Failure Modes to Test (Phase 2)
1. **Sync Failures are Silent/Lost:** If a config is saved while the parent is down, the child logs an error but there's no retry queue. If no other configs are changed for a week, that child's configs are missing on the parent for a week.
2. **Payload Size (Scale issue):** Syncing users passes *all* users every time (`User.query.all()`). For a panel with 10k users, this JSON payload will be massive. This is a severe performance bottleneck for horizontal scaling.
3. **Missing usage records:** `UsageApi` on the parent has a known warning state if the child sends usage for a UUID the parent doesn't know. If user sync is delayed, usage counts might get dropped silently.

## Conclusion
The single-writer per-node premise holds. Coordination is purely HTTP REST sync. SQLite (plan 015) is architecturally safe.
However, the actual sync implementation is naive (transmits full state instead of deltas for users/configs) and has no retry queue for partitions, which means "scale horizontally" works functionally but will hit hard performance limits and transient data-loss bugs at scale.
