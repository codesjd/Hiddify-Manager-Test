# Plan 019: A `--lite` / low-RAM install profile (spike → implement)

> **Executor instructions**: SPIKE-then-implement. Measure first (Step 1), then
> wire the profile. Verify on a real box. Update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- install.sh config.env.default`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P3
- **Effort**: S–M
- **Risk**: LOW–MED
- **Depends on**: best sequenced AFTER 017 (SQLite) and 002/003/005 (the big RAM levers)
- **Category**: direction
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

To fit 512 MB without losing features you actually use, the operator shouldn't
pay RAM for daemons they don't. The per-subsystem gating already exists — every
`other/*` subsystem is opt-in via an `hconfig` enable flag, and
`HIDDIFY_APPLY_SUBSYSTEMS` already narrows an apply. A `lite` profile formalizes
"default the optional daemons off" without removing any capability (each can be
re-enabled). Honest caveat: the big consumers are MariaDB/Redis (addressed by
002/003/017), so this plan COMPOUNDS those — it's not the main lever alone.

## Current state

- `install.sh:92-160` — each `other/*` subsystem is gated by an `hconfig` enable
  flag passed to `install_run` (`dnstt_enable`, `telegram_enable`,
  `ssfaketls_enable`, `wireguard_enable`, `has_l2tp_outbound`, …).
- `install.sh:214-251` — `HIDDIFY_APPLY_SUBSYSTEMS` already implements opt-in
  narrowing of an apply to an allow-list (the apply-time analogue).
- No existing `lite`/`low-mem`/`minimal` profile (grep confirms).
- `PROJECT_SPEC.md` §2.1: **never disable a core** (both xray+singbox must run —
  disabling one caused outages). A lite profile must NOT touch cores.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n install.sh` | exit 0 |
| (server) RSS per unit | `systemctl status <unit>` / `ps -o rss= -p <pid>` | measured baseline |
| (server) lite install | `HIDDIFY_PROFILE=lite ./install.sh ...` | optional daemons not started; stack works |

## Scope

**In scope**:
- `install.sh` — a `HIDDIFY_PROFILE=lite` (or flag) that defaults the OPTIONAL
  subsystem enable-flags off (never cores, never DB, never Redis, never haproxy/nginx).
- `config.env.default` — document the profile and what it disables.

**Out of scope**:
- Cores (xray/singbox) — never disabled (§2.1).
- MariaDB/Redis/haproxy/nginx (non-optional; handled by 002/003/017).
- Removing subsystems — this only changes DEFAULTS; all stay re-enableable.

## Git workflow

- Branch: `advisor/019-lite-profile`. Commit spike measurements separately. No push/PR unless instructed.

## Steps

### Step 1 (SPIKE): Measure per-subsystem RSS on a real box

On a running box, record RSS for each optional `other/*` daemon
(ss-faketls, dnstt-router, telegram, wireguard, amneziawg, mieru). This tells you
which defaults-off actually move the needle vs. 002/003/017. Report the numbers.

**STOP if**: the optional daemons collectively use trivial RAM (<~30 MB) — then a
lite profile isn't worth it vs. 002/003/017; report and recommend REJECT.

### Step 2 (IMPLEMENT): Add the profile

If Step 1 justifies it, add `HIDDIFY_PROFILE=lite` handling in `install.sh` that
sets the optional enable-flags off by default (operators re-enable specific ones
via `config.env`/panel). Ensure cores/DB/Redis/haproxy/nginx are untouched.

**Verify**: `bash -n install.sh` → exit 0.

### Step 3: Document it

Add `HIDDIFY_PROFILE=lite` to `config.env.default` with the list of what it
disables and a note that anything can be re-enabled.

### Step 4 (server): Verify a lite install

`HIDDIFY_PROFILE=lite ./install.sh` on staging: optional daemons not started, all
cores + panel + proxying still work, and re-enabling one subsystem via config
brings it back.

## Test plan

- Offline: `bash -n`. No pytest applies.
- Server Steps 1 & 4 are the real evidence (RSS deltas + functional check).

## Done criteria

- [ ] Step 1 RSS measurements reported (justify or reject the profile)
- [ ] (if justified) `HIDDIFY_PROFILE=lite` defaults optional daemons off; cores/DB/Redis untouched
- [ ] `config.env.default` documents it
- [ ] (server) lite install works; re-enable path works
- [ ] `plans/README.md` row updated (or REJECTED with the RSS reasoning)

## STOP conditions

- `install.sh` drifted.
- The profile would disable a subsystem a rendered subscription still points at
  (breaks clients) — the profile must only affect defaults for NEW installs and
  never silently disable something in use.
- Any temptation to disable a core — forbidden (§2.1).

## Maintenance notes

- Sequence AFTER the big levers (017/002/003/005); on its own it's a modest win.
- Reviewer: confirm cores/DB/Redis are never in the disable set.
