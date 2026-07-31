# Plan 002: Cap MariaDB memory with a tuning drop-in

> **Executor instructions**: Follow step by step. Run every verification
> command and confirm the expected result. Honor STOP conditions. Update this
> plan's row in `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- other/mysql/install.sh`
> If it changed, compare the "Current state" excerpt to live code before proceeding; mismatch → STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `0c87bc75`, 2026-07-26
- **Note**: MUTUALLY EXCLUSIVE with plan 017 (SQLite backend). If you deploy
  017 and drop MariaDB entirely, this plan is moot. Decide the DB direction
  first. This plan is the "keep MariaDB, make it fit 512MB" path.

## Why this matters

The operator's goal is running the whole stack on a 512 MB VPS. MariaDB is the
single largest *tunable* steady-state RAM consumer, and the installer leaves it
at package defaults — no InnoDB buffer-pool cap, no `performance_schema`
control, no connection cap. Stock MariaDB idles ~150–250 MB RSS for a dataset
that is a few config tables + users. A one-file tuning drop-in reclaims the
largest chunk of the RAM budget with no feature loss.

## Current state

- `other/mysql/install.sh` installs `mariadb-server`, generates a password,
  sets `bind-address = 127.0.0.1`, and restarts — but writes **no** memory
  tuning. Relevant excerpt:
  ```bash
  # other/mysql/install.sh
  install_package mariadb-server
  ...
  MARIADB_CONF="/etc/mysql/mariadb.conf.d/50-server.cnf"
  ... # only bind-address is touched; no buffer-pool / perf_schema / max_connections
  ```
- Debian/Ubuntu MariaDB reads `*.cnf` drop-ins from
  `/etc/mysql/mariadb.conf.d/` in filename order; a `60-*.cnf` loads after the
  stock `50-server.cnf`, so its `[mysqld]` values win.
- The DB is created with charset `utf8mb4` (`other/mysql/install.sh`); do not
  change collation/charset.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n other/mysql/install.sh` | exit 0 |
| (server-only) verify applied | `mysql -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size'"` | shows the capped value |
| (server-only) service up | `systemctl is-active mariadb` | `active` |

## Scope

**In scope**:
- `other/mysql/install.sh` — add code that writes the tuning drop-in.

**Out of scope**:
- `50-server.cnf` (stock file — never edit; add a `60-*` drop-in instead).
- `hiddify-panel/run.sh` / the `SQLALCHEMY_DATABASE_URI` construction.
- Postgres installer.
- Any charset/collation change.

## Git workflow

- Branch: `advisor/002-cap-mariadb-memory`
- One commit. Do not push/PR unless instructed.

## Steps

### Step 1: Write a tuning drop-in from the installer

In `other/mysql/install.sh`, after MariaDB is installed and before the final
`systemctl restart mariadb`, write `/etc/mysql/mariadb.conf.d/60-hiddify.cnf`:

```bash
cat >/etc/mysql/mariadb.conf.d/60-hiddify.cnf <<'EOF'
# Hiddify low-RAM tuning (512 MB VPS target). Values chosen for a tiny
# working set (config tables + users). Loaded after 50-server.cnf, so these win.
[mysqld]
innodb_buffer_pool_size = 64M
performance_schema = OFF
max_connections = 40
sort_buffer_size = 1M
join_buffer_size = 1M
tmp_table_size = 8M
max_heap_table_size = 8M
EOF
```

Place it so it runs on every install/reinstall (idempotent — the file is
overwritten each time, which is fine). Keep the existing bind-address logic.

**Verify**: `bash -n other/mysql/install.sh` → exit 0; `grep -n "60-hiddify.cnf" other/mysql/install.sh` → 1+ matches.

### Step 2: (Server verification — only if you have a live/staging box)

Run the mysql installer path (or `apply`/reinstall), then confirm MariaDB
still starts and honors the cap. If you have no server, note in your report
that Step 2 was not run (per `PROJECT_SPEC.md` §7, DB/service changes are
verified on the real server).

**Verify (server)**: `systemctl is-active mariadb` → `active`;
`mysql -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size'"` → `67108864` (64M).

## Test plan

- No offline unit test applies (this is a config-file write in shell).
- Verification is `bash -n` (offline) + the server checks in Step 2.
- If a lightweight assertion is wanted, add a shell check that the drop-in is
  syntactically a valid `[mysqld]` block — optional, low value.

## Done criteria

- [ ] `bash -n other/mysql/install.sh` exits 0
- [ ] `grep -n "innodb_buffer_pool_size" other/mysql/install.sh` finds the drop-in write
- [ ] (server, if available) MariaDB `active` after install with buffer pool = 64M
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- `other/mysql/install.sh` drifted from the excerpt (changed since 0c87bc75).
- On a live box, MariaDB fails to start with the drop-in (e.g. a directive
  unsupported by that MariaDB version) — report which directive; do not
  guess-remove more than the offending line.
- You discover the deployment does NOT use `/etc/mysql/mariadb.conf.d/`
  (non-Debian MariaDB layout) — report the actual include path.

## Maintenance notes

- If user count grows large, `innodb_buffer_pool_size` may need raising; it's a
  single line in the drop-in.
- Reviewer: confirm the drop-in filename sorts after `50-server.cnf` and that
  no charset/collation was altered.
- If plan 017 (SQLite) is adopted instead, mark this plan REJECTED in the index.
