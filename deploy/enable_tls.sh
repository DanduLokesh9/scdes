#!/usr/bin/env bash
# Request a free Let's Encrypt certificate and switch the site to HTTPS.
#
# Run this only after http://app.staging.governingai.us loads in a browser.
# Certbot proves you control the name by answering a challenge on port 80 at
# that exact hostname — if DNS has not propagated, or port 80 is closed, it
# fails with a message that does not obviously say so.

set -euo pipefail

# Staging unless told otherwise. Production: DOMAIN=app.governingai.us bash deploy/enable_tls.sh you@iiac.ai
DOMAIN="${DOMAIN:-app.staging.governingai.us}"
EMAIL="${1:-}"

if [ -z "$EMAIL" ]; then
    echo "Usage: bash deploy/enable_tls.sh you@yourdomain.com"
    echo "  Let's Encrypt uses the address only to warn you before a"
    echo "  certificate expires. Certificates renew automatically."
    exit 1
fi

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

say "Checking this host is the one $DOMAIN points at"
resolved=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
mine=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]' || true)
echo "    $DOMAIN -> ${resolved:-nothing}"
echo "    this server -> ${mine:-unknown}"
if [ -n "$resolved" ] && [ -n "$mine" ] && [ "$resolved" != "$mine" ]; then
    echo
    echo "    They do not match. Certbot will fail. Wait for DNS to propagate"
    echo "    (the record's TTL is 600s) and run this again."
    exit 1
fi

say "Installing Certbot"
sudo apt-get update -qq
sudo apt-get install -y -qq certbot python3-certbot-nginx

say "Requesting the certificate"
# --nginx edits the site config in place: adds the 443 server block, points it
# at the new certificate, and sets up the HTTP redirect.
sudo certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --redirect

say "Confirming renewal is armed"
# Certbot installs a systemd timer. A dry run proves renewal will actually work
# in 60 days rather than discovering it does not on the day it matters.
systemctl list-timers 'certbot*' --no-pager || true
sudo certbot renew --dry-run

say "Checking HTTPS end to end"
curl -fsS -o /dev/null -w "    HTTP %{http_code} over TLS\n" "https://$DOMAIN/"
curl -fsS -o /dev/null -w "    HTTP %{http_code} on plain HTTP (301 = redirecting)\n" \
     "http://$DOMAIN/" || true

cat <<EOF

Done. https://$DOMAIN is live and will renew itself.

EOF
