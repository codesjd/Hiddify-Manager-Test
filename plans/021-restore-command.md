# Plan 021: Operator-facing `restore` command (make backups usable for recovery)

> **Executor instructions**: Build plan. Follow steps, run verifications, honor
> STOP conditions, update `plans/README.md`. This is DESTRUCTIVE (overwrites the
> DB) — the confirmation guard is mandatory.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/panel/cli.py hiddify-panel/src/hiddifypanel/panel/init_db.py hiddify-panel/src/hiddifypanel/panel/hiddify.py`
> Mismatch → compare before proceeding.

## Status

- **Priority**: P3
- **Effort**: S (CLI wrapper over an existing primitive)
- **Risk**: MED (destructive restore)
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

The panel produces JSON backups (`backup_task`, auto-pushed to Telegram) and can
RESTORE one — but only implicitly, as a side-effect of a SQLite version upgrade
in `init_db.py`. There is no operator-facing "restore from backup" command or
REST route. For a fragile remote VPS that needs rebuilding, the existing backups
are effectively write-only. Exposing the restore primitive that already exists
turns them into real disaster-recovery.

## Current state

- `panel/cli.py:33-54` — `backup` / `backup_task` produce a JSON export.
- `panel/init_db.py:1353-1364` — during a SQLite upgrade, restores by calling
  `hiddify.set_db_from_json(json_data, set_users=True, set_domains=True,
  remove_domains=True, remove_users=True, set_settings=True, override_unique_id=True,
  set_admins=True, override_root_admin=True, override_child_unique_id=0,
  replace_owner_admin=True)`.
- `hiddify.set_db_from_json(...)` (in `panel/hiddify.py`) is the restore primitive
  — it already exists and is already called at init_db.py:1361.
- No `restore` CLI/REST entry (grep `backup|restore` under `restapi/**` = 0 hits).
- Importer precedent: `panel/cli.py:209` `xui_importer` is a CLI command wrapping
  `hutils/importer/xui.py` — follow its registration style.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/panel/cli.py` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |
| (server) restore | `hiddify-panel-cli restore <backup.json> --yes` | DB restored; panel reflects it |

## Scope

**In scope**:
- `panel/cli.py` — add a `restore` command wrapping `hiddify.set_db_from_json`,
  reading a backup JSON path, with a MANDATORY confirmation flag.
- Optionally `menu.sh` — expose it under an advanced/backup menu.

**Out of scope**:
- Changing `set_db_from_json` itself.
- The backup producer.
- A REST restore route (larger; note as follow-up).
- New import sources (Marzban/3x-ui) — separate, larger effort.

## Git workflow

- Branch: `advisor/021-restore-command`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Read set_db_from_json's real signature and the destructive flags

Open `panel/hiddify.py` `set_db_from_json` and confirm the exact parameter names
(the init_db call passes `remove_users`/`remove_domains`/`override_root_admin`,
etc.). Understand which flags are destructive. The `init_db.py:1361` call is the
reference invocation.

### Step 2: Add the `restore` CLI command with a confirmation guard

In `panel/cli.py`, register a `restore` command (mirroring `xui_importer`'s
registration at :209) that:
- takes a `<backup.json>` path and reads/parses it;
- REQUIRES an explicit `--yes`/`--force` flag (or interactive "type CONFIRM")
  before proceeding, because it overwrites users/domains/settings;
- calls `hiddify.set_db_from_json(...)` with the same flags init_db uses for a
  full restore (or expose granular flags: `--users/--domains/--settings`);
- prints a clear before/after summary (counts).

**Verify**: `python -m py_compile .../cli.py` → exit 0;
`hiddify-panel-cli restore --help` lists the command (on a box with the CLI).

### Step 3: (Optional) menu entry

Add a `restore` entry to `menu.sh` under an advanced/backup section, requiring
the same confirmation.

### Step 4: (Server verification)

On a staging box: take a backup, change some data, `restore` it with `--yes`, and
confirm the data is restored. Confirm that WITHOUT `--yes` it refuses.

## Test plan

- Offline: add a test that the command REFUSES without the confirmation flag
  (parse-level / dry-run), and that it correctly reads a well-formed backup JSON
  and calls `set_db_from_json` with the expected flags (mock the primitive).
- Server Step 4 is the real restore gate.

## Done criteria

- [ ] `py_compile` clean; `restore` registered in the CLI
- [ ] Refuses to run without an explicit confirmation flag
- [ ] Delegates to the existing `set_db_from_json` (no reimplementation)
- [ ] (server) round-trip restore works; unconfirmed run is a no-op
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any excerpt drifted, or `set_db_from_json`'s signature differs from init_db's call.
- The primitive has side effects beyond the DB (e.g. triggers an apply mid-restore)
  that make a partial failure dangerous — report before shipping; may need to run
  with the panel stopped (like schema ALTERs, §2.4/§3.6).

## Maintenance notes

- Keep the confirmation guard — this overwrites live data.
- Follow-up (not this plan): a REST restore route + additional import sources.
- Reviewer: verify the destructive flags match intent and the guard cannot be bypassed.
