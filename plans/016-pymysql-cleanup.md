# Plan 016: Remove the dead `pymysql` dependency (optionally drop the MySQL C toolchain)

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. The optional driver switch (Part B) must
> be verified on a real server.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/pyproject.toml hiddify-panel/run.sh docker-init.sh common/install.sh common/hiddify_installer.sh hiddify-panel/install.sh`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (Part A delete); MED (Part B driver switch)
- **Depends on**: none
- **Category**: dependencies
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

`pymysql` is declared but never imported — dead weight. Separately, the live
MySQL driver `mysqlclient` is a **C extension** requiring `default-libmysqlclient-dev`
+ `build-essential` at install; `pymysql` is pure-Python and already declared.
Part A removes the dead dep. Part B (optional) standardizes on `pymysql`, letting
the build drop the C toolchain from the MySQL path — a real footprint win for a
512 MB VPS. Do Part A always; do Part B only with server verification.

## Current state

- `pyproject.toml:34` `pymysql==1.1.2`, `:63` `mysqlclient==2.2.8`, plus
  `psycopg[binary]` for Postgres (legit).
- Zero `import pymysql` anywhere (verified).
- Live MySQL connection string is `mysql+mysqldb://` (= mysqlclient):
  `hiddify-panel/run.sh:24`, `docker-init.sh:30`. Postgres uses `postgresql+psycopg://`.
- C toolchain pulled for mysqlclient: `common/install.sh:4`
  (`default-libmysqlclient-dev build-essential`), `common/hiddify_installer.sh:61`,
  `hiddify-panel/install.sh:3`.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Deps resolve | `cd hiddify-panel/src && uv pip install -e '.[dev]'` (or pip) | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |
| (server, Part B) DB connects | panel starts, reads/writes users | works on MySQL install |

## Scope

**Part A (in scope)**: `pyproject.toml` — remove the `pymysql` line.
**Part B (optional, in scope only if chosen)**: `run.sh:24`, `docker-init.sh:30`
(`mysql+mysqldb` → `mysql+pymysql`), re-add `pymysql`, remove `mysqlclient` +
the `default-libmysqlclient-dev`/`build-essential`(mysql-only) from the 3
install scripts.

**Out of scope**: `psycopg`/Postgres path; the SQLite plan (017); any behavior
change beyond the driver.

## Git workflow

- Branch: `advisor/016-pymysql-cleanup`. Part A one commit; Part B a second commit
  if done. No push/PR unless instructed.

## Steps

### Step 1 (Part A): Delete the dead dependency

Remove `"pymysql==1.1.2",` from `pyproject.toml:34`. Confirm nothing imports it.

**Verify**: `grep -rn "pymysql" hiddify-panel/src/hiddifypanel/` → no matches;
`cd hiddify-panel/src && uv pip install -e '.[dev]'` → exit 0; `pytest tests/` green.

### Step 2 (Part B — OPTIONAL, only with a server to verify): switch to pymysql

If you want the build-toolchain reduction: change `mysql+mysqldb://` →
`mysql+pymysql://` in `run.sh:24` and `docker-init.sh:30`; re-add
`pymysql==1.1.2` to pyproject and remove `mysqlclient==2.2.8`; remove
`default-libmysqlclient-dev` (and `build-essential` if not needed elsewhere —
check! it may be needed by other C builds like simple-obfs) from
`common/install.sh:4`, `common/hiddify_installer.sh:61`, `hiddify-panel/install.sh:3`.

**Verify (server, MySQL install)**: panel starts, users read/write correctly,
usage accounting works. `bash -n` on the 3 install scripts.

## Test plan

- Part A: dependency resolves + existing tests green.
- Part B: server smoke — the panel must connect to MySQL via pymysql and perform
  a read + write. No offline test covers the driver.

## Done criteria

- [ ] Part A: `pymysql` removed; deps resolve; tests green
- [ ] (If Part B) connection strings use `pymysql`; `mysqlclient` + mysql-only
      build packages removed; server verified on a MySQL install
- [ ] `build-essential` NOT removed if still needed by other C builds (verified)
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any excerpt drifted, or a `pymysql` import turns up (then it's not dead — report).
- Part B: `build-essential` is required by another subsystem (simple-obfs,
  amneziawg) — do NOT remove it; only remove the mysql-specific `-dev` package.
- Part B: pymysql shows connection/perf problems on the target MySQL — revert to
  mysqlclient and report (pymysql is fine for a single-VPS panel but verify).

## Maintenance notes

- If plan 017 (SQLite) is adopted as the default backend, the whole MySQL driver
  question becomes moot for those installs — but keep MySQL working for existing
  deployments.
- Reviewer: confirm `psycopg` (Postgres) untouched.
