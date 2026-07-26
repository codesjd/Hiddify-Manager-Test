# Plan 015: Batch of independent one-line correctness fixes

> **Executor instructions**: Each item below is INDEPENDENT. For EACH item:
> (1) open the file at the given line, (2) confirm the "current" excerpt matches
> live code — if it does not, SKIP that item and note it (drift), do not guess;
> (3) apply the one-line fix; (4) run the item's verify. Commit per item or in
> small logical groups. Update `plans/README.md` when done. Do NOT bundle a fix
> whose current code doesn't match — report it instead.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/panel/cli.py hiddify-panel/src/hiddifypanel/drivers/ssh_liberty_bridge_api.py hiddify-panel/src/hiddifypanel/drivers/xray_api.py hiddify-panel/src/hiddifypanel/hutils/node/api_client.py hiddify-panel/src/hiddifypanel/panel/admin/UserAdmin.py hiddify-panel/src/hiddifypanel/models/base_account.py hiddify-panel/src/hiddifypanel/hutils/network/net.py`

## Status

- **Priority**: P2
- **Effort**: S (each item minutes)
- **Risk**: LOW (each is a localized one-liner)
- **Depends on**: 001 recommended
- **Category**: correctness
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

A cluster of small, high-confidence bugs — each a one-liner with clear correct
behavior. Individually minor; together they remove real papercuts (dropped SSH
usage, garbage CLI output, a dead node-response validator, over-fetching a count).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile (per file) | `python -m py_compile <file>` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |

## Scope

**In scope**: exactly the files/lines listed per item below. **Out of scope**:
anything not listed; do not "improve" adjacent code (repo rule §0.2).

## Items

### 015-a — SSH driver drops usage every cycle (`int += str`)
- File: `drivers/ssh_liberty_bridge_api.py` (`get_all_usage`, ~line 42-51). The
  redis client uses `decode_responses=True`, so counters come back as `str`, then
  `user_driver.py:33` does `int += str` → TypeError → the whole SSH driver's
  usage is discarded (after counters were already reset).
- Fix: cast in `get_all_usage`: return `{k: int(v) for k, v in allusage.items()}`.
- Verify: `python -m py_compile .../ssh_liberty_bridge_api.py` → exit 0. (Live: SSH usage accrues when `ssh_server_enable`.)

### 015-b — TUIC CLI prints the ORM object, not the hostname
- File: `panel/cli.py:106` — `f"{domain}:{int(hconfig(ConfigEnum.tuic_port))+domain.id}"`.
  Sibling `hysteria_domain_port()` at :97 correctly uses `{domain.domain}`.
- Fix: `f"{domain.domain}:..."`.
- Verify: `grep -n 'f"{domain}:' .../cli.py` → no matches; py_compile exit 0.

### 015-c — `import_config` updates bool configs via the wrong map
- File: `panel/cli.py:200` — inside `if k in boolmap:` it filters
  `BoolConfig.key == strmap[k]` (should be `boolmap[k]`) → KeyError / wrong row.
- Fix: use `boolmap[k]`.
- Verify: read the surrounding block to confirm `boolmap`/`strmap` names; py_compile exit 0.

### 015-d — Node responses never validated (always-true isinstance)
- File: `hutils/node/api_client.py:51` — `return resp if isinstance(output_schema, type(dict)) else output_schema().load(resp)`.
  `type(dict)` is `type`, and `output_schema` is always a class, so the check is
  always True → the marshmallow `.load()` branch is dead (no validation/remap).
- Fix: `isinstance(output_schema, type(dict))` → `output_schema is dict`.
- Verify: py_compile exit 0. NOTE: enabling real `.load()` may surface latent
  schema mismatches on node payloads — if this is multi-node-active, verify on a
  parent/child staging box; if you cannot, apply the fix but flag it for
  multi-node verification in your report.

### 015-e — Node calls have no timeout, catch only HTTPError
- File: `hutils/node/api_client.py` (`__call`, ~lines 33/35/53) —
  `requests.request(...)` with no `timeout=`; retry loop excepts only
  `requests.HTTPError`, so `ConnectionError`/`Timeout`/`JSONDecodeError` escape.
- Fix: add `timeout=5` to the request; broaden the except to
  `requests.RequestException`; add a small `sleep` between retries. (Match
  `telemt_api`, which already passes `timeout=5`.)
- Verify: py_compile exit 0. (Prevents a hung node blocking the sync thread.)

### 015-f — Admin user-list count over-fetches the whole table (PERF-05)
- File: `panel/admin/UserAdmin.py:205` and `:273` — `len(User.query.all())` fully
  hydrates every user just to count. (Line 378 already has `# count = query.count()`
  commented — the right way.)
- Fix: replace both with `User.query.count()`.
- Verify: `grep -n "User.query.all()" .../UserAdmin.py` → no matches at 205/273; py_compile exit 0.

### 015-g — `base_account.get_id()` is broken code
- File: `models/base_account.py:31` — `f'{self.__class__.name}_{self.id if self.hasattr("id") else "-"}'`:
  `self.hasattr(...)` isn't a method (AttributeError) and `self.__class__.name` is
  the mapped Column, not `__name__`. (Contained — subclasses override it — but wrong.)
- Fix: `f'{self.__class__.__name__}_{self.id if hasattr(self, "id") else "-"}'`.
- Verify: py_compile exit 0.

### 015-h — net.py literal-IP fast path is dead code
- File: `hutils/network/net.py:150` — `return set(ipaddress.ip_address(domain))`;
  the address object isn't iterable, so `set(...)` raises, caught by a bare
  `except:`, falling through to a full DNS lookup for a literal IP.
- Fix: `return {ipaddress.ip_address(domain)}`.
- Verify: py_compile exit 0.

### 015-i — xray `get_enabled_users_terminal` tests the wrong length
- File: `drivers/xray_api.py:199` — `if len(data)>0: return users` where `data`
  is the whole parsed object but `users` derives from `data['users']`; a tag
  returning `{"users": []}` short-circuits remaining tags with an empty list.
- Fix: `if len(users) > 0`.
- Verify: py_compile exit 0. (Confirm `users`/`data` names in context first.)

## Test plan

- Where a helper is pure (015-b hostname formatting, 015-g get_id, 015-h literal
  IP, 015-f count semantics), add a small assertion to `tests/` following plan
  001's pattern. The driver items (015-a/d/e/i) are better verified on a server;
  add offline tests only where they don't need live drivers.
- `pytest tests/` must stay green.

## Done criteria

- [ ] Each applied item's `python -m py_compile` exits 0
- [ ] `grep` checks in each item confirm the old pattern is gone
- [ ] `pytest tests/` green
- [ ] Any SKIPPED item (drift) is reported, not silently left
- [ ] No files outside the listed lines modified
- [ ] `plans/README.md` row updated (note which items landed vs skipped)

## STOP conditions (per item)

- The item's current excerpt doesn't match live code → SKIP + report (do not guess).
- 015-d/015-e change node behavior — if multi-node is live and you can't verify,
  apply but flag for staging verification rather than marking fully DONE.

## Maintenance notes

- These were split out from a larger audit; the remaining MED-confidence smells
  (port collision at domain id≥100, Outbound/RoutingRule delete not rebuilding
  config, admin self-edit double-`del` 500, raw ConfigAdmin cache staleness,
  telemt filter column, single-outbound xrayjson usage-config drop) are listed in
  `plans/README.md` "Findings considered / deferred" as separate investigate items,
  NOT included here because they need more than a one-liner or real-server semantics.
