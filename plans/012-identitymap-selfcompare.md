# Plan 012: Fix identity-map self-comparison in User/Domain change hooks

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Live effect (client removal / config
> rebuild) verified on a real server (`PROJECT_SPEC.md` §7).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/panel/admin/UserAdmin.py hiddify-panel/src/hiddifypanel/panel/admin/DomainAdmin.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: MED (touches flask-admin change-hook ordering)
- **Depends on**: none
- **Category**: correctness / security-adjacent (revoked-UUID keeps working)
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Both `UserAdmin.on_model_change` and `DomainAdmin.on_model_change` fetch the
"old" row with `User.by_id(model.id)` / `Domain.by_domain(model.domain)` — but
SQLAlchemy's identity map returns the **same instance** already mutated by
flask-admin's `populate_obj`, so `old.X != model.X` is always False. Consequences:
(1) changing a user's UUID never removes the old client from xray/singbox — the
revoked credential keeps working; (2) changing a domain's mode without also
editing a port/key never marks config dirty, so traffic keeps using the old
mode's inbounds. DomainAdmin already uses the CORRECT pattern
(`sa_inspect(model).attrs[...].history.has_changes()`) two lines below the bug —
use it as the in-file exemplar.

## Current state

```python
# UserAdmin.py  (on_model_change)
294:  old_user = User.by_id(model.id)                    # identity-mapped == model (already mutated)
...
304:  if old_user and old_user.uuid != model.uuid:       # always False
305:      user_driver.remove_client(old_user)            # never runs
```
```python
# DomainAdmin.py  (on_model_change)
398:  old_db_domain = Domain.by_domain(model.domain)     # identity-mapped == model
399:  if is_created or not old_db_domain or old_db_domain.mode != model.mode:   # mode check always False on edit
...
403:  elif any(sa_inspect(model).attrs[attr].history.has_changes()             # <-- CORRECT pattern already here
404:           for attr in ('http_port', 'tls_port', 'reality_port', ...)):
```
`sa_inspect` is already imported in DomainAdmin.py (used at :403). Confirm the
import name in UserAdmin.py (likely `from sqlalchemy import inspect as sa_inspect`
— add it if absent).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/panel/admin/{UserAdmin,DomainAdmin}.py` | exit 0 |
| (server) UUID change | edit a user's UUID → old client removed from cores | old UUID stops working |
| (server) mode change | edit a domain's mode only → apply prompt appears, config rebuilt | new mode active |

## Scope

**In scope**:
- `DomainAdmin.py:399` — use `sa_inspect(model).attrs['mode'].history.has_changes()`.
- `UserAdmin.py:294-305` — capture the pre-change uuid via SQLAlchemy history
  before comparing, and remove the OLD client.

**Out of scope**:
- The port/key `elif` block in DomainAdmin (already correct — do not touch).
- `can_have_more_users()` guard placement (separate smell, plan 015 family).
- `user_driver.remove_client` internals.

## Git workflow

- Branch: `advisor/012-identitymap-selfcompare`. Commit per file. No push/PR unless instructed.

## Steps

### Step 1: Fix DomainAdmin mode detection (use the in-file exemplar)

Change line 399's mode comparison to the history-based check already used at
:403:
```python
if is_created or not old_db_domain or sa_inspect(model).attrs['mode'].history.has_changes():
```
Keep the `is_created`/`not old_db_domain` guards for the create case.

**Verify**: `python -m py_compile .../DomainAdmin.py` → exit 0;
`grep -n "old_db_domain.mode != model.mode" .../DomainAdmin.py` → no matches.

### Step 2: Fix UserAdmin UUID-change client removal

The old UUID is available from SQLAlchemy history AFTER `populate_obj`:
`sa_inspect(model).attrs['uuid'].history.deleted` holds `[old_uuid]` when it
changed. Use it to remove the old client:
```python
from sqlalchemy import inspect as sa_inspect   # if not already imported
...
uuid_hist = sa_inspect(model).attrs['uuid'].history
if uuid_hist.deleted:                    # uuid actually changed
    old_uuid = uuid_hist.deleted[0]
    # remove_client needs a user-like object carrying the OLD uuid:
    from copy import copy
    stale = copy(model); stale.uuid = old_uuid
    user_driver.remove_client(stale)
```
Confirm what `user_driver.remove_client` actually reads off the object (likely
`.uuid`); if it needs more fields, build the stale object accordingly. Remove the
now-dead `old_user = User.by_id(model.id)` line if nothing else uses it (check
lines 294-305 context — `model.added_by` logic at :295-296 does NOT use
`old_user`, so it can go).

**Verify**: `python -m py_compile .../UserAdmin.py` → exit 0.

### Step 3: (MANDATORY server verification)

On a box: (a) change a user's UUID, confirm the old UUID no longer connects
(client removed from xray/singbox); (b) change ONLY a domain's mode (no port
edit) and confirm an apply is triggered and the new mode's inbounds are live.

**Verify (server)**: old UUID rejected; domain mode change rebuilds config.

## Test plan

- Offline: history-based detection is hard to unit-test without a real session;
  if feasible, add a test using an in-memory SQLite session that loads a row,
  mutates `mode`/`uuid`, and asserts `sa_inspect(obj).attrs['x'].history.has_changes()`
  / `.deleted` behave as used. Otherwise rely on server Step 3 and note it.
- Server Step 3 is the real gate (client removal + config rebuild).

## Done criteria

- [ ] `py_compile` clean on both files
- [ ] DomainAdmin mode check uses `history.has_changes()`
- [ ] UserAdmin removes the OLD client on UUID change (via history.deleted)
- [ ] (server) revoked UUID stops working; mode-only change rebuilds config
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Either file drifted from the excerpts.
- `user_driver.remove_client` needs fields not present on a shallow-copied model
  carrying only the old uuid — report what it needs before improvising.
- flask-admin calls `on_model_change` BEFORE `populate_obj` in the pinned version
  (then history wouldn't be populated yet) — verify the ordering; if so, STOP and
  report (the whole approach depends on populate-then-hook ordering).

## Maintenance notes

- The root anti-pattern is "fetch old row by natural/primary key inside a change
  hook" — the identity map defeats it. Prefer `sa_inspect(model).attrs[...].history`.
- Reviewer: check for the same pattern in other ModelViews' `on_model_change`.
