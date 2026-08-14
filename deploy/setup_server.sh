#!/usr/bin/env bash
# Bootstrap the server. Run once, then again freely — every step is idempotent,
# so re-running after a failure picks up where it left off rather than breaking.
#
#   ssh -i govern.pem ubuntu@107.21.44.130
#   cd /opt/governingai && bash deploy/setup_server.sh
#
# What it does: system packages, a Python 3.11+ interpreter, a virtualenv, the
# requirements, the systemd service, and nginx. It does NOT request a TLS
# certificate — that is a separate step, deliberately, because it fails
# confusingly if DNS has not propagated and is better run on its own.

set -euo pipefail

APP_DIR=/opt/governingai
DOMAIN=app.staging.governingai.us
say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --------------------------------------------------------------- packages

say "Updating package lists"
sudo apt-get update -qq

say "Installing nginx, git and build basics"
sudo apt-get install -y -qq nginx git curl ca-certificates

# The application needs 3.11 or newer. Ubuntu 24.04 ships 3.12 and is fine;
# 22.04 ships 3.10, which is not, so add the PPA only in that case rather than
# unconditionally pulling in a third-party repository.
say "Finding a Python 3.11+ interpreter"
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
            PY=$candidate
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    say "No suitable Python found — adding the deadsnakes PPA for 3.12"
    sudo apt-get install -y -qq software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.12 python3.12-venv
    PY=python3.12
fi
echo "    using $PY ($($PY --version))"

say "Installing the venv module for $PY"
sudo apt-get install -y -qq "${PY}-venv" || sudo apt-get install -y -qq python3-venv

# ----------------------------------------------------------- the app itself

say "Preparing $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown -R ubuntu:ubuntu "$APP_DIR"
cd "$APP_DIR"

say "Creating the virtualenv"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip

say "Installing requirements"
./.venv/bin/pip install --quiet -r requirements.txt
./.venv/bin/python -c "import openpyxl, docx, yaml; print('    dependencies OK')"

say "Checking the app starts and its tests pass"
./.venv/bin/pip install --quiet pytest
./.venv/bin/python -m pytest -q || echo "    (tests reported failures — see above)"

# ------------------------------------------------------------------ service

say "Installing the systemd service"
sudo cp deploy/systemd/governingai.service /etc/systemd/system/governingai.service
sudo systemctl daemon-reload
sudo systemctl enable governingai
sudo systemctl restart governingai
sleep 3
sudo systemctl is-active governingai && echo "    service is running"

say "Checking the app answers on 127.0.0.1:8765"
curl -fsS -o /dev/null -w "    HTTP %{http_code} from the app\n" http://127.0.0.1:8765/ \
  || { echo "    app did not answer — logs follow"; sudo journalctl -u governingai -n 40 --no-pager; exit 1; }

# -------------------------------------------------------------------- nginx

say "Configuring nginx for $DOMAIN"
sudo cp deploy/nginx/governingai.conf /etc/nginx/sites-available/governingai
sudo ln -sf /etc/nginx/sites-available/governingai /etc/nginx/sites-enabled/governingai
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

say "Checking nginx proxies through to the app"
curl -fsS -o /dev/null -w "    HTTP %{http_code} through nginx\n" -H "Host: $DOMAIN" http://127.0.0.1/ \
  || echo "    nginx did not proxy — check /var/log/nginx/governingai.error.log"

cat <<EOF

Done. The app is running behind nginx on port 80.

Next, once http://$DOMAIN loads in a browser:

    bash deploy/enable_tls.sh

Useful afterwards:
    sudo systemctl status governingai        # is it running
    sudo journalctl -u governingai -f        # live logs
    sudo systemctl restart governingai       # after a code change

EOF
