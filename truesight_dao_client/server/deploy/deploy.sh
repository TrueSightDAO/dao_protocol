#!/usr/bin/env bash
# Deploy the dao_protocol FastAPI service to the standalone NELANCO box
# (dao_protocol_nelanco).
#
# Topology (since 2026-05-28 NELANCO cutover; see
# sentiment_importer/NELANCO_ARCHITECTURE.md):
#   seni_ror              — Edgar Rails app box (NELANCO 54.211.179.126); its
#                            nginx proxies /proxy/gas/* across the VPC to:
#   dao_protocol_nelanco  — standalone NELANCO box (98.93.94.86) running this
#                            service on :8010 (systemd unit
#                            truesight-dao-protocol). Private IP 172.31.23.207
#                            is what seni_ror's nginx points at — same VPC,
#                            same SG, default self-ingress allows :8010.
#
# History: before 2026-05-28 this service was co-hosted with Rails on EXPLORYA
# `seni_ror_new` (3.90.179.151, now stopped) via 127.0.0.1:8010 upstream.
# The cutover split it onto its own box so the cost lands on NELANCO.
#
# First-time setup on dao_protocol_nelanco (run once, manually):
#   git clone https://github.com/TrueSightDAO/dao_protocol.git /home/ubuntu/dao_protocol
#   cd /home/ubuntu/dao_protocol && python3 -m venv .venv
#   sudo cp truesight_dao_client/server/deploy/truesight-dao-protocol.service /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable truesight-dao-protocol
#   # then run this script for the install + start
#
# Usage:
#   ./deploy.sh                          # git pull + pip install + restart
#   SSH_HOST=dao_protocol_nelanco ./deploy.sh
#
# The nginx upstream block on seni_ror (edgar.truesight.me's web tier) is a
# separate, manual step — not done here. The block lives at
# /etc/nginx/sites-available/edgar.conf and proxies /proxy/gas/* to
# 172.31.23.207:8010 across the VPC.

set -euo pipefail

SSH_HOST=${SSH_HOST:-dao_protocol_nelanco}
APP_DIR=${APP_DIR:-/home/ubuntu/dao_protocol}
UNIT=truesight-dao-protocol
PORT=${PORT:-8010}

log() { printf '\n\033[1;36m[deploy %s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
run() { ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=10 "$SSH_HOST" "$@"; }

log "$SSH_HOST: git pull + install (.venv, editable, [server] extra)"
run "set -euo pipefail
  cd $APP_DIR
  git checkout main
  git pull --ff-only origin main
  [ -d .venv ] || python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -e . -r requirements-server.txt"

log "$SSH_HOST: restart $UNIT"
run "sudo systemctl restart $UNIT"

log "$SSH_HOST: wait for port $PORT"
run "for i in \$(seq 1 30); do
    (echo > /dev/tcp/127.0.0.1/$PORT) >/dev/null 2>&1 && { echo '  up'; exit 0; }
    sleep 2
  done
  echo '  $UNIT did not open port $PORT within 60s' >&2
  sudo systemctl status $UNIT --no-pager | tail -30 >&2
  exit 1"

log "$SSH_HOST: local health check"
run "curl -fsS http://127.0.0.1:$PORT/healthz && echo"

log "deploy complete (remember: the krake_ng nginx location flip is a separate manual step)"
