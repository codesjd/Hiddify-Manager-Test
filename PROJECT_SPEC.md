# Hiddify-Manager Fork — Whole-Project Spec & Execution Plan

> **Role of this document.** This is the *plan*, and the plan is the product. It is written to be
> executed by other agents/engineers who did not do the original work. It carries the architecture,
> the non-negotiable operating rules, the current state of every major feature area, and precise,
> self-contained specs for the open work. An executor should be able to pick up any item in §5,
> implement it, verify it against the stated done-criteria, and ship it without needing to
> reconstruct context first.
>
> It is **not** an implementation. No item here has been half-built against this document. Where
> code already exists, that is noted with a confidence level in §4.

---

## 0. How to use this document

1. Read §1–§3 once. They are the mental model and the rules. Violating §3 is how this project has
   historically taken the production server down.
2. Pick a work item from §5. Each is written as: *problem → root cause (if known) → change → files →
   verification → done-criteria*. Do only what the item says; do not "improve" adjacent code.
3. Run the verification gates in §7 **before every commit**, not just at the end.
4. Follow the dual-branch workflow in §1.3 for every change.

---

## 1. What this project is

### 1.1 Summary
A heavily patched fork of **Hiddify-Manager** (the VPN panel + the shell install/apply system that
renders and runs xray-core, sing-box, HAProxy, nginx, and assorted `other/*` subsystems). ~110
commits of custom work sit on top of upstream, spanning new protocols/transports, a reworked HAProxy
relay, panel/DB features, install-time robustness fixes, and an admin-UI redesign.

The running record of *why* each patch exists is **`CHANGES_BY_CLAUDE.md`** (1200+ lines, mostly
Farsi). Treat it as the changelog/rationale log. This spec is the forward-looking companion.

### 1.2 The three branches
| Branch | Purpose | Notes |
|---|---|---|
| `claude/saving-mechanism-bug-yvzifn` | Primary feature/dev branch | Default target for new work. |
| `optimize` | Parallel integration branch | Receives cherry-picks of feature-branch commits. **A separate, concurrent process also pushes here** (e.g. the schema-reconciler commits `9c09bde7`/`5869b880`/`bf98e727` appeared here without going through this workflow). Always `git fetch` before cherry-picking. |
| `claude/dashboard-modern-redesign` | "Orbit Admin" dashboard redesign | **Stale ref, safe to delete** (see §5.5) — its tip (`f17eec4`) is a plain git ancestor of the feature branch with zero unique commits. The actual redesign work landed on the feature branch itself (`592957c`) and is live on both active branches, wired into `Dashboard.py::index_modern.html`. |

### 1.3 Dual-branch commit workflow (mandatory)
For every change:
1. Commit to `claude/saving-mechanism-bug-yvzifn`, verify (§7), push with retry/backoff.
2. In the `optimize` worktree: `git fetch origin optimize`, cherry-pick the commit, re-verify, push.
3. **Migration numbers are NOT portable between branches** (see §3 rule 5). If the cherry-pick touches
   `init_db.py`/`config_enum.py`, expect a conflict, renumber for the destination branch, then run
   `python3 common/check_migrations.py <path-to-init_db.py-on-that-branch>` before continuing.

---

## 2. Architecture map

### 2.1 Two cores, one `core_type`
- **xray-core** serves vless/vmess/trojan/reality/xhttp and the custom finalmask protocols
  (xdns/xicmp) and the new native `hysteria`.
- **sing-box** serves hysteria2/tuic/shadowsocks2022/anytls/mieru/naive — these exist **only** as
  sing-box inbounds; there is no xray template for them.
- `core_type` (DB config) picks the *primary* core, but **both run**. On an xray-primary install,
  sing-box must still run or every sing-box-only protocol points at a dead port. They self-exclude
  overlapping inbounds via `{% if core_type=="singbox" %}` gates and use distinct control ports.
- Do not "simplify" this by disabling a core. That has caused outages (see `CHANGES_BY_CLAUDE.md`
  §"Keep sing-box running on xray-core installs").

### 2.2 HAProxy multi-hop relay (the part that surprises people)
`:443` (`https-in`, raw SNI passthrough) → `to_https_in_ssl` (relays via `send-proxy-v2` to an
abstract socket) → `in-tcpmode` (real TLS termination, ALPN shortcut, then `use_backend v10-*`
path rules) → per-protocol backends → `127.0.0.1:5000` (singbox) or the xray inbound. A separate
`in-httpmode` frontend handles a MAP-based dynamic-backend path.
- Per-domain "port exclusivity" reject rules must be guarded with `!{ ssl_fc }` so they only fire on
  genuine plaintext, never on relayed HTTPS (bug fixed in `33f2eed`).
- Introspect live state with `echo "@1 show stat" | socat stdio /run/haproxy-master.sock` (the `@1`
  routes to worker 1). `show map <path>` proves map freshness.

### 2.3 Config render pipeline (memorize this — it's the blast radius)
```
DB  →  all_configs_for_cli()  →  /opt/hiddify-manager/current.json
                                        │  (read at MODULE IMPORT time by)
                                        ▼
                              common/jinja.py  →  renders every *.j2 →  per-subsystem .json
```
- `common/jinja.py` reads `current.json` with a bare `json.load()` at import. If that file is empty
  or invalid, **every** template render silently no-ops (per-file try/except → stderr only → no
  output file). This once cascaded into an outage.
- `reload_all_configs()` in `common/utils.sh` now writes atomically (temp file → `jq` validate →
  `mv`) and leaves the previous good file untouched on failure (fixed `78c977a`). Preserve this
  pattern for any future writer of `current.json`.

### 2.4 The schema reconciler (foreign to older checkouts — do not fight it)
`hiddify-panel/src/hiddifypanel/database.py::reconcile_schema()` (called from `init_db()`) uses
Alembic `compare_metadata()` to auto-apply **only** additive diffs (`add_table`/`add_column`/
`add_index`), each behind a mandatory `backup_db()`. **Any** other diff (`modify_type`, renames,
extra columns) is treated as ambiguous: it logs an ERROR, returns `False`, and the caller does
`sys.exit(1)`. There is **no bypass flag** by design.
- Consequence: adding a `ConfigEnum` member widens a MySQL `ENUM(...)` column, which is a
  `modify_type` — the reconciler will **refuse it and crash-loop the panel** until the column is
  widened manually (`ALTER TABLE {bool_config,str_config} MODIFY COLUMN key ENUM(...) NOT NULL`,
  values sourced live from the `ConfigEnum` class). Do this with the panel **stopped** or the ALTER
  starves on lock contention.

### 2.5 Panel code layout (where things live)
The panel (`hiddify-panel/src/hiddifypanel/`) is a Flask + flask-admin app. Full navigable map is in
§8; the parts you touch most:
- `models/` — SQLAlchemy models + enums: `config_enum.py` (all settings), `proxy.py`
  (`ProxyProto`/`ProxyL3`/`ProxyTransport`/`ProxyCDN`), `domain.py` (`DomainType`, port-offset props),
  `child.py` (multi-node), `user.py`/`admin.py`/`role.py`, `usage.py`, `routing.py`
  (custom outbounds/routing rules). Migrations live in `panel/init_db.py` (`_vNNN` functions).
- `hutils/proxy/` — subscription/config generation: `shared.py` (per-proxy dict builder + `get_port`),
  `xrayjson.py` (full Xray JSON sub), `singbox.py` (sing-box JSON sub), `xray.py` (share links),
  `clash.py`, `wireguard.py`/`amneziawg.py`.
- `panel/admin/` — flask-admin views (`DomainAdmin`, `SettingAdmin`, `ProxyAdmin`, `Actions`,
  `OutboundAdmin`, `RoutingRuleAdmin`, `InboundOverrideAdmin`, `NodeAdmin`, `QuickSetup`, `UserAdmin`,
  `Dashboard`).
- `panel/hiddify.py` — `all_configs_for_cli()` builds the DB→`current.json` payload (§2.3 pipeline).
- `panel/cli.py` — `hiddify-panel-cli` entrypoints (`all-configs`, `init-db`, `update-usage`, backup).
- `drivers/` — the **live control plane** (§2.8), distinct from the render pipeline.
- Note: **`all_public_ports()` is implemented twice** — `panel/admin/Actions.py` and
  `hutils/network/net.py`. Keep them in sync (drift bug fixed `c7b4ecb`).

### 2.6 Config data model (how a "setting" behaves)
- Settings are a fixed enum: **`ConfigEnum`** (~243 members). Each member carries a
  **`ConfigCategory`** (UI grouping: `general`/`proxies`/`tls`/`reality`/`hysteria`/`hidden`/…) and an
  **`ApplyMode`**: `nothing` | `apply_config` | `reinstall`. Values are stored per-child in
  `bool_config` / `str_config` tables (typed via `_BoolConfigDscr`/`_StrConfigDscr`/`_IntConfigDscr`/
  `_TypedConfigDscr`), read with `hconfig(ConfigEnum.x, child_id)`.
- `ApplyMode` is the contract for **what a settings change triggers**: `apply_config` → re-render +
  apply (fast), `reinstall` → full `install.sh install` (slow, reruns subsystem installers),
  `nothing` → stored only. Adding a setting means choosing the *cheapest* correct ApplyMode.
- Adding a `ConfigEnum` member widens a MySQL `ENUM` column → see the schema-reconciler crash-loop
  trap in §2.4. This is the single most common way a new setting breaks the panel.
- `Proxy` rows (protocol × transport × L3 × CDN combinations) are seeded by `init_db.py` migrations
  and enable/disable which inbounds render. `Domain` rows (with a `DomainType` mode) drive per-domain
  ports/certs/SNI.

### 2.7 Install / apply modes & the commander (how the panel drives the shell)
The panel never edits configs on disk directly. It calls **`commander(Command.x)`**
(`panel/run_commander.py` → `common/commander.py`), which spawns a detached shell process:
| Command | Runs | When |
|---|---|---|
| `apply` | `apply_configs.sh` (= `install.sh apply_configs`, `DO_NOT_INSTALL=true`) | most settings/domain/proxy changes (ApplyMode.apply_config) |
| `apply_users` | `install.sh apply_users` (`DO_NOT_INSTALL=true`, `MODE=apply_users`) | user add/remove — **fast path**, only re-renders per-user templates + pushes via drivers (§2.8) |
| `reinstall` | `install.sh install` | ApplyMode.reinstall settings, or Reinstall button |
| `restart_services` | `restart.sh` | Restart button |
- `install.sh main()` branches on `MODE`/`DO_NOT_INSTALL`: a full install runs every subsystem
  installer; `apply_configs` skips installers but re-renders + restarts; `apply_users` skips almost
  everything except the per-user render + driver push. `HIDDIFY_APPLY_SUBSYSTEMS` can scope an apply
  to specific subsystems.
- **The commander runs install.sh as a detached child of `hiddify-panel.service`** — this is why the
  `systemctl kill --kill-who=main` fix (§4.4) matters: a bare kill would take out the running apply.

### 2.8 Live driver control plane (the *other* path to the cores)
Parallel to the render pipeline, `drivers/` (`user_driver.py` fans out to `XrayApi`, `SingboxApi`,
`WireguardApi`, `AmneziaWgApi`, `SSHLibertyBridgeApi`, `TelemtApi`) talks to each running core's
**control API** (xray gRPC on 10085, singbox on 10086, etc.) to:
- `get_all_usage()` — pull per-UUID byte counters (drives usage accounting / quota enforcement).
- `add_client()` / `remove_client()` — push a single user live, no full re-render.
This is why `apply_users` is cheap and why both cores must stay running even on a single-core install
(§2.1) — the panel polls them for stats regardless of `core_type`. When debugging "usage not
counting" or "disabled user still connects," this path, not the render pipeline, is the suspect.

### 2.9 Multi-node (parent / child)
Real, first-class feature. A `Child` row has a `ChildMode`: `virtual` (single box, the common case),
`remote` (this panel is a child node of a parent), or `parent`. Config/proxies/domains/usage are all
per-child (FK to `child.id`). The sync happens over the **commercial REST API v2**
(`panel/commercial/restapi/v2/{parent,child}/`): children register with a parent, push usage, pull
config. `hutils/node/{parent,child,shared,api_client}.py` + `panel/admin/NodeAdmin.py` implement it;
`hutils.node.is_parent()/is_child()` gate behavior (e.g. the Dashboard renders `parent_dash.html`
instead of the redesigned `index_modern.html` in parent mode — see §5.5). Most single-VPS installs
never leave `virtual` mode, but **any change to config/usage/domain handling must not assume
single-node** — check the `child_id` dimension.

### 2.10 Request-serving stack (who answers a browser/client)
- **nginx** (`nginx/`) fronts the **panel** (Flask app served via uwsgi/asgi on `:9000` — the
  `hiddify-http-api` curl target in `common/utils.sh` hits `localhost:9000/<api_path>/api/v2/…`) and
  also acts as a **CDN-facing dispatcher**: unix-socket vhosts (`nginx/run/h1.sock`, `h2.sock`,
  `nginx_cdn_dispatcher*.sock`, `grpc-singbox.sock`) receive `proxy_protocol` traffic relayed from
  HAProxy and forward HTTP/1.1, HTTP/2, and gRPC to the right core. Real client IP is recovered via
  `set_real_ip_from` + the CF/AR real-ip conf snippets.
- **HAProxy** (`haproxy/`) is the `:443`/`:80` edge splitter (§2.2).
- **the cores** (`xray/`, `singbox/`) terminate the actual proxy protocols.
So the end-to-end path for a CDN/WS client is: client → HAProxy `:443` → (relay) → nginx socket →
core; for the panel: browser → HAProxy/nginx → uwsgi → Flask.

---

## 3. Operating rules (non-negotiable)

1. **Never run `update.sh`.** It pulls upstream and would overwrite the fork.
2. **Verify before every commit** (§7): `py_compile` all touched Python; `env.parse()` all touched
   Jinja; `bash -n` all touched shell.
3. **Atomic writes + validation** for any file another subsystem reads (see §2.3).
4. **Network-facing changes must be tested on the real server**, not assumed. The sandbox cannot
   exercise real xray/sing-box traffic.
5. **Migration numbers are per-branch.** Check the destination branch's actual `MAX_DB_VERSION` and
   highest `_vNNN` before adding/cherry-picking a migration; never assume the source number is free.
   Enforce this mechanically, not by eyeballing: `python3 common/check_migrations.py <path/to/init_db.py>`
   parses the file's AST (no import, no side effects) and fails if any `_vNNN` name is defined twice
   (Python silently lets the later definition shadow the earlier one — the first migration's body
   then never runs for anyone who already passed that version) or if `MAX_DB_VERSION` is lower than
   the highest defined `_vNNN` (that migration would never be dispatched). Run it against the
   destination branch's `init_db.py` **after** renumbering and **before** completing the cherry-pick
   or committing a new migration — treat a non-zero exit as a hard blocker, same as a failing verify
   gate in §7.
6. **Production DB caution.** Stop the panel before schema-widening ALTERs. Look at what you're about
   to delete/overwrite before doing it.
7. **Do not make speculative changes to REALITY routing.** `special_reality_tcp` binds directly (not
   via the 443 hop) *by design* to avoid the "received real certificate (potential MITM)" failure.
   This has been broken by "clever" changes before and reverted.
8. **Respect protocol/client compatibility** when generating subscriptions: exclude protocols a given
   client can't parse (e.g. ssh/dnstt/amneziawg/mieru/naive from the combined Xray-JSON and sing-box
   JSON subs) rather than emitting invalid outbounds.

---

## 4. Feature inventory & current state

Confidence: **A** = tested working on the real server · **B** = implemented + static-verified, not
fully field-tested · **C** = implemented but known-uncertain/open.

### 4.1 Protocols & transports
| Feature | State | Notes |
|---|---|---|
| REALITY direct-bind (`special_reality_tcp`) | A | Both xray and sing-box templates; `and ptls` guard fixes duplicate links. |
| xdns / xicmp (finalmask mKCP + ICMP tunnels) | B | Dedicated inbounds, `CAP_NET_RAW` for xicmp, client link/config gen. Schema matched to Xray-core source, not docs. |
| AnyTLS inbound + kTLS offload + TUIC congestion control | B | Shared TLS include (`tls_inbound.pj2`). |
| Hysteria2 (sing-box) | A | Works, DPI-resistant via salamander obfs. |
| **Hysteria (Xray-core native)** | **C** | **Open — see §5.1.** Built this session; config verified correct at every inspectable layer; does not connect from the test client. |
| KCP transport | — | Retired (`e02e494`). |
| Subscription generation (xray JSON / sing-box JSON / share links) | A/B | Many fixes: alpn splitting, pinned-cert cache, allowInsecure→pcs, singbox-only filtering, dns.servers pre-1.12 format hardcoded. |

### 4.2 HAProxy routing
| Feature | State | Notes |
|---|---|---|
| `http_port` exclusivity `!{ ssl_fc }` guard | A | Fixed all-WS/grpc/httpupgrade drop. |
| Stale routing tables after protocol toggle | A | `08d75b7`. |
| tcp+vision REALITY bypass of SNI hop | A | `9201905`. |

### 4.3 Panel / DB / admin
| Feature | State | Notes |
|---|---|---|
| Additive schema reconciler + backup | A | See §2.4. Foreign to older checkouts. |
| Per-domain overrides (transport/security/SNI/host/path/fingerprint/alpn/obfs) | B | Real form, not raw JSON. |
| Outbound chaining / Routing Rules / Inbound Overrides | B | `CustomOutbound`/`CustomRoutingRule` models; read into `current.json`. |
| AmneziaWG-as-Outbound (WARP retirement) | B | Built-in WARP subsystem retired; vendored prebuilt AWG binaries. Parts flagged untested in CHANGES. |
| RBAC (finer admin/agent permissions) | B | |
| Public webhook (user enable/disable events) | B | Field renamed `webhook_secret`→`webhook_signing_key` to dodge the "secret ⇒ must be UUID" rule. |
| Per-domain REALITY fields, HTTP/TLS ports moved off global Settings | A | |
| L2TP/IPsec inbound + outbound (`other/l2tp`) | B | Standalone subsystem, hardened for containerized VPS. |

### 4.4 Install / ops robustness
| Fix | State | Notes |
|---|---|---|
| `reload_all_configs()` atomic + JSON-validate | A | `78c977a`. §2.3. |
| `systemctl kill --kill-who=main` self-kill fix | A | Apply/Reinstall was killing its own script. |
| ACME single stuck domain no longer blocks whole install | A | |
| nginx hardcoded `1.26.*` pin fixed for newer Ubuntu | A | |
| simple-obfs built from source (`-Wno-error`, dropped libpcre3-dev) | A | |
| Drop unused DSA SSH host key gen (fresh-install crash) | A | |

### 4.5 Admin UI
| Item | State | Notes |
|---|---|---|
| "Orbit Admin" dashboard redesign | A | **Live on both `claude/saving-mechanism-bug-yvzifn` and `optimize`** (commit `592957c`, `index_modern.html`, wired in `Dashboard.py`). The `claude/dashboard-modern-redesign` branch name is a stale, fully-subsumed pointer, not the actual location of this work — see §5.5. |
| Settings/Domain/Proxies form redesigns, CSRF fixes | A/B | Duplicate-CSRF-field save bug fixed `f3cd04d`. |

---

## 5. Open work items (executable specs)

### 5.1 Hysteria (Xray-core native) — REMOVED, not fixed  ·  resolved
**Outcome.** The feature (`ProxyProto.hysteria`, "Hysteria (Xray)") was removed entirely rather than
debugged further. Root-caused as far as it could be without upstream access: Xray-core's native
`hysteria` transport has zero obfuscation support (`transport/internet/hysteria/config.proto` has
only `auth`/`udp_idle_timeout`/`masq_*` fields — confirmed against current source, no salamander/obfs
field exists at all). Live testing showed the server-side QUIC handshake genuinely completing
(tcpdump-confirmed bidirectional traffic, correct ServerHello-class responses) while the client-side
handshake never finished, over a network path (Cloudflare WARP) that passes *obfuscated* Hysteria2
(sing-box, same user) without issue. That's consistent with something in that path fingerprinting and
interfering with plain/unobfuscated QUIC specifically — a client-network-path/protocol-capability gap
Xray's implementation has no way to work around (no obfuscation option to fall back to), not a config
bug in this codebase.

**What was removed:** server inbound template (`xray/configs/05_inbounds_07_hysteria.json.j2`,
deleted), client gen (`hutils/proxy/xrayjson.py`'s `add_hysteria_settings`/stream-settings branch,
now excluded via the same skip-list as hysteria2/tuic/etc), `hutils/proxy/xray.py`'s `to_link`
branch, `hutils/proxy/shared.py`'s port/proto handling, ports in `panel/admin/Actions.py` +
`hutils/network/net.py`, the `internal_port_xray_hysteria` Domain property. `init_db.py`'s `_v149`
migration deletes any "Hysteria (Xray)" Proxy rows `_v148` already created on existing installs.
`ConfigEnum.xray_hysteria_port` is left defined but unused/orphaned since `_v148` (historical,
never rewritten) still references the key.

### 5.2 TUIC over the user's network  ·  priority: low  ·  likely won't-fix
**Status.** TUIC fails for this user across ISPs; attributed to unobfuscated-QUIC fingerprinting /
WARP, not a server bug (obfuscated Hysteria2 works on the same network). **Do not spend server-side
effort** unless §5.1 step 1 reveals a shared root cause. Action: fold into the §6 "unobfuscated QUIC"
note; optionally surface a tooltip.

### 5.3 Reconcile the "needs real-server test" backlog  ·  priority: medium
Several CHANGES items are implemented but flagged untested. Field-test each on the real/staging
server and promote B→A or open a fix:
- AmneziaWG-as-Outbound end-to-end (the retirement of built-in WARP).
- `allowInsecure` removal for Xray-core ≥26.2.6 (pinned-cert path) across all share-link types.
- mieru/naive relay routing.
- RBAC permission enforcement on every admin/agent route.
- Public webhook delivery (enable/disable events) against a real receiver.
Each: exercise the real flow, capture evidence, record result in CHANGES, update §4 confidence.

### 5.4 Migration-numbering divergence policy  ·  priority: medium  ·  structural  ·  **DONE (b)**
**Problem.** `claude/saving-mechanism-bug-yvzifn` and `optimize` have different `_vNNN` numbers for
the same conceptual migrations, so cherry-picks that touch migrations conflict and must be
hand-renumbered. This is error-prone and has already bitten (`_v148` on feature = `_v149` on
optimize).
**Change.** Option (b) shipped: `common/check_migrations.py` — an AST-based checker (no import, no
side effects) that fails on a duplicate `_vNNN` function name (Python silently lets the later
definition shadow the earlier one, so the first migration's body becomes permanently dead code for
anyone who already passed that version) or on `MAX_DB_VERSION` being lower than the highest defined
`_vNNN`. The rule to run it before every migration cherry-pick/addition is now written into §3 rule 5
and §7. Verified against both branches at write time: feature branch (90 functions, `MAX_DB_VERSION=148`)
and `optimize` (92 functions, `MAX_DB_VERSION=149`) both pass clean; the duplicate- and
stale-MAX_DB_VERSION-detection paths were each exercised against a synthetic broken file to confirm
they actually fire. Option (a) (re-sequencing one branch to match the other) was **not** done — it's
a larger, riskier one-time migration-history rewrite that wasn't justified just to add a lint check;
revisit only if the divergence keeps causing real friction.
**Done-criteria.** ✅ Written rule in this repo (§3 rule 5, §7) + a verified, working no-duplicate/
no-stale-MAX_DB_VERSION AST checker passing on both branches.

### 5.5 Decide the fate of `claude/dashboard-modern-redesign`  ·  priority: low  ·  **RESOLVED — premise was wrong**
**Investigated, not assumed.** `git merge-base --is-ancestor claude/dashboard-modern-redesign
claude/saving-mechanism-bug-yvzifn` returns true, and `git log claude/saving-mechanism-bug-yvzifn..
claude/dashboard-modern-redesign` is empty: the branch's tip (`f17eec4`) has **zero commits** the
feature branch doesn't already have. It is not "unmerged standalone work" — it's a plain historical
checkpoint ref that was never advanced.

The actual "Orbit Admin" redesign (`index_modern.html`, the design-brief-scoped single-screen
Dashboard rebuild) landed via commit `592957c` directly on the shared history and is **already live**
on both `claude/saving-mechanism-bug-yvzifn` and `optimize` — confirmed by finding it wired into
`Dashboard.py`'s actual render path (`return render_template('index_modern.html', ...)` for the
non-parent-mode case, with `index.html` explicitly kept for parent/child-status mode since the
redesign brief was single-screen-dashboard-only). There is no separate "merge it in" decision to
make; that already happened. §4.5's confidence rating is corrected A→A (was mislabeled B/unmerged).

**Action taken:** corrected §1.2 and §4.5 above to state the true location of this work. **Action
recommended, not taken:** delete the `claude/dashboard-modern-redesign` ref (local + remote) since it
is fully subsumed and its name now actively misleads anyone reading branch history — deleting a
remote ref is the kind of visible, shared-state action this project's operating rules ask to be
confirmed rather than done unilaterally. If you want it gone: `git push origin --delete
claude/dashboard-modern-redesign && git branch -D claude/dashboard-modern-redesign`.
**Done-criteria.** ✅ Investigated and documented. ⬜ Optional cleanup (branch deletion) pending a
go-ahead.

---

## 6. Risk register & known traps

- **`current.json` empty-file cascade** — mitigated (§2.3) but the *class* remains: any new writer of
  a file consumed at Jinja import time must be atomic + validated, and `common/jinja.py`'s
  import-time `json.load()` is still a single point of silent, total failure. Consider (separate
  item) making that import failure loud/fatal instead of silently rendering nothing.
- **Concurrent pushes to `origin/optimize`** — another process lands commits here. Always fetch
  before cherry-picking; never force-push without `--force-with-lease` and a reason.
- **WARP masks test results** — a "server bug" that only reproduces through WARP is probably not a
  server bug. Always confirm network-facing failures with WARP off before touching code.
- **Encoding/mojibake class** — double-UTF-8 `§`→`Â§` has appeared baked into source
  (`singbox.py`). When a tag/string looks wrong, inspect raw bytes, don't trust the terminal render.
- **Schema reconciler crash-loop** — any non-additive model change (enum widen, rename) will
  `sys.exit(1)` the panel until reconciled manually with the panel stopped (§2.4).

---

## 7. Verification & release checklist

**Before every commit:**
- [ ] `python -m py_compile` on every touched `.py`.
- [ ] Jinja `Environment().parse(open(t).read())` on every touched `.j2`/`.pj2`.
- [ ] `bash -n` on every touched shell script.
- [ ] For subscription-gen changes: render for at least one real proxy dict and confirm valid JSON.

**Before shipping a network-facing change:**
- [ ] Exercised on the real/staging server (not assumed).
- [ ] For QUIC/UDP protocols: confirmed with WARP off.
- [ ] Firewall/ports opened where needed (`all_public_ports()` in **both** copies).

**Dual-branch:**
- [ ] Committed + pushed to `claude/saving-mechanism-bug-yvzifn`.
- [ ] `git fetch origin optimize`, cherry-picked, migration numbers checked, re-verified, pushed.
- [ ] If the change touches `init_db.py`: `python3 common/check_migrations.py <path/to/init_db.py>`
      passes (exit 0) on **both** branches after any renumbering — non-zero is a hard blocker.

**PRs:** open as ready-for-review; mirror any repo PR template; subscribe to PR activity and drive CI
to green.

---

## 8. Full component reference (navigate any part of the repo)

A map of the whole project, not just the session-touched files, so an executor can locate anything.

### 8.1 Root orchestration (shell)
| Path | Role |
|---|---|
| `install.sh` | The engine. `main()` branches on `MODE`/`DO_NOT_INSTALL` into full-install vs `apply_configs` vs `apply_users`; runs each subsystem via `install_run <dir> [enable-flag]`. |
| `apply_configs.sh` | Thin wrapper → `DO_NOT_INSTALL=true ./install.sh apply_configs`. |
| `menu.sh` / `status.sh` / `restart.sh` / `uninstall.sh` | Operator CLI, health output, service restart, teardown. |
| `update.sh` | **Do not run** (§3 rule 1) — pulls upstream. |
| `docker-init.sh`, `Dockerfile`, `docker-compose.yml` | Container path. |

### 8.2 `common/` (shared install/render machinery)
| Path | Role |
|---|---|
| `utils.sh` | Shell library: `reload_all_configs()` (atomic, §2.3), `hiddify-http-api()`, `allow_port()`/iptables helpers, service health checks. |
| `jinja.py` | The render engine (§2.3): reads `current.json`, renders every `.j2` via a 4-way process pool. |
| `commander.py` | Maps `Command.*` → shell entrypoints (the panel's hand on the shell). |
| `replace_variables.sh` | Substitutes `current.json`-derived vars into non-Jinja config. |
| `check_migrations.py` | **(new, §5.4)** AST lint for `init_db.py` migration numbering. |
| `install.sh`, `run.sh.j2`, `hiddify_installer.sh`, `package_manager.sh`, `google-bbr.sh`, `sysctl.conf` | Base OS/tooling setup, BBR, sysctl. |
| `packages.lock` / `packages.db` | Pinned versions (e.g. Xray-core v26.6.1). |

### 8.3 Config-render subsystems (each: `install.sh` + `run.sh` + `*.service` + `configs/` or `*.j2`)
| Dir | Role |
|---|---|
| `xray/` | xray-core: `configs/*.j2` inbound/outbound templates (finalmask xdns/xicmp, native hysteria, reality, the `05_inbounds_new.json` vless/vmess/trojan matrix), `pre-start.sh`, service. |
| `singbox/` | sing-box: `configs/*.j2` for hysteria2/tuic/anytls/naive/mieru/ss2022; shared TLS include `common/includes/tls_inbound.pj2`; has a `tests/` suite. |
| `haproxy/` | `:443`/`:80` splitter (§2.2): `haproxy.cfg.j2`, `fronts/`, `backends/`, `maps/`, `iplists/`. |
| `nginx/` | Panel front + CDN/gRPC socket dispatcher (§2.10): `nginx.conf.j2`, `conf.d/{xray,singbox}-base.conf.j2`, `parts/`, real-ip snippets. |
| `acme.sh/` | Cert issuance/renewal: `get_cert.sh`, `prepare_acme.sh`, `generate_self_signed_cert.sh`, `cert_utils.sh`. |

### 8.4 `other/*` subsystems (each gated by an enable-flag in `install.sh`)
`mysql` / `postgres` (DB backend — postgres/timescaledb opt-in via `DB_BACKEND`) · `redis`
(own `hiddify-redis` unit with auth — **not** stock `redis-server`) · `amneziawg` (WARP replacement,
vendored binaries) · `wireguard` · `l2tp` (strongSwan+xl2tpd IPsec) · `dnstt` (DNS tunnel) ·
`ssfaketls` (simple-obfs) · `ssh` · `telegram` (MTProto) · `hiddify-cli` · `v2ray` (legacy, mostly
off) · `docker` · `deprecated/` (removal scripts run early in `main()`).

### 8.5 Panel (`hiddify-panel/src/hiddifypanel/`)
| Area | Contents |
|---|---|
| top-level | `__init__.py`/`base.py`/`base_setup.py` (app factory), `database.py` (**schema reconciler**, §2.4), `Events.py` (hooks incl. webhook), `auth.py`, `cache.py`, `celery.py`. |
| `apps/` | `wsgi_app.py` / `asgi_app.py` / `celery_app*.py` — process entrypoints. |
| `models/` | ORM + enums (§2.5/§2.6). |
| `panel/` | `hiddify.py` (`all_configs_for_cli`), `cli.py`, `init_db.py` (migrations), `run_commander.py`, `hlogger.py`, `usage.py`; `admin/` (flask-admin views), `user/` (subscription/user pages), `common_bp/` (login), `node/` (gRPC node bits). |
| `panel/commercial/` | REST API `restapi/v1` + `restapi/v2/{admin,user,parent,child,panel}`, `telegrambot/`. The v2 admin/user APIs are the programmatic surface; `parent`/`child` power multi-node (§2.9). |
| `hutils/` | Helpers: `proxy/` (sub generation), `network/net.py` (incl. 2nd `all_public_ports`), `node/` (multi-node), `flask.py`, `crypto.py`, `encode.py`, `system.py`, `webhook.py`, `importer/xui.py` (import from x-ui). |
| `drivers/` | Live control plane (§2.8). |
| `static/`, `templates/`, `translations/` | Assets (incl. the AdminLTE plugins), Jinja templates (incl. `admin/templates/index_modern.html` — the Orbit redesign, §5.5), i18n. |

### 8.6 Ops / CI
`operations/` (lxd + oracle deploy helpers), `release/`, `btn-deploy/` (one-click deploy, incl.
`oracle/`), `.github/` workflows (e.g. the AmneziaWG cross-build), `docs/`.

### 8.7 Runtime state (not in git, referenced everywhere)
`/opt/hiddify-manager/current.json` (rendered config source, §2.3) · `/opt/hiddify-manager/ssl/*.crt`
(+`.key`) · `/opt/hiddify-manager/{xray,singbox}/configs/*.json` (rendered outputs) ·
`/run/haproxy-master.sock` (stats/introspection, §2.2) · core control ports (xray 10085, singbox
10086) · panel http-api on `:9000`.
