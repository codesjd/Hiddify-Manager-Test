# Spike: Nginx Responsibilities and HAProxy Replacements

## Nginx Responsibilities Map

Nginx is currently used to terminate/route various traffic paths. Below are its exact responsibilities and their alternative owners if Nginx were to be removed.

### 1. ACME HTTP-01 Challenges
*   **Current:** Nginx serves `/.well-known/acme-challenge/` for certbot/acme.sh out of `/opt/hiddify-manager/acme.sh/www/`.
*   **Owner:** Currently handled via `start_nginx_acme()` modifying `nginx/parts/acme.conf` before getting certs.
*   **Alternative:** HAProxy can handle this natively. We can define an HAProxy backend mapped to a local HTTP server (like python's `http.server` started by acme.sh scripts or even served by Hiddify-panel directly if it exposes a route), or HAProxy can return a static file (less ideal) or we keep a tiny python server for the duration of the ACME run. The panel itself `hiddifypanel` is another candidate.

### 2. Decoy / Fake Site
*   **Current:** If a request comes in that doesn't match proxy paths, Nginx proxies it to a configured `decoy_domain` via `nginx/parts/def-link.conf.j2`. It acts as a reverse proxy for the decoy domain.
*   **Alternative:** HAProxy can do this natively via `server decoy_server ${decoy_domain}:443 ssl verify none` or similar in a default backend if it's not a local static site. In fact, HAProxy already does this for `ssdecoy_http` and `tgdecoy_http`.

### 3. Static Assets serving for Panel
*   **Current:** Nginx serves static assets for the panel (`/opt/hiddify-manager/.venv313/bin/python .../static`) via `nginx/parts/proxy_to_static.conf.j2`.
*   **Alternative:** The panel (Flask/Gunicorn) is completely capable of serving its own static assets (e.g., using `send_from_directory`), or if it's behind HAProxy, Gunicorn/Uvicorn handles the static files.

### 4. Hiddify Panel Proxy
*   **Current:** Nginx proxies requests to the python panel backend at `http://localhost:9000`.
*   **Alternative:** HAProxy already defines a `backend hiddifypanel` that points to `127.0.0.1:9000`. Nginx is just sitting in the middle or beside it unnecessarily for panel traffic.

### 5. Proxy-Stats UI & API
*   **Current:** Nginx proxies `/proxy_path_admin/proxy-stats/` to `http://localhost:16756/`.
*   **Alternative:** HAProxy already defines `proxy_stats_ui_backend` and `proxy_stats_api_backend` pointing to `127.0.0.1:16756`.

### 6. Xray/Singbox Routing (gRPC, TCP, WS, xhttp)
*   **Current:** Nginx proxies certain paths (like `path_grpc`, `path_tcp`, `path_ws`, `path_xhttp`) to unix sockets or local ports belonging to Xray/Singbox. It terminates HTTP/2 or HTTP/1.1 and passes to Xray.
*   **Alternative:** HAProxy can route based on paths to those unix sockets or ports. HAProxy already routes to Xray/Singbox for many things. For HTTP-based transport (WS, gRPC), HAProxy can route directly to the backend. Xray/Singbox can terminate their own transports.

### 7. Github Raw / Object Proxying
*   **Current:** Nginx proxies `/ghr/`, `/gho/`, `/gh/` to github.com and raw.githubusercontent.com for client proxying/speedups.
*   **Alternative:** HAProxy can act as a reverse proxy for these github endpoints just as easily.

### 8. Short-link redirect
*   **Current:** Nginx returns `307` redirects for short links (e.g. `nginx/parts/short-link.conf`).
*   **Alternative:** HAProxy can issue HTTP redirects directly via `http-request redirect location ...`.

## Escalation: Unknowns or Missing Alternatives
There are no outright "impossible" replacements, but there are complex ones:

1.  **Xray/Singbox HTTP/2 & gRPC termination:** Nginx currently listens on `h2.sock` (HTTP/2) and routes gRPC calls directly to Xray `grpc_pass 127.0.0.1:2023`. HAProxy *can* route gRPC and HTTP/2, but we need to ensure the HAProxy configuration perfectly mirrors the Nginx gRPC routing without breaking compatibility.
2.  **ACME Challenge:** Nginx dynamically creates a location block during `get_cert`. If we drop Nginx, HAProxy needs a way to route `/.well-known/acme-challenge/` to a temporary server that the `acme.sh` script spins up, or the Panel needs to serve it. This is a subtle ACME path that must be bulletproof to avoid silent cert renewal failures weeks later.

## Conclusion
A clean replacement is entirely feasible. The core engine (HAProxy) and the Panel can absorb all Nginx responsibilities. However, due to the Escalate conditions on ACME and complex proxying, removing Nginx requires careful re-implementation of the ACME HTTP-01 challenge routing and Xray HTTP/2 transport routing inside HAProxy.