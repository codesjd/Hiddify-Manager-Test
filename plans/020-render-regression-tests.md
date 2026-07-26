# Plan 020: Offline render/subscription regression tests (golden files)

> **Executor instructions**: Build plan. Follow steps, run verifications, honor
> STOP conditions, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- .github/workflows/main.yml hiddify-panel/src/hiddifypanel/hutils/proxy/shared.py`
> Mismatch → compare before proceeding.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (pure test addition)
- **Depends on**: 001 (test harness), pairs with 017 (CI already runs on SQLite)
- **Category**: direction / tests
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

The repo's rule "test network changes on the real server" is correct for live
traffic, but the *render/subscription* layer is CI-testable WITHOUT traffic — and
a recurring class of bugs (missing proxy rows, wrong subscription contents,
un-rendered templates) keeps shipping: `907d8ffa` (add_column never called for 7
Domain columns), AnyTLS rows missing, ShadowTLS wrongly in the combined sub. A
golden-file test — seed a known DB on SQLite, generate configs/subscriptions,
assert against checked-in expected output — catches these in CI for free and
shrinks the "must test on the Turkey box" loop.

## Current state

- CI already boots the panel on SQLite (`.github/workflows/main.yml:34`); the
  substrate exists.
- No assertions on subscription/config-render OUTPUT exist (plan 001 adds only
  pure-helper unit tests).
- Config/sub generation lives in `hutils/proxy/{shared,xrayjson,singbox,xray,clash}.py`,
  driven by `make_proxy()` (`shared.py:578`) from seeded `Proxy`/`Domain`/config rows.
- CLI entry `hiddify-panel-cli all-configs` produces the `current.json` payload.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Install | `cd hiddify-panel/src && uv pip install -e '.[dev]'` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |

## Scope

**In scope**:
- `hiddify-panel/src/tests/test_render_golden.py` (create) + a fixtures dir with
  a seed and expected-output golden files.
- Optionally a `conftest.py` fixture that builds an in-memory/file SQLite DB with
  a representative proxy matrix.
- `.github/workflows/main.yml` — add a step running `pytest tests/` (the panel
  test job; keep it non-blocking-optional first if you prefer, but wire it).

**Out of scope**:
- Live-traffic tests (stay on the server per §7).
- Changing generation code — if a golden test reveals a bug, report it separately.

## Git workflow

- Branch: `advisor/020-render-regression-tests`. Commit fixtures + tests + CI wiring. No push/PR unless instructed.

## Steps

### Step 1: Build a seeded-DB fixture

Add a pytest fixture that creates a SQLite DB and seeds a representative matrix:
a couple of Domains (direct + reality + cdn), users, and enabled Proxies across
proto/transport (vless-tcp, vless-reality, trojan-ws, mieru, anytls). Reuse the
app's own seeding where possible (init_db) or insert rows directly.

**Verify**: fixture builds without error in a bare `pytest` run.

### Step 2: Golden-file assertions on generated output

For that fixture, generate (a) `make_proxy()` dicts per proto/transport and (b)
the full Xray-JSON / sing-box / share-link subscriptions, and assert key fields
(`port`, `alpn`, `path`, `transport`, presence/absence of each protocol) against
checked-in expected values. Start with the specific regressions above (AnyTLS row
present; ShadowTLS absent from combined sub; the 7 Domain port columns populated).

**Verify**: `cd hiddify-panel/src && python -m pytest tests/test_render_golden.py -v` → pass.

### Step 3: Wire into CI

Add a `pytest tests/` step to the panel CI job. If you want to avoid blocking on
day one, allow-failure first, then flip to required once stable.

**Verify**: the workflow YAML is valid (`python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/main.yml'))"`).

## Test plan

- The golden tests ARE the deliverable. Keep them deterministic (no timestamps in
  golden output; if generation embeds any, normalize before asserting).
- Follow plan 001's import-light style; the DB fixture is the one heavyweight piece.

## Done criteria

- [ ] `pytest tests/test_render_golden.py` passes against checked-in goldens
- [ ] Goldens cover ≥5 proto/transport combos incl. AnyTLS + a combined-sub exclusion case
- [ ] CI runs `pytest tests/`
- [ ] No generation SOURCE changed (only tests/fixtures/CI)
- [ ] `plans/README.md` row updated

## STOP conditions

- Generation can't be driven offline without a live core/network — capture what's
  needed; a partial golden set (dict-level, no live validation) is still valuable, ship that.
- A golden test fails because the CURRENT output is itself buggy (not your test) —
  report it as a finding; do not encode the buggy output as the golden.

## Maintenance notes

- Golden files need updating when output intentionally changes — document the
  regenerate step in a comment at the top of the test.
- This is the CI safety net for every future `hutils/proxy` change.
