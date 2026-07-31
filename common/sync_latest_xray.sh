#!/bin/bash
# Resolves the latest XTLS/Xray-core release from GitHub and pins it into
# packages.lock via package_manager.sh's add_package (which downloads the
# real asset and computes its real sha256 - nothing here is a hardcoded
# hash). Safe to re-run: add_package() is idempotent for a version already
# in packages.lock (it re-verifies/rewrites the same line), and every
# failure path here just leaves packages.lock untouched instead of
# breaking install.sh's caller.
#
# Intended to run periodically (e.g. a daily cron alongside acme.sh's own
# renewal cron - see common/run.sh.j2) so packages.lock's xray entry stays
# current without an admin hand-editing it. install.sh itself does NOT
# call this automatically: a fresh install/apply should never depend on
# GitHub's API being reachable or rate-limit-friendly at that exact
# moment - it always has a working pinned version already in
# packages.lock regardless of whether this script has ever run.
SCRIPT_DIR="$(realpath "$(dirname "$BASH_SOURCE")")"
if [[ "$SCRIPT_DIR" != *develop* ]]; then
    SCRIPT_DIR="/opt/hiddify-manager/common"
fi
source "$SCRIPT_DIR/package_manager.sh"

latest_json=$(curl -sL --connect-timeout 5 "https://api.github.com/repos/XTLS/Xray-core/releases/latest")
if [[ -z "$latest_json" ]]; then
    error "sync_latest_xray: could not reach GitHub API, leaving packages.lock unchanged"
    exit 1
fi

# tag_name looks like "v26.6.27" - strip the leading v to match the bare
# version numbers already used throughout packages.lock (e.g. "26.6.1").
tag=$(echo "$latest_json" | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"v?([^"]+)".*/\1/')
if [[ -z "$tag" ]]; then
    error "sync_latest_xray: could not parse tag_name from GitHub API response"
    exit 1
fi

current=$(get_latest_version xray amd64)
if [[ "$tag" == "$current" ]]; then
    echo "sync_latest_xray: already on latest ($tag)"
    exit 0
fi

echo "sync_latest_xray: pinning xray $tag (was $current)"
add_package xray "$tag" amd64 "https://github.com/XTLS/Xray-core/releases/download/v${tag}/Xray-linux-64.zip"
add_package xray "$tag" arm64 "https://github.com/XTLS/Xray-core/releases/download/v${tag}/Xray-linux-arm64-v8a.zip"
