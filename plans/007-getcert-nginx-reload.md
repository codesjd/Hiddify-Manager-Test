# Plan 007: Reload nginx with the ACME challenge on the single-domain cert path

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Cert issuance must be confirmed on a
> real server (`PROJECT_SPEC.md` §7).
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- acme.sh/get_cert.sh acme.sh/cert_utils.sh acme.sh/prepare_acme.sh`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: correctness / reliability
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

The single-domain cert path (the panel's per-domain "get certificate" action →
`get_cert.sh`) writes the ACME challenge location into `nginx/parts/acme.conf`
but never reloads the running nginx, so `/.well-known/acme-challenge/*` 404s,
HTTP-01 validation fails, and the domain silently falls back to a self-signed
cert. The full-install path works only because it calls `start_nginx_acme` once
up front. This is a likely contributor to "cert not obtained" reports.

## Current state

- `acme.sh/get_cert.sh` (whole file) — calls `get_cert` then `stop_nginx_acme`,
  with **no** `start_nginx_acme`:
  ```bash
  #!/bin/bash
  cd $(dirname -- "$0")
  source cert_utils.sh
  get_cert $1
  echo "cert installation is done."
  sleep 2
  stop_nginx_acme
  ```
- `acme.sh/cert_utils.sh:72-77` — `start_nginx_acme()` is the ONLY place that
  writes `acme.conf` AND reloads nginx:
  ```bash
  start_nginx_acme(){
      mkdir -p /opt/hiddify-manager/acme.sh/www/.well-known/acme-challenge
      echo "location /.well-known/acme-challenge {root /opt/hiddify-manager/acme.sh/www/;}" >/opt/hiddify-manager/nginx/parts/acme.conf
      chown -R nginx /opt/hiddify-manager/acme.sh/www/
      systemctl restart hiddify-nginx
  }
  ```
- `acme.sh/prepare_acme.sh` (the acme `--pre-hook`) writes `acme.conf` but was
  deliberately stripped of its nginx reload (comment explains it relies on
  `start_nginx_acme` having run once, to avoid parallel-restart races during the
  full-install loop).
- `stop_nginx_acme` (cert_utils.sh) empties `acme.conf` and reloads — so in
  steady state the running nginx has an EMPTY acme.conf loaded.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| Shell syntax | `bash -n acme.sh/get_cert.sh` | exit 0 |
| (server) issue | trigger the panel "get certificate" for a real domain pointing at the box | real (non-self-signed) cert installed |
| (server) challenge served | `curl -s http://<domain>/.well-known/acme-challenge/test` after start_nginx_acme | served by nginx (not 404 from elsewhere) |

## Scope

**In scope**:
- `acme.sh/get_cert.sh` — add the missing `start_nginx_acme` call.

**Out of scope**:
- `prepare_acme.sh` (leave the reload out of it — that removal was intentional
  to avoid the parallel-restart race; the fix belongs in the single-domain
  caller).
- `cert_utils.sh` `get_cert()` issuance/install-gating logic (already fixed
  this session).
- The full-install path in `run.sh` (already calls `start_nginx_acme`).

## Git workflow

- Branch: `advisor/007-getcert-nginx-reload`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Call start_nginx_acme before issuing

In `get_cert.sh`, add `start_nginx_acme` before `get_cert $1`, mirroring the
full-install path (which reloads nginx with the challenge location up front):

```bash
source cert_utils.sh
start_nginx_acme      # ensure running nginx serves /.well-known/acme-challenge
get_cert $1
echo "cert installation is done."
sleep 2
stop_nginx_acme
```

**Verify**: `bash -n acme.sh/get_cert.sh` → exit 0;
`grep -n "start_nginx_acme" acme.sh/get_cert.sh` → 1 match before `get_cert`.

### Step 2: (MANDATORY server verification)

On a box with a real domain pointing at it, trigger the panel's single-domain
"get certificate". Confirm HTTP-01 succeeds and a real cert (not self-signed) is
installed at `/opt/hiddify-manager/ssl/<domain>.crt`.

**Verify (server)**: `openssl x509 -in /opt/hiddify-manager/ssl/<domain>.crt -noout -issuer`
shows a real CA (e.g. Let's Encrypt/ZeroSSL), not the self-signed subject.

## Test plan

- Offline: `bash -n` is the gate (this is shell orchestration).
- Server Step 2 is the real regression check — the whole point is a real cert.

## Done criteria

- [ ] `bash -n acme.sh/get_cert.sh` exit 0; `start_nginx_acme` called before `get_cert`
- [ ] (server) single-domain issuance yields a real CA cert, not self-signed
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- `get_cert.sh` or `cert_utils.sh` drifted from the excerpts.
- Adding `start_nginx_acme` breaks the full-install path because `get_cert.sh` is
  also invoked inside the parallel loop (check: is `get_cert.sh` called per-domain
  in `run.sh`? If yes, the up-front reload could re-introduce the race the
  comment warns about — STOP and report; the fix may need to be idempotent/guarded).
- On the server, HTTP-01 still 404s after the change — capture the nginx access
  log for the challenge path and report.

## Maintenance notes

- Keep `prepare_acme.sh` reload-free; the reload belongs in the single-domain
  entrypoint, not the per-domain pre-hook.
- Reviewer: confirm `get_cert.sh` is the single-domain path and not also the
  parallel full-install path (grep callers of `get_cert.sh`).
