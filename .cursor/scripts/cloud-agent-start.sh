#!/usr/bin/env bash
set -euo pipefail

if ! redis-cli ping >/dev/null 2>&1; then
  redis-server --daemonize yes
fi

mkdir -p /opt/hiddify-manager/log/system /opt/hiddify-manager/hiddify-panel

if ! redis-cli ping >/dev/null 2>&1; then
  echo "Redis failed to start" >&2
  exit 1
fi
