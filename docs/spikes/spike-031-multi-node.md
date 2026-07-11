# 031 Multi-Node Load Test - Phase 1 Spike

## Goal
Validate the existing parent/child multi-node sync behavior, identifying partition semantics, conflict resolution, and confirming the independent-DB premise needed for the SQLite migration (plan 015).

## Sync Model Discovery

### 1. Registration (`ChildMode.remote` connecting to `ChildMode.parent`)
- A remote node initiates registration by calling `__get_register_data_for_api` (in `child.py`).
- It sends **its entire database state** to the parent: `admin_users`, `users`, `domains`, `proxies`, `hconfigs`.
- The parent (`register_to_parent` endpoint) bulk-registers all these items.
- *Wait, no:* `register_to_parent` in `child.py` is the *child* sending its request. The endpoint itself is in `parent/register_api.py`.
Let me look at `parent/register_api.py` and `child/sync_with_parent`.

### 2. Synchronization (`sync_with_parent`)
- **Triggered when:**
  - Background task triggered on domain creation/deletion, config changes (`Actions.py`, `DomainAdmin.py`, `ProxyAdmin.py`, `SettingAdmin.py`).
- **Direction:** Child pushes state *to* parent. (Wait, let's verify.)
  - `sync_with_parent` calls `__get_sync_data_for_api(*fields)`, grabbing ALL `Domain`, `Proxy`, `StrConfig`, `BoolConfig` records.
  - Puts them to `/api/v2/parent/sync/` on the parent.
  - Parent's `SyncApi` endpoint (`parent/sync_api.py`):
    - Reads domains, proxies, hconfigs from the request.
    - Saves them using `bulk_register` with `force_child_unique_id=child.unique_id`.
    - Returns its own `users` and `admin_users`.
  - Child receives response:
    - Overwrites its local users: `AdminUser.bulk_register(res['admin_users'], remove=True)`, `User.bulk_register(res['users'], remove=True)`.

- **Usage Sync (`sync_users_usage_with_parent`)**
  - Child posts its usage dict. Parent adds it to users' usage (`usage.add_users_usage_uuid`).

## Conflict Resolution & Behavior
- **Config / Domains / Proxies:** Child is authoritative for its own records. Parent just saves them tagged with `child_id`.
- **Users / Admins:** Parent is authoritative. The child gets full syncs of users/admins from the parent and completely overwrites its local copies (`remove=True`).
- **Conflict Strategy:** "Last write wins" (bulk overwrite) for users on the child.
- **Partition Behavior:** If child is disconnected, local config changes queue? No queue mechanism found. `sync_with_parent` just returns `False` if API call fails. Data changed on child while partitioned will just get sent on the *next* successful sync trigger. If user data changes on parent, child won't know until next sync.

## The Independent-DB Premise (Plan 015)
- **Confirmed:** Yes, each node (parent and children) has its own local DB. The child reads/writes its own local DB. Syncing happens via HTTP/REST API calls (`NodeApiClient`) passing JSON.
- There is NO shared database connection. The multi-node design assumes each node is fully independent and state is passed via the REST API. This validates that moving to SQLite per-node will not break multi-node architecture (in fact, it's exactly what the architecture implies).

## Risk List / Failure Modes to Test (Phase 2)
1. **Sync Failures are Silent/Lost:** `run_node_op_in_bg` might swallow errors if the parent is down. A domain added while partitioned might never sync to parent unless another config change triggers a full sync.
2. **Bulk Register Scale:** Syncing users passes *all* users every time (`User.query.all()`). For a panel with 100k users, this JSON payload will be massive and slow down the sync API.
3. **Usage Conflicts:** If usage is synced concurrently or out of order, does `add_users_usage_uuid` handle increments correctly or just overwrite? (needs inspection)

## Conclusion
The single-writer per-node premise holds. Coordination is purely HTTP REST sync. SQLite (plan 015) is architecturally safe. However, the sync implementation is naive (full state transfer instead of deltas) and will likely strain under heavy load/user count.
