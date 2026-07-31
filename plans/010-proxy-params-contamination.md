# Plan 010: Stop `make_proxy` from mutating the cached Proxy.params dict

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 001 (test baseline) recommended — this fix is unit-testable
- **Category**: correctness
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

`make_proxy()` aliases the live, cached `Proxy.params` ORM JSON dict into the
per-request proxy dict, then mutates it in place (injects default headers and a
`download` key). Because `get_proxies()` is cached (`ttl=300`) and the same
`Proxy` objects are reused across every domain in `get_valid_proxies()`, those
mutations persist and leak into other domains' and later requests' generated
links — cross-domain/cross-request config contamination. Affects single-node
installs, not just multi-node.

## Current state

```python
# hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py
631:    'params': proxy.params or {},         # aliases the live ORM dict when non-empty
...
690:    put_default_header(base['params'])    # mutates it in place
...
696-698:  base['params']['download'] = ...    # inserts into the same shared dict
```
`proxy.params` is `Column(JSON, default=dict)` on the `Proxy` model. `get_proxies()`
is `@cache.cache(ttl=300)`; the returned `Proxy` objects are reused per domain.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass incl. new test |

## Scope

**In scope**:
- `hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py` line 631 (copy the dict).
- `hiddify-panel/src/tests/test_make_proxy_params.py` (create) if `make_proxy`
  is unit-testable with stubbed ORM objects; otherwise a smaller targeted test.

**Out of scope**:
- `put_default_header` / the `download` logic (they can keep mutating — once the
  dict is a copy, mutation is safe).
- The `@cache` decorator on `get_proxies`.
- Other fields in the returned dict.

## Git workflow

- Branch: `advisor/010-proxy-params-contamination`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Copy the params dict instead of aliasing

Change line 631 from `'params': proxy.params or {},` to a copy:
```python
'params': dict(proxy.params) if proxy.params else {},
```
If `proxy.params` can contain nested dicts that are ALSO mutated downstream
(check `put_default_header` and the `download` insertion — the `download` value
may itself be a dict), use `copy.deepcopy(proxy.params)` instead. Read those two
sites to decide; prefer `dict(...)` (shallow) if only top-level keys are mutated.

**Verify**: `python -m py_compile .../shared.py` → exit 0;
`grep -n "'params': proxy.params or {}" .../shared.py` → no matches.

### Step 2: Add a regression test

In `tests/test_make_proxy_params.py`, construct a fake `Proxy` with a non-empty
`params` dict, call `make_proxy` twice (or across two domains) and assert the
original `proxy.params` is unchanged after the call (no injected headers /
`download` key leaked back into it). Stub the ORM objects as simple namespaces
(the audit notes `Proxy`/`Domain`/`hconfigs` are attribute bags). If `make_proxy`
needs too much app context to call directly, instead unit-test the narrower
invariant: that mutating the returned `base['params']` does not affect the input
`proxy.params` (i.e. assert `base['params'] is not proxy.params`).

**Verify**: `cd hiddify-panel/src && python -m pytest tests/test_make_proxy_params.py -v` → pass.

## Test plan

- New test asserts input `proxy.params` is not mutated / not aliased.
- Follow the structural pattern of plan 001's tests (import-light, specific
  asserts).

## Done criteria

- [ ] `python -m py_compile .../shared.py` exit 0
- [ ] Line 631 copies the dict (no direct alias)
- [ ] New test proves `proxy.params` is not mutated by `make_proxy`
- [ ] `pytest tests/` green
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- `shared.py` drifted from the excerpt.
- Downstream code mutates NESTED dicts inside params (then a shallow `dict()` is
  insufficient — switch to `deepcopy` and note it).
- `make_proxy` cannot be exercised at all offline even for the narrow invariant —
  deliver the source fix + a `is not` identity assertion and note the coverage limit.

## Maintenance notes

- Root cause is aliasing a cached ORM mutable; watch for the same pattern
  elsewhere in `hutils/proxy/*` (e.g. any `x = proxy.<json_col>` followed by
  in-place mutation).
- Reviewer: confirm no downstream code relied on the leak (unlikely — it was a bug).
