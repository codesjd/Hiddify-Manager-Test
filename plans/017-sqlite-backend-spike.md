# Plan 017: Add a SQLite DB backend (spike → implement) to drop MariaDB on small VPS

> **Executor instructions**: This is a SPIKE-then-implement plan. Do the
> investigation steps FIRST and STOP to report if a blocker is found before
> writing the install wiring. Verify on a real/staging server. Update
> `plans/README.md` when done (or BLOCKED with findings).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- install.sh hiddify-panel/run.sh hiddify-panel/src/settings.toml hiddify-panel/src/hiddifypanel/panel/init_db.py hiddify-panel/src/hiddifypanel/database.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2 (biggest structural 512MB win; but a real feature with real risk)
- **Effort**: M
- **Risk**: MED
- **Depends on**: 001 (offline tests), and interacts with 002 (if SQLite ships, 002 MariaDB tuning is moot)
- **Category**: direction / migration
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

MariaDB is the single largest steady-state RAM consumer (~150-250 MB). SQLite is
already a first-class in-tree backend — production `settings.toml` defaults to
it, CI runs the panel on it, and `init_db.py` has SQLite-file handling — but
`install.sh`/`run.sh` have no `sqlite` arm and always start a DB daemon. Adding
`DB_BACKEND=sqlite` drops MariaDB entirely (the biggest 512MB reclaim) and
likely removes the schema-reconciler enum-widen crash-loop trap (SQLite has no
native ENUM type). This is a real feature, not a config tweak: single-writer
concurrency and reconciler behavior on SQLite must be verified.

## Current state (evidence this is half-wired)

- `hiddify-panel/src/settings.toml:6,47,50` — `[default]`, `[testing]`, and
  `[production]` all default to `sqlite:///...`.
- `.github/workflows/main.yml:34` — CI runs the panel on
  `SQLALCHEMY_DATABASE_URI=sqlite:////opt/hiddify-manager/hiddify-panel/database.db`.
- `hiddify-panel/panel/init_db.py:1346-1364` — first-class SQLite file handling
  (`hiddifypanel.db`, rename `.old`, restore from backup JSON via `set_db_from_json`).
- `hiddify-panel/run.sh:13` — `if [ -z "${SQLALCHEMY_DATABASE_URI}" ]` — already
  RESPECTS a pre-set URI, so a sqlite URI works today if the env var is set; the
  gap is the convenience arm + not starting mysql.
- `install.sh:51-56` and `run.sh:14-25` — `DB_BACKEND` only branches
  `postgres`/`timescaledb` vs `else→mysql`; no `sqlite` arm.
- `PROJECT_SPEC.md` §2.4 — adding a `ConfigEnum` member widens a MySQL ENUM
  (`modify_type`) → reconciler refuses → crash-loop. SQLite renders enums as
  VARCHAR/CHECK, so this trap likely disappears (VERIFY — this is the key spike).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n install.sh hiddify-panel/run.sh` | exit 0 |
| (server) sqlite install | `DB_BACKEND=sqlite ./install.sh ...` | no mysql started; panel up on sqlite |
| (server) reconciler | add a throwaway `ConfigEnum` member, run init-db on sqlite | no `sys.exit(1)` crash-loop |

## Scope

**In scope**:
- `install.sh` — add a `sqlite` arm to the `DB_BACKEND` branch that (a) does NOT
  `install_run other/mysql`, (b) sets a sqlite `SQLALCHEMY_DATABASE_URI`.
- `hiddify-panel/run.sh` — add the sqlite arm building the file URI.
- `config.env.default` — document `DB_BACKEND` incl. `sqlite` (also covers DOC-01).

**Out of scope**:
- The ORM/models (already SQLite-compatible — do not change).
- Removing MySQL/Postgres backends (keep them for existing installs).
- Alembic batch-mode migrations UNLESS the spike proves they're needed (see Step 2).

## Git workflow

- Branch: `advisor/017-sqlite-backend`. Commit spike findings separately from
  wiring. No push/PR unless instructed.

## Steps

### Step 1 (SPIKE): Prove SQLite runs the full panel on a staging box

Set `SQLALCHEMY_DATABASE_URI=sqlite:////opt/hiddify-manager/hiddify-panel/hiddifypanel.db`
(as CI does), start the panel + background jobs, and exercise: create/edit users,
domains, settings; run `apply`; let usage accounting run under some traffic. This
uses the EXISTING code (run.sh already respects the URI). Confirm nothing MySQL-
specific breaks.

**STOP if**: any ORM/query error that only happens on SQLite appears — capture it;
that's a real blocker to report before proceeding.

### Step 2 (SPIKE): Verify the schema reconciler on SQLite

Add a throwaway `ConfigEnum` member, run `init-db` on the SQLite DB, and confirm
`reconcile_schema()` does NOT `sys.exit(1)` (the MySQL enum-widen trap). Then
test a realistic migration (an `add_column`) applies. If SQLite's Alembic
`compare_metadata()` produces a `modify_type`/`ALTER` that SQLite can't do
natively, note whether Alembic **batch mode** is required — if so, that becomes a
prerequisite sub-task (report it; do not silently ship without it).

**STOP if**: the reconciler crash-loops on SQLite too, OR a normal migration
fails without batch mode — report; the "trap disappears" benefit needs this.

### Step 3 (IMPLEMENT): Add the sqlite arm to install.sh + run.sh

Only after Steps 1-2 pass. In `run.sh`, add:
```bash
elif [ "$DB_BACKEND" == "sqlite" ]; then
    SQLALCHEMY_DATABASE_URI="sqlite:////opt/hiddify-manager/hiddify-panel/hiddifypanel.db"
```
In `install.sh`, add a `sqlite` arm that skips `install_run other/mysql` (and
postgres) entirely. Keep `mysql` as the default (unchanged behavior for existing
installs).

**Verify**: `bash -n install.sh hiddify-panel/run.sh` → exit 0.

### Step 4 (IMPLEMENT): Document DB_BACKEND (also fixes DOC-01)

Add to `config.env.default` a commented `DB_BACKEND=` line listing valid values
(`mysql` default, `postgres`, `timescaledb`, `sqlite`) with a one-line note that
sqlite is the low-RAM option.

### Step 5 (MANDATORY server verification)

Full `DB_BACKEND=sqlite ./install.sh` on staging: confirm MariaDB is NOT
installed/started, panel + background jobs run, users/domains/usage all work, and
`free -h` shows the MariaDB RSS gone.

## Test plan

- Offline: extend plan 001 / 020's harness to run the seed→all-configs→sub-gen
  path on a sqlite `:memory:` or file DB (CI already proves import works).
- Server Step 5 is the real gate.

## Done criteria

- [ ] Spike Steps 1-2 pass (panel runs on sqlite; reconciler doesn't crash-loop) OR blocker reported
- [ ] `DB_BACKEND=sqlite` arm in install.sh + run.sh; `bash -n` clean
- [ ] `config.env.default` documents DB_BACKEND
- [ ] (server) sqlite install runs full stack with no MariaDB; usage/domains/users work
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any drift in the excerpts.
- Spike reveals SQLite-only ORM breakage, OR the reconciler still crash-loops, OR
  migrations need batch-mode that isn't present — STOP, report, mark BLOCKED. Do
  NOT ship a half-working backend.
- Multi-node (`child_id` writes) + Celery/usage writers cause SQLite
  "database is locked" under load — report; may need WAL mode
  (`PRAGMA journal_mode=WAL`) as a sub-task.

## Maintenance notes

- If shipped, mark plan 002 (MariaDB tuning) REJECTED for sqlite installs (moot).
- WAL mode + a busy_timeout are the usual SQLite-under-concurrency mitigations;
  note them for the reviewer.
- Keep MySQL/Postgres fully working — sqlite is an added option, not a replacement.
