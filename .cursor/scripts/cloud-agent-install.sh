#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3.12-venv \
  python3.12-dev \
  build-essential \
  libev-dev \
  libmysqlclient-dev \
  libpq-dev \
  redis-server

sudo mkdir -p /opt/hiddify-manager/log/system /opt/hiddify-manager/hiddify-panel
sudo chown -R "$(whoami):$(whoami)" /opt/hiddify-manager

if [[ ! -f /opt/hiddify-manager/hiddify-panel/app.cfg ]]; then
  cat > /opt/hiddify-manager/hiddify-panel/app.cfg <<'EOF'
STDOUT_LOG_LEVEL=INFO
HIDDIFY_CONFIG_PATH=/opt/hiddify-manager/
SECRET_KEY=dev-secret-key-change-me
DEBUG=True
RUN_HOST=0.0.0.0
RUN_PORT=9000
DB_VERSION=0
SQLALCHEMY_DATABASE_URI=sqlite:////opt/hiddify-manager/hiddify-panel/hiddifypanel.db
REDIS_URI_MAIN=redis://127.0.0.1:6379/0
REDIS_URI_SSH=redis://127.0.0.1:6379/1
REDIS_URI_SSE=redis://127.0.0.1:6379/2
EOF
fi

cd hiddify-panel/src
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -U pip setuptools wheel
.venv/bin/pip install -e '.[dev]'

export HIDDIFY_CFG_PATH=/opt/hiddify-manager/hiddify-panel/app.cfg
if [[ ! -f /opt/hiddify-manager/hiddify-panel/hiddifypanel.db ]]; then
  .venv/bin/hiddifypanel init-db
fi
