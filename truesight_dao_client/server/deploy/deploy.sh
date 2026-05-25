#!/usr/bin/env bash
# Deploy the dao_protocol FastAPI service to the Edgar app box (seni_ror_new).
#
# Topology (see agentic_ai_context/EDGAR_DAO_EXTRACTION_PLAN.md):
#   krake_ng      — nginx reverse proxy (SEPARATE box, SSH :2202); fronts edgar.truesight.me
#   seni_ror_new  — Edgar Rails app box; this service runs here on :8010 (systemd unit
#                   truesight-dao-protocol), alongside Rails on :3002
#
# First-time setup on seni_ror_new (run once, manually):
#   git clone https://github.com/TrueSightDAO/dao_protocol.git /home/ubuntu/dao_protocol
#   cd /home/ubuntu/dao_protocol && python3 -m venv .venv
#   sudo cp truesight_dao_client/server/deploy/truesight-dao-protocol.service /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable truesight-dao-protocol
#   # then run this script for the install + start
#
# Usage:
#   ./deploy.sh                 # git pull + pip install + restart
#   SSH_HOST=seni_ror_new ./deploy.sh
#
# The nginx location flip on krake_ng is a SEPARATE, manual step (sensitive,
# shared proxy) — not done here. See the plan doc.

set -euo pipefail

SSH_HOST=${SSH_HOST:-seni_ror_new}
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
  ./.venv/bin/pip install -e '.[server]'"

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
