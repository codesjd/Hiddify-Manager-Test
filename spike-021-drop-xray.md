# Spike 021 - Drop Xray Core Analysis

## Goal
Determine the exact delta of xray-exclusive features lost if Xray is completely removed and replaced by Singbox.

## Findings

1. **Protocols and Transports:**
   - **xHTTP:** The only feature explicitly locked to `xray` core. 
     - Checked `core_type == "xray"` and `transport == "xhttp"`.
     - Code explicitly says: `xhttp is xray-specific; singbox has no xhttp inbound`.
     - `ProxyTransport.xhttp` and `DomainType.special_reality_xhttp` are used to filter/generate configs for xHTTP.
   - **Reality:** Singbox fully supports reality. Xray has some edge cases (e.g. `special_reality_xhttp` which is just xHTTP over Reality).
   - **AmneziaWG, L2TP, Hysteria, Naive, TUIC, Mieru:** Neither core dials AmneziaWG/L2TP natively, handled by `freedom` outbounds binding to interfaces. Singbox handles Hysteria, Naive, TUIC, Mieru natively. Xray generates `blackhole` for these. Thus, Singbox is *more* capable here.

2. **Flow Control:**
   - Xray uses `XTLS` flow control (e.g., `xtls-rprx-vision`). Singbox fully supports `xtls-rprx-vision` on VLESS/Reality. No capability delta found here.

3. **`to_xray_dict` usage:**
   - Evaluated `hiddify-panel/src/hiddifypanel/models/routing.py`.
   - `to_xray_dict` and `to_singbox_dict` handle custom routing outbounds and rules.
   - Removing `to_xray_dict` allows collapsing the dual-core serialization path.

## Capability Delta
The **ONLY** capability lost is the **xHTTP transport** (`xhttp` network type in proxies, and `xhttp_enable` / `path_xhttp` configurations).

## Existing Install Migration Story
Users with `xhttp` proxies / domains will lose connectivity on those specific links.
- **Migration Path:** 
  1. Deprecate `xhttp_enable` config.
  2. For existing domains with `special_reality_xhttp` mode, migrate them to `reality` or `special_reality_tcp` (or notify admin to migrate).
  3. For proxies using `transport="xhttp"`, these are auto-generated based on `xhttp_enable` and `special_reality_xhttp` domains. Disabling the config stops generation.

## Conclusion
The engineering delta is exactly as stated in the plan: **xHTTP is the only loss**. If the product accepts this loss, we can proceed to Phase 2 (removal).
