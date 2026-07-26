# Plan 005: Replace the Celery worker+beat with an in-process scheduler

> **Executor instructions**: This is the highest-risk plan in the 512MB bundle.
> Follow every step, run all verifications, and treat the STOP conditions as
> hard stops. This change MUST be exercised on a real/staging server before it
> is considered done (per `PROJECT_SPEC.md` §7). Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/celery.py hiddify-panel/src/hiddifypanel/panel/usage.py hiddify-panel/src/hiddifypanel/panel/cli.py hiddify-panel/hiddify-panel-background-tasks.service hiddify-panel/src/hiddifypanel/apps/celery_app.py`
> Any change → compare against "Current state" before proceeding; mismatch → STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: plan 001 (need a way to verify nothing broke) — strongly recommended first
- **Category**: perf
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

`hiddify-panel-background-tasks.service` runs a full second CPython interpreter
(Celery worker + beat, `--concurrency 1 --pool=solo`) that carries the
celery+kombu+redis+SQLAlchemy+gRPC import graph — typically ~80–150 MB RSS
resident 24/7 — purely to fire **two** periodic jobs: `update_local_usage`
(every 60 s) and `backup_task` (every 6 h). Celery's queue/retry/broker
semantics are not load-bearing: no code enqueues tasks (every `.delay()` /
`.apply_async()` is commented out), overlap is already prevented by a Redis
lock, and the per-minute result blob is never read. Moving these two jobs into
the already-running bjoern panel process (via an in-process scheduler) deletes
an entire persistent service — the second-biggest steady-state RAM reclaim
available toward the 512 MB goal.

## Current state

- `hiddify-panel/hiddify-panel-background-tasks.service:12` runs:
  ```
  ExecStart=/opt/hiddify-manager/.venv313/bin/python -m celery -A hiddifypanel.apps.celery_app:celery_app worker --beat --loglevel debug --concurrency 1 --pool=solo
  ```
  Its comments explain `KillMode=process` exists because tasks here can shell
  out to `install.sh` and must survive a restart of the unit.
- `hiddify-panel/src/hiddifypanel/celery.py` defines the schedule twice — the
  Flask variant `init_app(app)` (lines 9–50) and the deployed no-Flask variant
  `init_app_no_flask()` (lines 54–110). Both register exactly:
  ```python
  celery_app.add_periodic_task(60.0, usage.update_local_usage.s(), name='update usage')   # :27 / :85
  celery_app.add_periodic_task(crontab(hour="*/6", minute="0"), backup_task.s(), ...)      # :43 / :101
  ```
  All `.delay()` / `beat_schedule` lines are commented out; `task_ignore_result=True`
  is commented out (so results ARE stored every 60 s and never read).
- The two jobs:
  - `hiddify-panel/src/hiddifypanel/panel/usage.py` `update_local_usage()`
    (~line 37) — reads driver counters (reset-on-read) and writes usage; can
    call `hiddify.quick_apply_users()` which shells out. Needs an app context.
  - `hiddify-panel/src/hiddifypanel/panel/cli.py` `backup_task()` (line 38,
    `@shared_task(ignore_result=False)`) — JSON backup, auto-pushes to Telegram.
- The panel web process entry: `hiddify-panel/app.py` runs
  `bjoern.run(wsgi_app=hiddifypanel.create_app(), ...)`. The app factory is in
  `hiddify-panel/src/hiddifypanel/base.py`/`base_setup.py`.
- Overlap guard for `update_local_usage` is a Redis `nx` lock inside `usage.py`
  (so a missed/slow run cannot double-run).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/{celery.py,base_setup.py,apps/scheduler.py}` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass (plan 001 suite still green) |
| (server) panel up | `systemctl is-active hiddify-panel` | `active` |
| (server) old unit gone | `systemctl is-enabled hiddify-panel-background-tasks 2>&1` | `disabled`/not-found |
| (server) usage advancing | check a user's usage increases over ~2 min under traffic | value grows |

## Scope

**In scope**:
- Create `hiddify-panel/src/hiddifypanel/apps/scheduler.py` (new in-process scheduler).
- Wire it into the web app factory (`base_setup.py` or wherever `create_app`
  finalizes) so it starts ONLY in the web process, ONCE.
- `pyproject.toml` — add `apscheduler` to dependencies IF you use it (preferred).
- `hiddify-panel/hiddify-panel-background-tasks.service` — stop enabling it;
  and the installer line that enables it (`hiddify-panel/run.sh` /
  `hiddify-panel/install.sh` — grep for `background-tasks`).
- `hiddify-panel/src/hiddifypanel/celery.py` — leave the task *definitions*
  importable (they're plain functions/`@shared_task`); only stop relying on the
  Celery process to schedule them.

**Out of scope**:
- The bodies of `update_local_usage` / `backup_task` — reuse them as-is.
- The reset-on-read usage semantics (that's a separate finding, CORR-21).
- Removing Celery from `pyproject.toml` entirely — other code may import
  `@shared_task`; leave the dependency, just stop running the worker.
- The `commander`/`install.sh` detach mechanism.

## Git workflow

- Branch: `advisor/005-drop-celery-process`. Commit per logical step. No push/PR
  unless instructed.

## Steps

### Step 1: Add an in-process scheduler module

Create `apps/scheduler.py` with an APScheduler `BackgroundScheduler` (preferred;
add `apscheduler` to `pyproject.toml`) that runs the two jobs inside an app
context. Target shape:

```python
from apscheduler.schedulers.background import BackgroundScheduler
_scheduler = None

def start(app):
    global _scheduler
    if _scheduler is not None:      # idempotent: never start twice
        return
    def _usage():
        with app.app_context():
            from hiddifypanel.panel import usage
            usage.update_local_usage()
    def _backup():
        with app.app_context():
            from hiddifypanel.panel.cli import backup_task
            backup_task()
    sch = BackgroundScheduler(timezone="UTC")
    sch.add_job(_usage, "interval", seconds=60, max_instances=1, coalesce=True, id="update_usage")
    sch.add_job(_backup, "cron", hour="*/6", minute=0, max_instances=1, id="backup_task")
    sch.start()
    _scheduler = sch
```

If adding a dependency is undesirable, a `threading.Timer`/loop fallback is
acceptable, but APScheduler gives you `max_instances=1` + cron for free. The
existing Redis `nx` lock in `update_local_usage` remains the real overlap guard.

**Verify**: `python -m py_compile hiddify-panel/src/hiddifypanel/apps/scheduler.py` → exit 0.

### Step 2: Start the scheduler from the web process only, exactly once

In the web app factory path (the one `hiddify-panel/app.py` →
`create_app()` uses — read `base.py`/`base_setup.py` to find where the app is
finalized), call `scheduler.start(app)`. Guard so it runs only in the bjoern
web process, not in CLI invocations (`hiddify-panel-cli ...`) or during
`init-db`. A reliable guard: start it lazily from `app.py` right before
`bjoern.run(...)`, NOT inside `create_app` (which the CLI also calls). Prefer
editing `hiddify-panel/app.py`:

```python
if __name__ == "__main__":
    import bjoern, hiddifypanel
    app = hiddifypanel.create_app()
    from hiddifypanel.apps.scheduler import start as start_scheduler
    start_scheduler(app)
    bjoern.run(wsgi_app=app, host="127.0.0.1", port=9000)
```

This is the cleanest single-process, single-start location.

**Verify**: `python -m py_compile hiddify-panel/app.py` → exit 0. Confirm no CLI
entrypoint imports `app.py`'s `__main__` block (it won't — guarded by `__main__`).

### Step 3: Stop enabling the background-tasks service

Find where the unit is enabled/started (grep `background-tasks` across
`hiddify-panel/*.sh`, `install.sh`, `common/`). Remove/comment the enable+start
so a fresh install no longer runs the Celery process. On existing servers the
operator will `systemctl disable --now hiddify-panel-background-tasks` (document
this in your report). Leave the `.service` file in the tree (or delete it) —
prefer leaving it but not enabling it, to ease rollback.

**Verify**: `grep -rn "background-tasks" hiddify-panel/ install.sh common/` shows
no active (uncommented) `systemctl enable/start` of that unit.

### Step 4: (MANDATORY server verification)

On a staging/real box: deploy, restart `hiddify-panel`, disable the old unit,
then over ~2–3 minutes under some traffic confirm: (a) panel stays up, (b) a
user's usage counter advances (proves `update_local_usage` runs in-process),
(c) an `apply`/user-change still works and its detached `install.sh` survives a
panel restart (the reason `KillMode=process` existed). If backup timing matters,
trigger `backup_task()` manually via CLI and confirm it still produces a backup.

**Verify (server)**: usage advances; `systemctl is-active hiddify-panel` →
`active`; an apply completes; `hiddify-panel-background-tasks` is disabled and
RAM shows one fewer python process (`ps aux | grep celery` → none).

## Test plan

- Offline: plan 001's `pytest tests/` must stay green; add a small test that
  `apps.scheduler.start(app)` is idempotent (second call is a no-op) using a
  fake app object. Do NOT test the job bodies offline (they need DB/drivers).
- Server (Step 4) is the real regression gate for usage accounting and apply
  survival — non-negotiable before marking DONE.

## Done criteria

- [ ] `python -m py_compile` clean on scheduler.py, app.py
- [ ] `pytest tests/` green (001 suite) + idempotency test passes
- [ ] No active `systemctl enable/start hiddify-panel-background-tasks` remains
- [ ] (server) usage advances in-process; apply still survives panel restart; celery process gone
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any "Current state" excerpt drifted from live code.
- On the server, usage stops advancing after the switch, OR an apply no longer
  survives a panel self-restart (the KillMode concern) — revert and report; do
  NOT ship a change that breaks usage accounting or apply.
- You cannot find a single, guaranteed-once place to start the scheduler in the
  web process (e.g. bjoern forks workers) — STOP and report the process model;
  a double-start would double-run jobs.
- `update_local_usage` or `backup_task` turn out to be enqueued via `.delay()`
  somewhere after all (re-grep to be sure) — then Celery IS used as a queue and
  this plan's premise is wrong; report it.

## Maintenance notes

- Keep the Redis `nx` lock in `update_local_usage` — it's now the sole overlap
  guard. If plan 003 (Redis cap) is in, also set `task_ignore_result=True` isn't
  needed once Celery isn't running, but if any residual Celery use remains,
  uncomment it in `celery.py` to stop result writes.
- Reviewer: scrutinize the "start exactly once, web-process only" guard hardest
  — a scheduler started in a CLI/init-db invocation would fire jobs from the
  wrong process.
- Rollback is: re-enable the `.service`, remove the `scheduler.start()` call.
