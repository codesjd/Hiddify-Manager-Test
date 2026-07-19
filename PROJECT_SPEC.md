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
| `claude/dashboard-modern-redesign` | "Orbit Admin" dashboard redesign | Standalone, **not merged**. Only touches the admin Dashboard page. |

### 1.3 Dual-branch commit workflow (mandatory)
For every change:
1. Commit to `claude/saving-mechanism-bug-yvzifn`, verify (§7), push with retry/backoff.
2. In the `optimize` worktree: `git fetch origin optimize`, cherry-pick the commit, re-verify, push.
3. **Migration numbers are NOT portable between branches** (see §3.5). If the cherry-pick touches
   `init_db.py`/`config_enum.py`, expect a conflict and renumber for the destination branch.

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
- `models/` — SQLAlchemy models, `config_enum.py`, `domain.py`, `proxy.py`, migrations in
  `panel/init_db.py`.
- `hutils/proxy/` — subscription/config generation: `shared.py` (per-proxy dict builder + `get_port`),
  `xrayjson.py` (full Xray JSON sub), `singbox.py` (sing-box JSON sub), `xray.py` (share links).
- `panel/admin/` — flask-admin views (`DomainAdmin`, `Actions`, `OutboundAdmin`, etc).
- Note: **`all_public_ports()` is implemented twice** — `panel/admin/Actions.py` and
  `hutils/network/net.py`. Keep them in sync (drift bug fixed `c7b4ecb`).

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
| "Orbit Admin" dashboard redesign | B | On `claude/dashboard-modern-redesign`, **unmerged**, Dashboard page only. |
| Settings/Domain/Proxies form redesigns, CSRF fixes | A/B | Duplicate-CSRF-field save bug fixed `f3cd04d`. |

---

## 5. Open work items (executable specs)

### 5.1 Hysteria (Xray-core native) — get it connecting  ·  priority: high  ·  confidence the *code* is correct: high
**Problem.** The new `ProxyProto.hysteria` proxy renders correct server + client config, the UDP port
listens, the QUIC handshake completes (verified by decrypting captured Initial packets — valid
ServerHello, real ACKs both directions), but the client never establishes a usable session; it
retransmits its Initial and then restarts with a fresh connection.

**What is already verified correct (do not re-litigate):**
- Inbound `settings.users[]` JSON exactly matches Xray-core `infra/conf/hysteria.go`
  (`HysteriaUserConfig{auth,level,email}` → `HysteriaServerConfig.Build()`).
- TLS cert/key valid, not expired, cryptographically matched (EC key, verified via `openssl pkey`).
- Client `hysteriaSettings.auth` is the field `dialer.go` reads and sends.
- Auth is an **HTTP/3 POST** to a fixed masquerade URL *after* the QUIC handshake; on failure the
  server returns a generic 404 (anti-probe) and **logs nothing** on either path (confirmed in
  `hub.go::AuthHTTP`). So the total log silence is expected, not a misconfig.

**Two live hypotheses, not yet separated:**
1. Cloudflare WARP on the test client interfering with unobfuscated QUIC (same signature as TUIC,
   which also fails for this user over WARP while obfuscated Hysteria2 succeeds).
2. Immaturity/bug in Xray-core's brand-new native `hysteria` implementation.

**Executable steps (in order):**
1. **Isolate WARP.** Test the Hysteria (Xray) profile from a client with WARP fully off, on a network
   that is not otherwise filtering QUIC. If it connects → not our bug; document as
   "incompatible with WARP/QUIC-filtered networks" (§6) and mark the feature A-with-caveat. **Stop
   here if it works.**
2. **If it still fails with WARP off:** build a patched Xray-core to get visibility. `QLOGDIR` and
   `SSLKEYLOGFILE` are **not** honored by Xray's hysteria code (verified — not wired in), so log
   hooks won't help; you must add temporary `errors.LogInfo` statements to `hub.go::AuthHTTP`
   (log `auth` header received, validator hit/miss, chosen congestion branch) and `dialer.go`
   RoundTrip result, then `go build` and swap the binary on a staging box.
3. From the patched-binary logs, determine whether: (a) the HTTP/3 POST arrives at all, (b) the
   `auth` string the server receives equals the user UUID the client sent, (c) `validator.Get(auth)`
   returns the user. Fix whichever link is broken.
4. Cross-check congestion config: client sends `CommonHeaderCCRX` (BrutalDown); server picks BBR vs
   Brutal from it. A `0`/mismatch here won't fail auth but can wedge throughput — confirm it after
   auth succeeds.

**Files.** Server template `xray/configs/05_inbounds_07_hysteria.json.j2`; client gen
`hutils/proxy/xrayjson.py` (`add_hysteria_settings`, `add_stream_settings` hysteria branch),
`hutils/proxy/xray.py` (`to_link` hysteria branch), `hutils/proxy/shared.py` (`get_port`,
`get_valid_proxies`, `make_proxy`); ports in `panel/admin/Actions.py` + `hutils/network/net.py`;
migration/enum in `init_db.py` + `config_enum.py`.

**Done-criteria.** A real client (WARP off) connects through the Hysteria (Xray) profile and passes
traffic, OR the failure is conclusively attributed to WARP/network with the code confirmed correct
and the feature documented as best-effort in the admin UI.

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

### 5.4 Migration-numbering divergence policy  ·  priority: medium  ·  structural
**Problem.** `claude/saving-mechanism-bug-yvzifn` and `optimize` have different `_vNNN` numbers for
the same conceptual migrations, so cherry-picks that touch migrations conflict and must be
hand-renumbered. This is error-prone and has already bitten (`_v148` on feature = `_v149` on
optimize).
**Change (choose one, document it):** either (a) adopt a single source-of-truth ordering and
re-sequence one branch once to match, or (b) codify a checklist step: before any migration
cherry-pick, read destination `MAX_DB_VERSION` + AST-scan for duplicate `_vN` names, renumber, then
continue. Until (a) happens, (b) is mandatory.
**Done-criteria.** A written, followed rule in this repo (extend §3.5) plus, if (a), a verified
no-duplicate `_vN` AST check passing on both branches.

### 5.5 Decide the fate of `claude/dashboard-modern-redesign`  ·  priority: low
It's an unmerged, Dashboard-only redesign. Decide: merge into the feature branch (and re-test the
Dashboard render + admin nav), keep as an opt-in, or retire. No code work until that call is made.

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

**PRs:** open as ready-for-review; mirror any repo PR template; subscribe to PR activity and drive CI
to green.
