#!/usr/bin/env bash
# Step D: copy the local secrets into the GitHub repo's Actions secrets.
#
#   bash scripts/setup_secrets.sh
#
# Reads ~/.config/job-agent/.env (outside the repo) and the contact-stripped profile from
# `python -m jobagent profile`, then sets each secret with `gh secret set`, feeding the value
# on stdin. Values never appear on screen, in shell history or in command arguments: the
# script prints only "set NAME". It sets nothing if any value is empty.
set -euo pipefail

REPO="ibrahimsaadqureshi/job-agent"
ENV_FILE="${JOBAGENT_HOME:-$HOME/.config/job-agent}/.env"
FROM_ENV=(GEMINI_API_KEY GOOGLE_SERVICE_ACCOUNT_JSON SHEET_ID SLACK_WEBHOOK_URL)

cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi

command -v gh >/dev/null || { echo "error: the GitHub CLI (gh) is not installed" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: run 'gh auth login' first" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "error: $ENV_FILE not found" >&2; exit 1; }

# Print one value from the .env file (parsed the same way the app parses it).
read_env_value() {
  "$PY" -c '
import sys
from dotenv import dotenv_values
sys.stdout.write((dotenv_values(sys.argv[1]).get(sys.argv[2]) or "").strip())
' "$ENV_FILE" "$1"
}

# Read everything first, so a missing value stops the script before anything is set.
# (Plain indexed arrays: macOS ships bash 3.2, which has no associative arrays.)
NAMES=("${FROM_ENV[@]}" CANDIDATE_PROFILE)
VALUES=()
missing=()
for name in "${FROM_ENV[@]}"; do
  VALUES+=("$(read_env_value "$name")")
done
VALUES+=("$("$PY" -m jobagent profile 2>/dev/null || true)")
for i in "${!NAMES[@]}"; do
  [ -n "${VALUES[$i]}" ] || missing+=("${NAMES[$i]}")
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "error: empty, nothing was set: ${missing[*]}" >&2
  exit 1
fi

for i in "${!NAMES[@]}"; do
  printf '%s' "${VALUES[$i]}" | gh secret set "${NAMES[$i]}" --repo "$REPO" >/dev/null
  echo "set ${NAMES[$i]}"
done
unset VALUES
echo "Done. Check the names (never the values) with: gh secret list --repo $REPO"
