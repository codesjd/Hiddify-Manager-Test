# Plan 014: Make all_public_ports() single-source (kill the recurring drift)

> **Executor instructions**: Follow step by step, run verifications, honor STOP
> conditions, update `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 0c87bc75..HEAD -- hiddify-panel/src/hiddifypanel/hutils/network/net.py hiddify-panel/src/hiddifypanel/panel/admin/Actions.py`
> Mismatch vs "Current state" → STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 001 recommended (this is unit-testable)
- **Category**: tech-debt / correctness
- **Planned at**: commit `0c87bc75`, 2026-07-26

## Why this matters

`all_public_ports()` is implemented twice and `PROJECT_SPEC.md` §2.5 records
they were drift-fixed once already (`c7b4ecb`) and must stay in sync — **they've
re-drifted.** The `net.py` copy (served over the REST API `AllPublicPortsApi`,
used by operators/automation to configure a cloud security-group / external
firewall) is missing three port families the `Actions.py` copy has: L2TP
(500/4500/1701 UDP), AnyTLS (TCP), and tcp+vision REALITY (`internal_port_special`
TCP). Anyone provisioning a firewall from that API leaves those protocols
unreachable. Fixing the drift permanently means one source of truth.

## Current state

`hutils/network/net.py:569-611` — returns `{tcp:{port:label}, udp:{port:label}}`;
**missing** L2TP, AnyTLS, special_reality_tcp:
```python
def all_public_ports():
    tcp_ports={80:"http",443:"tls"}; udp_ports={443:"quic",}
    if hconfig(ConfigEnum.wireguard_enable): udp_ports[...]="wireguard"
    ... shadowsocks2022, mieru, ssh ...
    for d in Domain.query.all():
        udp_ports[d.internal_port_tuic]="tuic"; ...naive; ...hysteria2; ...xdns; ...xicmp
        if d.tls_port: tcp_ports[d.tls_port]="tls"; udp_ports[d.tls_port]="quic"
        if d.http_port: tcp_ports[d.http_port]="http"
    # NO l2tp, NO anytls, NO special_reality_tcp
    return {"tcp":to_int(tcp_ports),"udp":to_int(udp_ports)}
```
`panel/admin/Actions.py:76-128` — returns `{tcp:[int], udp:[int]}` (no labels);
**has** all three:
```python
if hconfig(ConfigEnum.l2tp_enable):
    for p in (500, 4500, 1701): udp_ports.add(p)
...
tcp_ports.add(d.internal_port_anytls)                 # AnyTLS
...
if d.mode == DomainType.special_reality_tcp:
    tcp_ports.add(d.internal_port_special)            # tcp+vision REALITY
```
`panel/commercial/restapi/v2/admin/system_actions.py:40` (`AllPublicPortsApi`)
serves the stale `net.py` copy.

## Commands you will need

| Purpose | Command | Expected |
|---------|---------|----------|
| py_compile | `python -m py_compile hiddify-panel/src/hiddifypanel/hutils/network/net.py hiddify-panel/src/hiddifypanel/panel/admin/Actions.py` | exit 0 |
| Tests | `cd hiddify-panel/src && python -m pytest tests/ -v` | pass incl. new test |

## Scope

**In scope**:
- `hutils/network/net.py:569-611` — add the 3 missing families (become the single source).
- `panel/admin/Actions.py:76-128` — replace the port-collection body with a call
  to `hutils.network.all_public_ports()`, adapting the shape (labels→bare ints).
- `hiddify-panel/src/tests/test_all_public_ports.py` (create).

**Out of scope**:
- `system_actions.py` (it already serves net.py — leave it; it now gets the fixed data).
- The in-host firewall (`common/utils.sh:allow_apps_ports` derives from live
  sockets `ss -tulpn`, independent — do not touch).
- Changing the REST response shape (keep whatever `AllPublicPortsApi` returns).

## Git workflow

- Branch: `advisor/014-all-public-ports-drift`. One commit. No push/PR unless instructed.

## Steps

### Step 1: Add the 3 missing families to net.py (the source of truth)

In `net.py:all_public_ports`, add (matching the Actions.py logic; import
`DomainType` if needed):
```python
if hconfig(ConfigEnum.l2tp_enable):
    for p in (500, 4500, 1701):
        udp_ports[p]="l2tp"
...
for d in Domain.query.all():
    ... existing ...
    tcp_ports[d.internal_port_anytls]="anytls"
    if d.mode == DomainType.special_reality_tcp:
        tcp_ports[d.internal_port_special]="reality_tcp"
```

**Verify**: `python -m py_compile .../net.py` → exit 0;
`grep -n "l2tp\|anytls\|special_reality_tcp\|internal_port_special" .../net.py` shows the additions.

### Step 2: Make Actions.py wrap net.py

Replace the Actions.py `all_public_ports` body (lines 77-128) with a call to the
net.py implementation, converting the `{port:label}` dicts to the bare-int
`{tcp:[int], udp:[int]}` shape the view returned before:
```python
from hiddifypanel.hutils.network.net import all_public_ports as _all_public_ports
...
def all_public_ports(self):
    p = _all_public_ports()
    return {"tcp": sorted(p["tcp"].keys()), "udp": sorted(p["udp"].keys())}
```
Keep the `@login_required(roles={Role.admin})` decorator. Confirm the view's
callers/consumers accept `list[int]` (they did before — same shape).

**Verify**: `python -m py_compile .../Actions.py` → exit 0;
`grep -n "tcp_ports=\|udp_ports=" .../Actions.py` → the manual sets are gone from this method.

### Step 3: Add a regression test locking the two in sync

In `tests/test_all_public_ports.py`, seed an in-memory SQLite DB (or stub) with
domains + enabled protocols covering all families, call both `net.all_public_ports()`
and the Actions view, and assert the Actions output equals the sorted int-keys of
the net output — so any future drift fails the test. If full DB setup is too
heavy offline, at minimum assert that the Actions method delegates to net.py
(e.g. monkeypatch `_all_public_ports` and check the view returns its keys).

**Verify**: `cd hiddify-panel/src && python -m pytest tests/test_all_public_ports.py -v` → pass.

## Test plan

- New test proves Actions == net (int-key view), preventing re-drift.
- Follow plan 001's import-light test pattern; stub ORM where possible.

## Done criteria

- [ ] `py_compile` clean on both files
- [ ] net.py includes L2TP, AnyTLS, special_reality_tcp
- [ ] Actions.py delegates to net.py (no duplicate collection logic)
- [ ] Regression test passes and would fail on future drift
- [ ] No files outside scope modified
- [ ] `plans/README.md` row updated

## STOP conditions

- Either file drifted from the excerpts.
- A consumer of the Actions view relies on the label dict rather than bare ints
  (it returned bare ints before, so unlikely) — report before changing the shape.
- `DomainType`/`internal_port_special`/`internal_port_anytls` are named
  differently than shown — read `models/domain.py` and use the real names.

## Maintenance notes

- Single source of truth now — future port families go in net.py only.
- Reviewer: confirm the REST `AllPublicPortsApi` output now includes the 3 added
  families (that endpoint feeds external firewall automation).
