# Plan 011: Fix the multi-node usage-accounting NameError

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Usage-accounting changes must be
> verified on a real multi-node setup (`PROJECT_SPEC.md` §7).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/panel/usage.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2 (HIGH severity, but multi-node-only; single-VPS installs unaffected)
- **Effort**: S–M
- **Risk**: MED (accounting correctness — a wrong fix double-counts)
- **Depends on**: 001 recommended
- **Category**: correctness
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

On any parent/child (multi-node) deployment, `add_users_usage_uuid()` calls
`_add_users_usage(...)`, but that function exists **only** inside a commented-out
block — so the moment a child reports usage, the call raises `NameError`, the
parent never accumulates child usage, and the child's reconciliation aborts.
Total loss of usage accounting for multi-node. Single-node uses a different path
(`add_users_usage_new`) and is unaffected.

## Current state

```python
# hiddify-panel/src/hiddifypanel/panel/usage.py
39:  return add_users_usage_new([{'uuid': uuid, "usage": uinfo['usage']} for ...], child_id=0)  # single-node path (OK)
...
47: def add_users_usage_uuid(uuids_bytes: Dict[str, Dict], child_id, sync=False):
48:     uuids_bytes = {u: v for u, v in uuids_bytes.items() if v and v.get('usage', 0) > 0}
49:     uuids = uuids_bytes.keys()
50:     users = db.session.query(User).filter(User.uuid.in_(uuids))
51:     dbusers_bytes = {u: uuids_bytes.get(u.uuid, {"usage": 0}) for u in users}
52:     _add_users_usage(dbusers_bytes, child_id, sync)  # type: ignore   <-- NameError: only defined commented at :178
```
- `def _add_users_usage(...)` exists ONLY as a comment at `usage.py:178`.
- The working single-node path `add_users_usage_new` (~line 39 caller) takes a
  list of `{'uuid', 'usage'}` dicts and a `child_id`, and writes via the
  `add_usage_json` stored proc (idempotent on absolute `current_usage`).
- Callers of `add_users_usage_uuid`: parent ingest
  (`panel/commercial/restapi/v2/parent/usage_api.py`) and child reconciliation
  (`hutils/node/child.py`).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/panel/usage.py` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |
| (server, multi-node) | child reports usage → parent totals increase | value grows |

## Scope

**In scope**:
- `hiddify-panel/src/hiddifypanel/panel/usage.py` — make `add_users_usage_uuid`
  actually accumulate (route through `add_users_usage_new`, or restore a correct
  `_add_users_usage`).

**Out of scope**:
- The reset-on-read semantics (CORR-21, separate).
- `add_users_usage_new` / the `add_usage_json` SP.
- The parent/child API handlers.

## Git workflow

- Branch: `advisor/011-multinode-usage-nameerror`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Understand the two accounting shapes before changing anything

Read `add_users_usage_new` and the commented `_add_users_usage` (usage.py:178)
fully. Determine the exact argument shape `add_users_usage_new` expects and
whether it keys on absolute `current_usage` (idempotent) or deltas. The fix MUST
preserve idempotency — a retried child report must not double-count.

If the semantics match, the minimal fix is to route `add_users_usage_uuid`
through `add_users_usage_new`:
```python
def add_users_usage_uuid(uuids_bytes, child_id, sync=False):
    uuids_bytes = {u: v for u, v in uuids_bytes.items() if v and v.get('usage', 0) > 0}
    data = [{'uuid': uuid, 'usage': v['usage']} for uuid, v in uuids_bytes.items()]
    return add_users_usage_new(data, child_id=child_id, sync=sync)  # match the real signature
```
Confirm `add_users_usage_new` accepts `child_id` and `sync` (adjust to its actual
signature). If it does NOT support `sync` or per-`child_id` accounting the way
the commented `_add_users_usage` did, restore `_add_users_usage` from the
comment instead, adapting it to current models — but ONLY if you can verify its
accounting matches (no double-count).

**Verify**: `python -m py_compile .../usage.py` → exit 0;
`grep -n "_add_users_usage" .../usage.py` → only the commented line remains (if
you routed through `add_users_usage_new`) OR a live def you fully verified.

### Step 2: (MANDATORY multi-node server verification)

This cannot be validated single-node. On a parent+child staging setup: have the
child report usage and confirm the parent's per-user totals increase and do NOT
double-count across two reports of the same absolute usage.

**Verify (server)**: parent totals advance once per real delta; a repeated
report with the same absolute value does not add twice.

## Test plan

- Offline: if `add_users_usage_new`'s data-shaping is pure enough, add a test
  that `add_users_usage_uuid` builds the correct list from a `uuids_bytes` input
  (mock `add_users_usage_new` and assert the args). This catches the NameError
  and the shape without a DB.
- Server Step 2 is the real accounting gate.

## Done criteria

- [ ] `python -m py_compile .../usage.py` exit 0
- [ ] `add_users_usage_uuid` no longer references an undefined `_add_users_usage`
- [ ] Offline test asserts correct arg-shaping (mocked)
- [ ] (server, multi-node) usage accumulates without double-counting
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- `usage.py` drifted from the excerpt.
- `add_users_usage_new`'s signature/semantics do NOT match what
  `add_users_usage_uuid` needs (e.g. no `sync`, no per-child) — STOP and report;
  do not guess an accounting path that might double-count.
- You cannot access a multi-node staging setup — deliver the source fix + offline
  test but mark the plan BLOCKED-on-verification in the index, not DONE.

## Maintenance notes

- Idempotency is the invariant: accounting keyed on absolute `current_usage`.
- Reviewer: scrutinize double-count risk hardest; this is the whole reason it's MED-risk.
- Related deferred: CORR-21 (reset-on-read before commit loses a cycle on DB error).
