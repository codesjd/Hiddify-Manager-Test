# Plan 003: Cap Redis memory (maxmemory + eviction policy)

> **Executor instructions**: Follow step by step. Run verifications, honor STOP
> conditions, update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- other/redis/redis.conf`
> Mismatch vs the "Current state" excerpt → STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Redis is the panel's cache and (currently) the Celery broker + result backend.
`redis.conf` sets no `maxmemory` and no eviction policy, so its RSS can climb
without bound under key churn or missed TTLs — a slow-OOM path on a 512 MB box.
The data is a pure cache/broker (safe to evict), so a cap + `allkeys-lru`
bounds the ceiling with no correctness impact.

## Current state

- `other/redis/redis.conf` sets `bind`, `dir`, logging, `supervised systemd`,
  and (appended by the installer) `requirepass` — but **no `maxmemory` and no
  `maxmemory-policy`** (verified: grep for `maxmemory` returns nothing).
- Redis is used as: app cache (`hiddify-panel/src/hiddifypanel/cache.py`,
  many `@cache.cache(ttl=...)` sites, fail-open on read) and Celery
  broker/result backend (`celery.py`). The cache recomputes on miss.
- `other/redis/install.sh` appends `requirepass` to this file if absent — do
  not disturb that logic. **Do not print or hardcode the password** (it is a
  generated secret).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Config lint (offline) | `grep -nE '^(maxmemory|maxmemory-policy)' other/redis/redis.conf` | shows the 2 new lines |
| (server) service up | `systemctl is-active hiddify-redis` | `active` |
| (server) value applied | `redis-cli -a "$PASS" CONFIG GET maxmemory` (operator supplies PASS) | shows the cap |

## Scope

**In scope**:
- `other/redis/redis.conf` — add two directives.

**Out of scope**:
- `other/redis/install.sh` (the `requirepass` append logic).
- `cache.py` / `celery.py` (the result-backend removal is plan 005, not here).
- Never reproduce or log the Redis password.

## Git workflow

- Branch: `advisor/003-cap-redis-memory`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Add maxmemory + eviction policy to redis.conf

Append (or insert near the other memory/limits settings) in
`other/redis/redis.conf`:

```
# Hiddify low-RAM cap (512 MB VPS target). Redis here is a cache + Celery
# broker only; evicting least-recently-used keys is safe (cache recomputes).
maxmemory 48mb
maxmemory-policy allkeys-lru
```

Ensure these lines are NOT inside any conditional block and appear once. Do not
place them after the installer-appended `requirepass` line if the installer
appends by `>>` — putting them before that append is safest (either order works
for Redis, but keep the generated secret last as the installer expects).

**Verify**: `grep -nE '^(maxmemory|maxmemory-policy)' other/redis/redis.conf`
→ exactly the two lines shown.

### Step 2: (Server verification, if available)

Restart `hiddify-redis`, confirm it stays up and reports the cap. If no server,
note Step 2 not run.

**Verify (server)**: `systemctl is-active hiddify-redis` → `active`.

## Test plan

- Offline: the grep in Step 1 is the gate.
- No pytest applies (config file).
- Server: confirm no eviction storms in logs at steady state (spot check).

## Done criteria

- [ ] `grep -nE '^(maxmemory|maxmemory-policy)' other/redis/redis.conf` shows both lines
- [ ] `other/redis/redis.conf` still contains the original bind/dir/supervised lines (unchanged)
- [ ] No password value appears in the diff
- [ ] (server, if available) `hiddify-redis` active after restart
- [ ] `plans/README.md` row updated

## STOP conditions

- `redis.conf` drifted from the excerpt.
- On a live box Redis refuses to start with these directives (version quirk) —
  report the exact error.
- You find `maxmemory` is already set elsewhere (a drop-in / CONFIG SET) —
  report it rather than duplicating.

## Maintenance notes

- If plan 005 (drop Celery) lands, also set `task_ignore_result=True` there so
  Redis stops storing a result blob every 60 s — complementary, handled in 005.
- 48 MB is conservative; raise if cache hit-rate suffers. Reviewer: confirm the
  eviction policy is `allkeys-lru` (not `noeviction`, which would error on OOM).
