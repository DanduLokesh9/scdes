#!/usr/bin/env bash
# What does AWS itself say about our mail sending?
#
# The client's verification code was appearing on screen instead of arriving
# by email. SES's own SMTP rejection said why — "Email address is not
# verified ... in region US-EAST-1" — which is the sandbox. This asks the SES
# API the same question directly, so the answer is AWS's rather than an
# inference from one error message.
#
# Needs credentials that can call the SES API. The SMTP credentials cannot:
# an SES SMTP password is derived from an IAM secret by HMAC and is not
# reversible, so it sends mail and nothing else. An instance role, or a real
# IAM key pair, is what this looks for.
#
# Read-only. It asks and reports; it changes nothing and sends nothing.

set -uo pipefail
REGION="${AWS_REGION:-us-east-1}"

say() { printf '\n=== %s\n' "$1"; }

say "is the aws cli here"
if command -v aws >/dev/null 2>&1; then
  aws --version 2>&1
else
  echo "not installed"
fi

say "does this box have credentials of its own"
TOKEN=$(curl -s -X PUT 'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' --max-time 3 || true)
ROLE=$(curl -s -H "X-aws-ec2-metadata-token: ${TOKEN}" --max-time 3 \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/ || true)
if [ -n "${ROLE}" ]; then
  echo "instance role: ${ROLE}"
else
  echo "no instance role attached"
fi
for d in "$HOME/.aws" /root/.aws; do
  if sudo test -d "$d"; then
    echo "credential dir ${d}:"
    sudo ls -a "$d"
  fi
done

if ! command -v aws >/dev/null 2>&1; then
  echo; echo "Cannot query the SES API without the cli. Stopping."
  exit 0
fi

say "who am I, as far as AWS is concerned"
aws sts get-caller-identity --output table 2>&1 | head -12 || true

say "the account's sending status"
# The one field that answers the question: ProductionAccessEnabled.
aws sesv2 get-account --region "${REGION}" \
  --query '{ProductionAccess:ProductionAccessEnabled,SendingEnabled:SendingEnabled,Enforcement:EnforcementStatus,Max24Hour:SendQuota.Max24HourSend,SentLast24Hour:SendQuota.SentLast24Hours,MaxPerSecond:SendQuota.MaxSendRate}' \
  --output table 2>&1 | head -20 || true

say "which identities are verified"
aws sesv2 list-email-identities --region "${REGION}" \
  --query 'EmailIdentities[].{Identity:IdentityName,Type:IdentityType,Verified:VerifiedForSendingStatus}' \
  --output table 2>&1 | head -30 || true

say "dkim and spf on the sending domain"
aws sesv2 get-email-identity --region "${REGION}" \
  --email-identity governingai.us \
  --query '{Verified:VerifiedForSendingStatus,DkimStatus:DkimAttributes.Status,DkimSigning:DkimAttributes.SigningEnabled,MailFrom:MailFromAttributes.MailFromDomain,MailFromStatus:MailFromAttributes.MailFromDomainStatus}' \
  --output table 2>&1 | head -20 || true

say "anything suppressed"
aws sesv2 list-suppressed-destinations --region "${REGION}" \
  --query 'SuppressedDestinationSummaries[].{Address:EmailAddress,Reason:Reason}' \
  --output table 2>&1 | head -20 || true
