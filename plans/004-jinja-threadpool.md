# Plan 004: Switch the render engine from ProcessPool to ThreadPool

> **Executor instructions**: Follow step by step. Run verifications, honor STOP
> conditions, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- common/jinja.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW–MED
- **Depends on**: none (independent; 001's test baseline is nice-to-have not required)
- **Category**: perf
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

`common/jinja.py` renders every `.j2` with a 4-way `ProcessPoolExecutor`. On
Linux that forks 4 CPython interpreters; refcounting breaks copy-on-write
almost immediately, so each child becomes ~30–40 MB resident — a ~120–160 MB
transient spike during every config apply, exactly when panel + xray + singbox
+ MariaDB are already resident. On a 1-vCPU box the 4-way split buys no CPU
parallelism anyway, because the heavy work per template is `subprocess`/file
I/O (which releases the GIL), not Python CPU. Threads give the same I/O overlap
with none of the fork spike — removing a real OOM-risk window on a 512 MB box.

## Current state

```python
# common/jinja.py
9:  import subprocess
10: from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
...
20: def exec(command):                       # jinja `exec` filter -> shells out
22:     output = subprocess.check_output(command, shell=True, ...)
...
57: def render(template_path):
59:     env.globals['enumerate'] = enumerate     # env mutated per-call (same values each time)
60:     env.filters["b64encode"] = b64encode
...  # renders, json5 parse+redump, writes output file, chmod/chown
...
126:    with ProcessPoolExecutor(4) as executor:
127:        executor.map(render, templates_to_render)
```

Key facts that make threads safe here:
- `render()` writes a **distinct output path** per template (no write contention).
- The module-level `env` is reassigned the **same** filter/global values on
  every call (idempotent under concurrency).
- The dominant cost is `subprocess.check_output` (GIL released while waiting).
- `ThreadPoolExecutor` is already imported (line 10) and has the same `.map` API.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile common/jinja.py` | exit 0 |
| (server) apply | `DO_NOT_INSTALL=true ./install.sh apply_configs` | renders complete, services restart |
| (server) outputs valid | `for f in xray/configs/*.json singbox/configs/*.json; do jq empty "$f" || echo BAD $f; done` | no BAD lines |

## Scope

**In scope**:
- `common/jinja.py` — line 126 executor swap; optionally hoist the redundant
  `env.filters=...` assignment block out of `render()`.

**Out of scope**:
- The `exec` filter / `subprocess.check_output(shell=True)` itself (that's a
  separate security-review concern; do not change its behavior here).
- The json5 parse/write logic (that's plan 006).
- Do NOT change the pool size semantics beyond process→thread (keep 4 workers).

## Git workflow

- Branch: `advisor/004-jinja-threadpool`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Swap ProcessPoolExecutor(4) → ThreadPoolExecutor(4)

Change line 126 from `with ProcessPoolExecutor(4) as executor:` to
`with ThreadPoolExecutor(4) as executor:`. Leave the `executor.map(render,
templates_to_render)` call unchanged.

**Verify**: `python -m py_compile common/jinja.py` → exit 0;
`grep -n "ProcessPoolExecutor(" common/jinja.py` → no matches inside
`render_j2_templates` (import line may retain the name — that's fine, or remove
the now-unused import from line 10).

### Step 2: (Optional) hoist the redundant env setup

The `env.globals[...]`/`env.filters[...]` block (lines 59–66) is re-executed on
every `render()` call with identical values. Optionally move it to module scope
(right after `env = Environment(...)` on line 56) so it runs once. This is safe
and removes redundant work under threads. If unsure, SKIP — the executor swap
is the load-bearing change.

**Verify**: `python -m py_compile common/jinja.py` → exit 0.

### Step 3: (Server verification, if available)

Run a full `apply_configs` on a staging/real box; confirm every rendered
`.json` is valid and services restart. Per `PROJECT_SPEC.md` §7, render
pipeline changes must be exercised on a real server. If no server, note it and
rely on py_compile + the reasoning above; flag that Step 3 is pending.

**Verify (server)**: the `jq empty` loop above prints no BAD lines; `xray` and
`singbox` services are `active`.

## Test plan

- Offline: py_compile is the gate; there is no unit test for the render loop
  (it walks the real filesystem and shells out).
- Server: the `jq empty` validity loop over rendered outputs + service-active
  check is the real regression check.
- If any `.j2` template's `exec` filter relies on **process isolation** (e.g.
  mutating global state that must not be shared), threads would expose it —
  Step 3 on a real box is where that surfaces. STOP if outputs differ from a
  ProcessPool baseline.

## Done criteria

- [ ] `python -m py_compile common/jinja.py` exits 0
- [ ] `render_j2_templates` uses `ThreadPoolExecutor`, not `ProcessPoolExecutor`
- [ ] (server, if available) full apply produces all valid JSON + services active
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- `jinja.py` drifted from the excerpt.
- On a real apply, rendered outputs differ from the ProcessPool baseline, or a
  template's `exec` filter misbehaves under threads — report which template.
- Any deadlock/hang during apply (would indicate shared-state contention) —
  revert to ProcessPool and report.

## Maintenance notes

- Threads share the module-level `env` and Jinja's template cache — both are
  thread-safe for rendering, but if a future change makes `render()` mutate
  shared state with per-template *values*, revisit.
- Reviewer: confirm each rendered file still gets its `chmod`/`chown` from the
  template's stat (that logic is per-call and unaffected by the executor type).
- Complements plan 006 (skip-write-on-parse-failure) — apply both for a robust
  render pipeline.
