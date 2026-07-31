# Plan 006: Validate rendered config before restarting a core (self-test + safe write)

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Render-pipeline changes must be
> exercised on a real server before DONE (`PROJECT_SPEC.md` §7).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- xray/run.sh singbox/run.sh common/jinja.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: MED
- **Depends on**: none
- **Category**: correctness / reliability
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

There is currently **no validation gate between a bad rendered config and a
live core restart**. This is why a malformed `xPaddingBytes` value earlier
crash-looped xray in production instead of being caught: the config self-test
is commented out, and the render engine writes unparseable output to disk on a
parse failure instead of keeping the last-good file. Two small changes restore
a fail-safe: (1) skip writing (keep previous) when the rendered JSON doesn't
parse, and (2) re-enable the core config self-test so a broken config never
triggers a restart.

## Current state

- `xray/run.sh:29-49` — the self-test is commented; `if [[ $? == 0 ]]` reads the
  preceding `echo`'s exit (always 0), so it always restarts; the else-branch is
  dead:
  ```bash
  if [ "$MODE" != "apply_users" ]; then
      # xray run -test -confdir configs
      echo "Ignoring xray test"
      if [[ $? == 0 ]]; then
          systemctl restart hiddify-xray.service
          systemctl start hiddify-xray.service
      else
          echo "Error in Xray Config!!!! do not reload xray service"
          sleep 60
          xray run -test -confdir configs
          ...
      fi
  fi
  ```
- `singbox/run.sh:9-27` — same pattern (`sing-box check` commented, dead else).
- `common/jinja.py:80-94` — on `json5.loads` failure it prints to stderr then
  **still writes** the raw unparseable content:
  ```python
  if rendered_content and output_file_path.endswith(".json"):
      try:
          json5object = json5.loads(rendered_content)
          rendered_content = json5.dumps(json5object, trailing_commas=False, indent=2, quote_keys=True)
      except Exception as e:
          print(f"Error parsing json {template_path}: {e}", file=sys.stderr)
  with open(output_file_path, "w", encoding="utf-8") as output_file:   # runs even on parse failure
      output_file.write(str(rendered_content))
  ```
- `xray` binary is on PATH after install; `xray run -test -confdir configs`
  exits non-zero on an invalid config set. sing-box uses `sing-box check -C <dir>`
  or `sing-box check -c <file>` (confirm the exact flag the installed version
  uses — read `singbox/run.sh` header / the binary's `--help` on the server).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n xray/run.sh singbox/run.sh` | exit 0 |
| py_compile | `python -m py_compile common/jinja.py` | exit 0 |
| (server) self-test | `xray run -test -confdir xray/configs` | exit 0 on good config |
| (server) apply | `DO_NOT_INSTALL=true ./install.sh apply_configs` | completes, services active |

## Scope

**In scope**:
- `common/jinja.py` — skip writing (keep previous file) when a `.json` target
  fails to parse.
- `xray/run.sh` — re-enable `xray run -test -confdir configs` as the real gate.
- `singbox/run.sh` — re-enable `sing-box check` as the real gate.

**Out of scope**:
- The executor swap in plan 004 (separate; both can coexist — apply order
  doesn't matter, but avoid editing the same lines twice).
- The import-time `json.load(current.json)` risk (known, separate).
- Changing what templates render — only the write/validate behavior.

## Git workflow

- Branch: `advisor/006-config-selftest`. Commit per file/logical unit. No
  push/PR unless instructed.

## Steps

### Step 1: Make jinja skip the write on parse failure

In `common/jinja.py`, restructure so that when `output_file_path` ends in
`.json` and `json5.loads` raises, the function **does not overwrite** the
existing output file (log to stderr and return/skip the write for that file).
Non-`.json` targets keep current behavior. Preserve the `chmod`/`chown` only
when a write actually happened.

Target shape:
```python
if rendered_content and output_file_path.endswith(".json"):
    try:
        obj = json5.loads(rendered_content)
        rendered_content = json5.dumps(obj, trailing_commas=False, indent=2, quote_keys=True)
    except Exception as e:
        print(f"Error parsing json {template_path}: {e}; keeping previous {output_file_path}", file=sys.stderr)
        return   # do NOT clobber the last-good file
with open(output_file_path, "w", encoding="utf-8") as f:
    f.write(str(rendered_content))
... # chmod/chown only on this path
```

**Verify**: `python -m py_compile common/jinja.py` → exit 0.

### Step 2: Re-enable the xray self-test as the restart gate

In `xray/run.sh`, replace the `echo "Ignoring xray test"` with a real
`xray run -test -confdir configs` and let `if [[ $? == 0 ]]` gate the restart.
Keep the else-branch behavior sane: on a failed test, do NOT restart (leaving
the running core on its last-good config), log clearly, and exit non-zero so the
caller/`check_hiddify_panel` can surface it. Remove the `sleep 60` busy-waits or
keep a single bounded retry — but the core must never be restarted onto a config
that failed `-test`.

**Verify**: `bash -n xray/run.sh` → exit 0; `grep -n "Ignoring xray test" xray/run.sh` → no matches.

### Step 3: Re-enable the sing-box check

Same treatment in `singbox/run.sh` using the correct `sing-box check` invocation
for the installed version (confirm the flag on the server). Gate the restart on
its exit code; never restart onto a failing config.

**Verify**: `bash -n singbox/run.sh` → exit 0.

### Step 4: (MANDATORY server verification)

On a staging/real box: (a) run a normal apply — confirm both cores self-test
clean and restart; (b) deliberately introduce a bad value in one template,
render, and confirm the core is NOT restarted and the previous config file is
preserved (jinja skip-write) and/or the self-test blocks the restart. Then
revert the bad value.

**Verify (server)**: good config → services `active`; bad config → running core
stays on last-good, error logged, no crash-loop.

## Test plan

- Offline: `bash -n` + `py_compile` gates. Add a small pytest for the jinja
  behavior IF you can call `render()` on a fixture template that produces
  invalid JSON and assert the output file is unchanged — only if it can run
  without the full `current.json`/app (it reads `current.json` at import, so
  this may need a fixture; if not feasible, rely on server Step 4 and say so).
- Server Step 4 is the real regression gate.

## Done criteria

- [ ] `bash -n xray/run.sh singbox/run.sh` exit 0; no "Ignoring xray test" left
- [ ] `python -m py_compile common/jinja.py` exit 0; parse-failure path returns without writing
- [ ] (server) bad config does NOT restart the core and preserves last-good file
- [ ] (server) good config still applies and restarts normally
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any excerpt drifted from live code.
- The installed `sing-box`/`xray` self-test flag differs from what you used and
  errors on a *valid* config (false positive) — report the correct flag; do not
  ship a gate that blocks good configs.
- Re-enabling the self-test reveals existing configs that fail `-test` on the
  current server (pre-existing latent breakage) — STOP and report; don't mask it.

## Maintenance notes

- This is the guard that would have caught the `xPaddingBytes` outage. Keep the
  invariant: never `systemctl restart` a core onto a config that failed `-test`.
- Complements plan 004 (jinja threads) — both touch `jinja.py`/`run.sh` but
  different lines; apply either order.
- Reviewer: verify the else-branch truly avoids restart (no fall-through
  `systemctl restart`).
