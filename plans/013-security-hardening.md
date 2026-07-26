# Plan 013: Security hardening — cookie flags, bootstrap password, API error leak

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`. Defensive changes only.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/base_setup.py hiddify-panel/src/hiddifypanel/models/admin.py hiddify-panel/src/hiddifypanel/panel/common.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (SEC-01/SEC-04); MED (SEC-03 — must not lock operators out)
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

Three independent, small, defensive gaps: (SEC-01) the admin session cookie is
emitted without `Secure`/`SameSite`, so it rides plaintext requests and
cross-site requests, widening CSRF surface; (SEC-03) a bootstrap fallback
creates a super-admin with the guessable password `admin`; (SEC-04) API 500s
return the raw exception string, leaking SQL/constraint/internal details.

## Current state

- `base_setup.py:114-126` configures server-side Redis sessions but sets **no**
  cookie flags:
  ```python
  114:  app.config['SESSION_TYPE'] = 'redis'
  116:  app.config['SESSION_REDIS'] = redis.from_url(os.environ['REDIS_URI_MAIN'])
  # no SESSION_COOKIE_SECURE / SAMESITE / HTTPONLY anywhere
  ```
  Flask defaults: `Secure=False`, `SameSite=None`, `HttpOnly=True`.
- `models/admin.py:208-219` (`get_super_admin`) — on missing `id==1` admin,
  inserts a super-admin with `password=generate_password_hash("admin")`
  (credential TYPE: default super-admin password; value referenced only):
  ```python
  db.session.add(AdminUser(id=1, uuid=str(uuid4()), username="admin",
      password=generate_password_hash("admin"), name="Owner",
      mode=AdminMode.super_admin, comment=""))
  ```
- `panel/common.py:53-57` — API error path returns the raw message unconditionally
  (not gated by `app.debug`):
  ```python
  if hutils.flask.is_api_call(request.path):
      return jsonify({'msg': str(e)}), 500
  ```
  (The HTML 500 traceback and the non-HTML `detail` are correctly `app.debug`-gated
  elsewhere — only this `msg` leaks.)

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/{base_setup.py,models/admin.py,panel/common.py}` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass |
| (server) cookie flags | login, inspect `Set-Cookie` | has `Secure; HttpOnly; SameSite=Lax` |

## Scope

**In scope**:
- `base_setup.py` — add the three cookie flags.
- `models/admin.py` — replace the static bootstrap password with a random one,
  surfaced to the operator.
- `panel/common.py` — return a generic message (+ log detail server-side) for API 500s.

**Out of scope**:
- Login rate-limiting (SEC-02) — separate plan (needs flask-limiter/Redis wiring).
- Node auth redesign (SEC-05) — separate, larger.
- The flask-admin action-CSRF question (SEC-06) — LOW-confidence, investigate separately.
- The `first_setup` / installer admin provisioning flow — read it (Step 2) but
  change only if needed to avoid lockout.

## Git workflow

- Branch: `advisor/013-security-hardening`. Commit per fix. No push/PR unless instructed.

## Steps

### Step 1: Set session cookie flags (SEC-01)

In `base_setup.py`, near the session config, add:
```python
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
```
Node-to-node calls authenticate via the `Hiddify-API-Key` header, not cookies, so
they're unaffected. `Lax` is compatible with the panel's own same-origin form posts.

**Verify**: `python -m py_compile .../base_setup.py` → exit 0;
`grep -n "SESSION_COOKIE_SECURE" .../base_setup.py` → 1 match.

### Step 2: Randomize the bootstrap super-admin password (SEC-03)

FIRST read how the normal install provisions the owner admin (the installer
imports `config.env` and `panel/cli.py` prints login links). Confirm the normal
path sets a real password/owner so this fallback is only a safety net. Then in
`get_super_admin`, replace `generate_password_hash("admin")` with a random
secret and surface it once to the operator (log it via the same channel
`panel/cli.py` prints login links, OR set a "must change on first login" flag if
one exists). Do NOT leave a static known password.

```python
import secrets
_pw = secrets.token_urlsafe(24)
... password=generate_password_hash(_pw) ...
logger.warning(f"Bootstrapped Owner admin; set a password immediately. Temp: {_pw}")
```
(Only log the temp password if there is no other surfacing path; prefer a
first-login-reset flag if the model supports it.)

**Verify**: `python -m py_compile .../admin.py` → exit 0;
`grep -n 'generate_password_hash("admin")' .../admin.py` → no matches.

### Step 3: Stop leaking exception text on API 500 (SEC-04)

In `panel/common.py`, return a generic message for API 500s and log the detail
server-side:
```python
if hutils.flask.is_api_call(request.path):
    logger.exception(e)
    return jsonify({'msg': 'Internal server error'}), 500
```
(If a correlation id is easy, include one; otherwise the generic message is
enough.) Leave the debug-gated HTML/detail paths as-is.

**Verify**: `python -m py_compile .../common.py` → exit 0;
`grep -n "'msg': str(e)" .../common.py` → no matches.

### Step 4: (Server verification, if available)

Log in, inspect `Set-Cookie` for all three flags; force an API 500 and confirm
no exception text is returned. Confirm normal login still works (Lax doesn't
break same-origin posts) and the installer still provisions a usable owner.

## Test plan

- Offline: if a Flask test client is available (needs app context), add a test
  asserting the login `Set-Cookie` carries `Secure; HttpOnly; SameSite=Lax`, and
  that a forced API 500 returns no `str(e)`. If app-context setup is too heavy
  offline, rely on server Step 4 and note it.
- SEC-03: add a test asserting the bootstrapped owner's password is NOT the
  literal `admin` (hash won't verify against "admin").

## Done criteria

- [ ] `py_compile` clean on all three files
- [ ] Session cookie sets Secure + HttpOnly + SameSite=Lax
- [ ] Bootstrap owner no longer uses the static `admin` password
- [ ] API 500 returns a generic message; detail only in server logs
- [ ] (server, if available) verified per Step 4; normal login unaffected
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Any file drifted from the excerpts.
- Setting `SESSION_COOKIE_SECURE=True` breaks login on an HTTP-only staging
  access pattern the operator uses (they front via HTTPS in prod — confirm; if
  they access the panel over plain HTTP intentionally, report before forcing Secure).
- Randomizing the bootstrap password could lock out an operator who relies on
  `admin`/`admin` on fresh installs — confirm the installer provisions the owner
  first; if not, STOP and report (don't silently lock them out).

## Maintenance notes

- Rotate any existing deployment still on `admin`/`admin`.
- SEC-02 (login rate-limit) and SEC-05 (node-auth rotation) are deferred to
  separate plans — note them in the index as follow-ups.
- Reviewer: confirm node-sync (header-auth) is unaffected by the cookie changes.
