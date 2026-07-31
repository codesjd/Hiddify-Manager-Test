# Plan 009: Fix two shell correctness bugs (iptables idempotency + masked exit code)

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- common/utils.sh install.sh docker-init.sh update.sh`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: correctness / reliability
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Two independent, verified shell bugs: (1) the iptables "add rule if missing"
guard is inert due to operator precedence, so every apply re-inserts firewall
rules; (2) `main |& tee` without `pipefail` reports the exit code of `tee`, not
`main`, so failed installs on the docker/manual paths report success. Both are
small, high-confidence fixes that improve reliability and make failures visible.

## Current state

- `common/utils.sh:388-394` — precedence bug: bash parses `A || B && C` as
  `(A || B) && C`, and `(iptables -C ...) || echo ...` is always exit-0, so
  `iptables -I` runs unconditionally; the `-C` existence check is dead:
  ```bash
  function add2iptables() {
      iptables -C $1 >/dev/null 2>&1 || echo "adding rule $1" && iptables -I $1
  }
  function add2ip6tables() {
      ip6tables -C $1 >/dev/null 2>&1 || echo "adding rule $1" && ip6tables -I $1
  }
  ```
- `install.sh:274-280` — `main |& tee $LOG_FILE; error_code=$?` with no
  `set -o pipefail` anywhere (grep confirms zero `pipefail` in these scripts), so
  `error_code` is `tee`'s status:
  ```bash
  if [[ " $@ " == *" --no-log "* ]]; then
      set -- "${@/--no-log/}"
      main
  else
      main |& tee $LOG_FILE
  fi
  error_code=$?
  ```
  `docker-init.sh:44` calls `./install.sh docker --no-gui $@` (no `--no-log`), so
  the container install hits exactly this masked branch. `update.sh:84-90` has
  the same `main |& tee` shape (do NOT run update.sh — it's forbidden — but the
  fix is safe to apply).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n common/utils.sh install.sh docker-init.sh update.sh` | exit 0 |
| Logic check (offline) | see Step 1 verify (a tiny bash snippet) | prints once |
| (server) firewall | after two applies, `iptables -S \| sort \| uniq -d` | no duplicated rule lines |

## Scope

**In scope**:
- `common/utils.sh` — group the iptables add-branch (both v4 and v6 functions).
- `install.sh` — capture `main`'s real status in the `tee` branch.
- `docker-init.sh` — only if it independently pipes `main` (it calls install.sh,
  so fixing install.sh covers it; verify and leave docker-init untouched if so).
- `update.sh` — apply the same `tee` fix (safe; do not execute the script).

**Out of scope**:
- `save_firewall()` dedup logic (it masks the iptables bug downstream — leave it;
  it's a useful backstop).
- Broad `set -euo pipefail` hardening of these scripts (risky; separate effort).
  Only fix the specific `tee` pipe status.

## Git workflow

- Branch: `advisor/009-shell-exitcode-bugs`. One or two commits. No push/PR unless instructed.

## Steps

### Step 1: Fix the iptables precedence

Group the "echo + insert" so the insert only runs when `-C` fails (rule absent):
```bash
function add2iptables() {
    iptables -C $1 >/dev/null 2>&1 || { echo "adding rule $1"; iptables -I $1; }
}
function add2ip6tables() {
    ip6tables -C $1 >/dev/null 2>&1 || { ip6tables -I $1; }
}
```
(The echo is optional; the load-bearing change is grouping `-I` under the `||`.)

**Verify**: offline logic check —
```bash
bash -c 'f(){ true || echo add && echo INSERT; }; f'   # OLD behavior: prints INSERT (bug)
bash -c 'f(){ true || { echo add; echo INSERT; }; }; f' # NEW: prints nothing (rule exists → no insert)
```
The second prints nothing; that's the fixed semantics. Also `bash -n common/utils.sh` → exit 0.

### Step 2: Capture main's real exit code past the tee

In `install.sh`, make `error_code` reflect `main`, not `tee`. Simplest robust
fix — use `PIPESTATUS`:
```bash
else
    main |& tee $LOG_FILE
    error_code=${PIPESTATUS[0]}
fi
```
(Do NOT move `error_code=$?` — with `|&` the `PIPESTATUS[0]` is `main`'s status.
Alternatively add `set -o pipefail` scoped to this branch, but `PIPESTATUS[0]`
is the minimal, side-effect-free fix.) Apply the same to `update.sh`.

**Verify**: `bash -n install.sh update.sh` → exit 0; `grep -n "PIPESTATUS\[0\]" install.sh` → 1 match in the tee branch.

### Step 3: Confirm docker-init needs no separate change

Read `docker-init.sh:44` — it invokes `install.sh`, so Step 2 covers it. Only
edit docker-init.sh if it independently does `main |& tee` (it should not).

**Verify**: `grep -n "|& tee\||& tee" docker-init.sh` → no independent pipe (else report).

### Step 4: (Server verification, if available)

On a box: run `apply` twice, confirm no duplicate iptables rules; force a known
install failure on the docker path and confirm non-zero exit is now reported.

**Verify (server)**: `iptables -S | sort | uniq -d` → empty; a failing install
returns non-zero.

## Test plan

- Offline: the two `bash -c` logic snippets in Step 1 demonstrate the fix;
  `bash -n` on all files. These are the gates.
- Server Step 4 confirms real behavior (dup rules gone, failures visible).

## Done criteria

- [ ] `bash -n common/utils.sh install.sh update.sh` exit 0
- [ ] iptables add-branch grouped so `-I` runs only when `-C` fails (both v4/v6)
- [ ] `install.sh` (and `update.sh`) use `${PIPESTATUS[0]}` for `error_code` in the tee branch
- [ ] (server, if available) no duplicate iptables rules after two applies; failed install returns non-zero
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any excerpt drifted.
- Adding `PIPESTATUS[0]` surfaces that `main` was already returning non-zero on
  currently-"successful" installs (i.e. installs were failing silently all along)
  — report the real failure rather than masking it again.
- The iptables functions are called in a context relying on the unconditional
  insert (unlikely) — report.

## Maintenance notes

- Do not globally add `set -e`/`pipefail` to these large scripts here — many
  steps intentionally tolerate failure; that's a separate, carefully-scoped effort.
- Reviewer: confirm `save_firewall`'s dedup still runs (it's the backstop) and
  that the `tee` fix didn't change logging behavior.
