# Plan 018: Add a `doctor`/preflight diagnostic command

> **Executor instructions**: Build plan. Follow steps, run verifications, honor
> STOP conditions, update `plans/README.md`. Diagnostics are read-only.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- status.sh menu.sh install.sh`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (read-only diagnostics)
- **Depends on**: none
- **Category**: direction / dx
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Install failures on constrained/remote VPS (Turkey) are chronic and the git log
is full of one-off fixes for them, but there is no preventive check. `status.sh`
is 57 lines of `systemctl is-enabled` — it checks none of the things that
actually fail (DNS pointing at the box, 80/443 reachable, RAM/swap headroom for
the 512MB target, cert validity, cores' control ports, `current.json` validity).
A `doctor` command turns "install silently hung / cert self-signed / OOM" into an
actionable report.

## Current state

- `status.sh` (57 lines) — prints global IP and, per service, `systemctl
  is-enabled`. No DNS/port/mem/cert/JSON checks.
- `menu.sh:47-55,168-171` — operator menu maps `status` → `status.sh`; adding a
  `doctor` entry is a one-line menu addition.
- `install.sh` — grep for `MemTotal`/`swap`/`free` = 0 hits: no memory preflight
  despite the 512MB target.
- Reusable helpers exist in `common/utils.sh` (`hiddify-http-api`, `allow_port`,
  service checks) and the HAProxy stats socket `/run/haproxy-master.sock`
  (`PROJECT_SPEC.md` §2.2).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n doctor.sh menu.sh` | exit 0 |
| (server) run | `bash doctor.sh` | prints a PASS/WARN/FAIL report, exits cleanly |

## Scope

**In scope**:
- New `doctor.sh` at repo root (read-only checks).
- `menu.sh` — add a `doctor` menu entry invoking it.

**Out of scope**:
- Any check that MUTATES state (this is diagnostics only).
- Changing `status.sh` (leave it; doctor is the richer companion).
- Auto-remediation (report only; the operator acts).

## Git workflow

- Branch: `advisor/018-doctor-command`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Write doctor.sh with checks scoped to KNOWN failure modes

Source `common/utils.sh`. Implement checks, each printing `PASS`/`WARN`/`FAIL`
(color via the existing `error`/`warning`/`success` helpers) and NEVER exiting
non-zero mid-run (collect and summarize). Scope to failures seen in git history:
- **MAIN_DOMAIN resolves to this box's IP** (`dig +short` vs the server IP the
  installer already computes) — WARN on mismatch.
- **80 and 443 reachable** (locally bound; and optionally an external check).
- **Memory/swap**: `MemTotal` and swap vs a 512 MB floor — WARN if under with no swap.
- **Cert presence + expiry** for each domain under `/opt/hiddify-manager/ssl/*.crt`
  (`openssl x509 -enddate`), FAIL on expired/self-signed where a real cert is expected.
- **Each core control port answering** (xray 10085, singbox 10086) and the 5 core
  services `active`.
- **`current.json` is valid JSON** (`jq empty` — the §2.3 silent-cascade file).

**Verify**: `bash -n doctor.sh` → exit 0.

### Step 2: Wire it into menu.sh

Add a `doctor` entry mirroring how `status` is wired (`menu.sh:47-55,168-171`).

**Verify**: `bash -n menu.sh` → exit 0; `grep -n "doctor" menu.sh` → 1+ matches.

### Step 3: (Server verification)

Run `bash doctor.sh` on a real box (ideally one exhibiting an install problem).
Confirm it correctly flags the actual issue and PASSes a healthy box (no false
FAILs — false positives erode trust, so tune thresholds conservatively).

## Test plan

- Offline: `bash -n` is the gate; optionally `shellcheck doctor.sh` if available.
- Server Step 3: run against a healthy box (all PASS) and a broken one (correct FAIL).

## Done criteria

- [x] `bash -n doctor.sh menu.sh` exit 0
- [x] doctor.sh checks DNS, ports, mem/swap, certs, core ports/services, current.json
- [x] All checks are read-only (no state mutation)
- [x] menu.sh exposes `doctor`
- [x] (server) healthy box → all PASS; broken box → correct FAIL
- [x] `plans/README.md` row updated

## STOP conditions

- `status.sh`/`menu.sh` drifted.
- A check requires mutating state to run — redesign it read-only or drop it.
- The server-IP source the installer uses isn't easily reusable — report; DNS
  check needs a reliable "this box's IP".

## Maintenance notes

- Keep checks scoped to real, seen failure modes — resist adding low-signal checks.
- This pairs naturally with a post-install auto-run of `doctor` (a follow-up).
- Reviewer: confirm no check can hang (bound any network probe with `timeout`).
