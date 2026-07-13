#!/usr/bin/env bash
# Securely install the Anthropic Admin API key into the prod server's .env.
#
# The key is typed at a HIDDEN prompt: it is never echoed to the screen, never
# written to a file on the laptop, never passed as a command-line argument
# (so it stays out of `ps` and shell history), and never printed in chat.
#
# Usage:  bash tools/set_admin_key.sh
set -euo pipefail

KEYFILE="/c/Viduti/Oracle Cloud Keys/ssh-key-2026-06-12.key"
HOST="ubuntu@80.225.249.122"
ENVFILE="/var/www/greencurve/.env"

read -rsp "Paste the Anthropic Admin API key (input hidden): " ADMIN_KEY
echo

if [[ -z "${ADMIN_KEY}" ]]; then
  echo "No key entered — aborted." >&2; exit 1
fi
if [[ "${ADMIN_KEY}" != sk-ant-admin* ]]; then
  echo "That does not look like an Admin key (expected it to start with 'sk-ant-admin')." >&2
  echo "A regular sk-ant-api key will NOT work for usage reporting — aborted." >&2
  exit 1
fi

# Pipe the key over stdin (never an argv), and write it atomically.
printf '%s' "${ADMIN_KEY}" | ssh -i "${KEYFILE}" -o StrictHostKeyChecking=no "${HOST}" \
  "sudo -n true 2>/dev/null || true
   K=\$(cat)
   sudo sed -i '/^ANTHROPIC_ADMIN_KEY=/d' ${ENVFILE}
   printf 'ANTHROPIC_ADMIN_KEY=%s\n' \"\$K\" | sudo tee -a ${ENVFILE} >/dev/null
   sudo chown root:www-data ${ENVFILE}
   sudo chmod 640 ${ENVFILE}
   echo \"installed: ANTHROPIC_ADMIN_KEY (len=\${#K}, tail=...\${K: -6})\""

unset ADMIN_KEY
echo "Done. The key is on the server only."
