# Plan 008: Bound install-path network calls with timeout + retry

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Install-path changes verified on a real
> server (`PROJECT_SPEC.md` §7).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- nginx/install.sh common/package_manager.sh common/utils.sh acme.sh/install.sh haproxy/install.sh`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: reliability
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Installs chronically hang or silently no-op on constrained/remote VPS (Turkey
especially). Several install-path network calls have no timeout and no retry, so
a slow or blocked endpoint hangs the whole install — the same failure class the
HAProxy PPA fix already addressed this session. This plan applies that same
bounded-timeout + backoff-retry pattern to the remaining unguarded calls.

## Current state

Unguarded network calls on the install hot path (from an audit sweep — confirm
each line before editing):
- `nginx/install.sh:13-18` — `curl https://nginx.org/keys/nginx_signing.key | gpg
  --dearmor | tee ...` : no timeout, no error check; a failed fetch yields a
  broken keyring, then `apt update`/`install_package nginx` proceed anyway.
- `common/package_manager.sh:114` — `curl -sL -o "$tmp_file" "$url"` (core binary
  downloads: xray/singbox/telemt/ssh/dnstt) : no `--connect-timeout`/`--max-time`,
  no retry. (It IS sha256-verified, so it fails safe, but can hang.) `add_package`
  uses `wget -q "$url"` (line ~42) likewise.
- `common/utils.sh:268` — `curl ... astral.sh/uv/install.sh | ... sh` (uv bootstrap).
- `common/utils.sh:307` — `curl bootstrap.pypa.io/get-pip.py | python`.
- `acme.sh/install.sh:8` — `curl -s -L https://get.acme.sh | sh`.

**Exemplar to copy** — the already-shipped HAProxy PPA fix in
`haproxy/install.sh` (added this session) wraps the call in `timeout` + a
backoff loop:
```bash
ppa_added=false
for backoff in 2 4 8 16; do
    if timeout 90 add-apt-repository -y ppa:vbernat/haproxy-${HAPROXY_VERSION}; then
        ppa_added=true; break
    fi
    warning "... failed, retrying in ${backoff}s"; sleep "$backoff"
done
if ! $ppa_added; then error "..."; fi
```
`warning`/`error` are defined in `common/utils.sh` (every script sources it).

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n nginx/install.sh common/package_manager.sh common/utils.sh acme.sh/install.sh` | exit 0 |
| (server) install | run a full install on a real box | completes; nginx/cores installed |

## Scope

**In scope** (add timeout+retry+result-check, matching the haproxy exemplar):
- `nginx/install.sh` (the signing-key curl + guard the apt steps on its success)
- `common/package_manager.sh` (the `curl -sL -o` download + the `wget` fetch)
- `common/utils.sh` (the uv and get-pip bootstraps)
- `acme.sh/install.sh` (the get.acme.sh bootstrap)

**Out of scope**:
- `haproxy/install.sh` (already done).
- The sha256-verification logic in `package_manager.sh` (keep it; just bound the
  fetch and retry before it).
- Changing WHICH endpoints are used or pinned versions.
- `get_release_version`/GitHub API helpers in `utils.sh` (they already have some
  `--connect-timeout`; only touch if clearly unguarded — verify first).

## Git workflow

- Branch: `advisor/008-install-network-timeouts`. Commit per file. No push/PR
  unless instructed.

## Steps

### Step 1: Guard the nginx signing-key fetch

Wrap the key `curl` in `timeout` + a backoff loop; if it ultimately fails,
`error` and do NOT proceed to `apt update`/install with a broken keyring (return
non-zero or skip). Use `curl --fail --connect-timeout 10 --max-time 60`.

**Verify**: `bash -n nginx/install.sh` → exit 0; `grep -n "timeout\|--max-time" nginx/install.sh` shows the guard.

### Step 2: Bound the core-binary downloads in package_manager.sh

Add `--connect-timeout 10 --max-time 300` (binaries are larger) and a small
retry loop around the `curl -sL -o` at ~line 114 and the `wget -q` at ~line 42.
Keep the existing sha256 check after a successful fetch — on retry exhaustion,
fail as it already does for a bad hash.

**Verify**: `bash -n common/package_manager.sh` → exit 0.

### Step 3: Bound the bootstrap pipes (uv, get-pip, acme.sh)

For the pipe-to-shell bootstraps at `utils.sh:268`, `utils.sh:307`, and
`acme.sh/install.sh:8`, wrap the `curl` in `timeout`/`--max-time` and retry the
fetch; keep the pipe. (These run rarely, at first install; a bounded single
retry is enough.)

**Verify**: `bash -n common/utils.sh acme.sh/install.sh` → exit 0.

### Step 4: (Server verification, if available)

Run a full install on a real box (ideally one on a constrained network).
Confirm it completes and installs nginx + cores. If no such box, note Step 4
pending and rely on `bash -n` + the fact the pattern mirrors the proven haproxy
fix.

**Verify (server)**: install completes; `nginx -v`, `xray version`, `sing-box version` all succeed.

## Test plan

- Offline: `bash -n` on every touched script is the gate.
- No pytest applies (shell network orchestration).
- Server Step 4 is the real-world check; the timeout values are the main thing
  to sanity-check (too low → false failures on slow-but-working links).

## Done criteria

- [ ] `bash -n` clean on all touched scripts
- [ ] Each targeted call has a bounded `timeout`/`--max-time` and a retry
- [ ] nginx key failure no longer lets a broken keyring proceed to apt install
- [ ] (server, if available) full install completes
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any excerpt drifted; or a targeted call already has a timeout (don't
  double-wrap — report).
- Chosen timeouts cause false failures on a legitimately slow link — raise them;
  don't remove the guard.
- A guarded failure now aborts an install that previously "succeeded degraded"
  in a way the operator relied on — report before making a fetch fatal (prefer
  fatal only for the nginx key + core binaries; keep optional bootstraps
  best-effort with a warning).

## Maintenance notes

- Keep timeout values generous (constrained networks are slow, not dead):
  connect ≤10s, total 60–300s depending on payload size.
- Reviewer: confirm the sha256 verification in `package_manager.sh` still runs
  after a successful (possibly retried) download.
- Consider extracting a shared `fetch_with_retry` helper into `common/utils.sh`
  in a later cleanup (see plan 015-family); this plan intentionally inlines to
  keep blast radius small.
