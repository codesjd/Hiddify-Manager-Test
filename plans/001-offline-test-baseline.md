# Plan 001: Establish an offline pytest baseline (and fix the broken dev-deps install)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/Makefile hiddify-panel/src/pyproject.toml common/check_migrations.py hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py hiddify-panel/src/hiddifypanel/hutils/network/net.py`
> If any of these changed since this plan was written, compare the "Current
> state" excerpts against live code before proceeding; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: LOW
- **Depends on**: none (this is the foundation other plans rely on)
- **Category**: tests + dx
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

The repo has **zero runnable tests**. The `Makefile` `test`/`lint`/`fmt`
targets are stubbed to `@echo skip`, CI triggers are commented out, and the
documented dev-deps install requests a non-existent extra so the tools never
install. Every risky change in the other plans (dropping Celery, the SQLite
backend, config-generation fixes) currently can only be verified on a live
server — which the sandbox cannot run. This plan creates a one-command
offline safety net (`pytest`) for pure-logic modules, starting with the ones
that need no app context, so subsequent plans have a real verification gate.

## Current state

- `hiddify-panel/src/Makefile:35` and `:86` install `.[test]`, but
  `pyproject.toml` defines the extra as **`dev`**, not `test` — so pip warns
  and installs no dev tools (pytest/mypy/flake8 silently absent):
  ```
  Makefile:35:  $(ENV_PREFIX)pip install -e cython .[test]
  Makefile:86:  @./.venv/bin/pip install -e .[test]
  ```
  ```
  pyproject.toml:75  [project.optional-dependencies]
  pyproject.toml:76  dev = [
  ```
- `common/check_migrations.py` is **pure stdlib** (`import ast`, `re`, `sys`
  only) with a clean contract — the frictionless first test target:
  ```python
  # common/check_migrations.py
  def check_file(path: str) -> bool:   # line 29 — returns True if OK, False if dup/stale
  def main(argv: list[str]) -> int:    # line 86 — CLI exit code
  ```
- Two more pure-logic targets (need the dev deps installed because their
  modules do heavy top-level imports — flask/models/dns/psutil):
  - `hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py:155` —
    `ports_to_ranges(csv)`: pure `str -> list[str]`, validates 1–65535,
    raises `ValueError`. Note a single port emits `"N-N"` (not `"N"`) — lock
    that behavior.
  - `hiddify-panel/src/hiddifypanel/hutils/network/net.py:467`
    `add_number_to_ipv4` / `:476` `add_number_to_ipv6` — pure per-user WG IP
    arithmetic.
- Repo verification gates today (from `PROJECT_SPEC.md` §7): `python -m
  py_compile`, Jinja `Environment().parse()`, `bash -n`,
  `python3 common/check_migrations.py <init_db.py>`. No test runner exists.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| py_compile | `python -m py_compile common/check_migrations.py` | exit 0 |
| Install dev deps | `cd hiddify-panel/src && uv pip install -e '.[dev]'` (or `pip install -e '.[dev]'`) | exit 0, pytest installed |
| Run tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | all pass |
| Migration lint | `python3 common/check_migrations.py hiddify-panel/src/hiddifypanel/panel/init_db.py` | exit 0 |

## Scope

**In scope** (the only files you may modify/create):
- `hiddify-panel/src/Makefile` (fix the extra name only)
- `hiddify-panel/src/tests/__init__.py` (create)
- `hiddify-panel/src/tests/test_check_migrations.py` (create)
- `hiddify-panel/src/tests/test_ports_and_ip.py` (create)
- `hiddify-panel/src/conftest.py` (create only if pytest can't import the package without it)

**Out of scope** (do NOT touch):
- The `Makefile` `test`/`lint`/`fmt` stub bodies — re-enabling `make lint`
  (mypy/flake8 on 169 dynamic files) is a separate plan; only fix the extra name.
- `check_migrations.py`, `shared.py`, `net.py` source — you are testing them,
  not changing them. If a test reveals a bug, STOP and report it (that's a
  separate finding), do not "fix" the source here.
- CI workflow files.

## Git workflow

- Branch: `advisor/001-offline-test-baseline`
- Commit style matches repo (`git log` shows plain imperative subjects, e.g.
  "Fix ...", "Add ..."). One commit is fine.
- Do NOT push or open a PR unless the operator instructs it. This is the
  feature branch `claude/saving-mechanism-bug-yvzifn`; per `PROJECT_SPEC.md`
  §1.3 changes are later cherry-picked to `optimize` — leave that to the operator.

## Steps

### Step 1: Fix the dev-deps extra name

In `hiddify-panel/src/Makefile`, change both `.[test]` occurrences (lines 35,
86) to `.[dev]`. Do not change anything else on those lines.

**Verify**: `grep -n "\.\[test\]" hiddify-panel/src/Makefile` → no matches;
`grep -n "\.\[dev\]" hiddify-panel/src/Makefile` → 2 matches.

### Step 2: Create the tests package and the zero-dependency first test

Create `hiddify-panel/src/tests/__init__.py` (empty) and
`hiddify-panel/src/tests/test_check_migrations.py`. Import the module by file
path so it works without installing the package:

```python
import importlib.util, pathlib, tempfile, os

_ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root
_spec = importlib.util.spec_from_file_location(
    "check_migrations", _ROOT / "common" / "check_migrations.py")
cm = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(cm)

def _write(tmp_path, body: str) -> str:
    p = tmp_path / "init_db.py"; p.write_text(body); return str(p)

def test_clean_file_passes(tmp_path):
    body = "MAX_DB_VERSION = 2\ndef _v1():\n    pass\ndef _v2():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is True

def test_duplicate_vnnn_fails(tmp_path):
    body = "MAX_DB_VERSION = 2\ndef _v1():\n    pass\ndef _v1():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is False

def test_max_db_version_lower_than_highest_vnnn_fails(tmp_path):
    body = "MAX_DB_VERSION = 1\ndef _v1():\n    pass\ndef _v2():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is False
```

If the real `check_file` signature/return differs from the "Current state"
excerpt, STOP (drift). Adjust the fixture body only if `check_migrations.py`
parses a different `MAX_DB_VERSION`/`_vNNN` shape than shown — read the source
to confirm the exact names before adjusting.

**Verify**: `cd hiddify-panel/src && python -m pytest tests/test_check_migrations.py -v`
→ 3 passed. (This needs only stdlib + pytest; if pytest isn't installed, run
Step 1's install command first.)

### Step 3: Add pure-logic tests for port/IP helpers

Create `hiddify-panel/src/tests/test_ports_and_ip.py` testing
`hutils.proxy.shared.ports_to_ranges` and
`hutils.network.net.add_number_to_ipv4/ipv6`. Cover: a contiguous run, a
gapped list, a single port (assert the `"N-N"` form), empty input,
out-of-range raises `ValueError`, and the IP-arithmetic carry cases. Import
normally (`from hiddifypanel.hutils.proxy.shared import ports_to_ranges`);
this requires `.[dev]` installed (Step 1).

If importing `shared`/`net` fails due to module-level side effects (DB/app),
add a minimal `hiddify-panel/src/conftest.py` that sets any required env vars
(e.g. `HIDDIFY_CFG_PATH`, `SQLALCHEMY_DATABASE_URI=sqlite:///:memory:`) — mirror
what `.github/workflows/main.yml:34` sets. If it still can't import without a
full app, STOP and report: that import coupling is itself a finding, and the
`check_migrations` test (Step 2) already establishes the baseline.

**Verify**: `cd hiddify-panel/src && python -m pytest tests/ -v` → all pass
(≥3 from Step 2 plus the new port/IP tests).

## Test plan

- New: `tests/test_check_migrations.py` (dup detection, stale MAX_DB_VERSION,
  clean file) — the zero-dependency anchor.
- New: `tests/test_ports_and_ip.py` (range compaction incl. single-port
  `"N-N"`, out-of-range raise, IPv4/IPv6 carry).
- Pattern to follow: there is no existing test to mirror — these ARE the
  pattern for later plans. Keep them import-light and assertion-specific.

## Done criteria

- [ ] `grep -rn "\.\[test\]" hiddify-panel/src/Makefile` returns nothing
- [ ] `cd hiddify-panel/src && python -m pytest tests/ -v` exits 0 with ≥3 tests
- [ ] `python3 common/check_migrations.py hiddify-panel/src/hiddifypanel/panel/init_db.py` still exits 0
- [ ] No files outside the in-scope list modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- The "Current state" excerpts don't match live code (drift since 0c87bc75).
- `check_migrations.py`'s `check_file` returns something other than a bool, or
  its dup/stale detection doesn't behave as the tests assume.
- A test you wrote fails because the *source* is buggy (not your test) — report
  it as a new finding; do not change the source in this plan.
- `shared`/`net` cannot be imported even with a minimal conftest — deliver
  Steps 1–2 and report the import-coupling blocker.

## Maintenance notes

- This suite is intentionally offline/pure-logic only. Live-traffic and
  config-apply verification stays on the real server per `PROJECT_SPEC.md` §7.
- Later plans (002+) add their own tests to `tests/`; keep this directory the
  home for offline unit tests.
- A reviewer should confirm no network/DB/app-context leaked into these tests
  (they must run in a bare checkout with only `.[dev]`).
- Deferred: re-enabling `make lint`/`mypy` and CI triggers — separate DX plan.
