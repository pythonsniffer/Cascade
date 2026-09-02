#!/usr/bin/env bash
# Publish Cascade to a Hugging Face Space (Docker SDK).
#
#   ./deploy/huggingface/push_to_space.sh <hf-username> [space-name]
#
# Prerequisites:
#   pip install -U "huggingface_hub[cli]"
#   hf auth login          # a token with WRITE scope
#
# Creates the Space if it does not exist, then pushes this repo to it. The Space's
# README.md must carry the YAML card at deploy/huggingface/README.md, so this script
# swaps it into place on the pushed branch only — your GitHub README is untouched.

set -euo pipefail
cd "$(dirname "$0")/../.."

USER="${1:?usage: push_to_space.sh <hf-username> [space-name]}"
SPACE="${2:-cascade-digital-twin}"
REMOTE="https://huggingface.co/spaces/$USER/$SPACE"

command -v hf >/dev/null 2>&1 || { echo "install the HF CLI: pip install -U 'huggingface_hub[cli]'"; exit 1; }

echo "==> ensuring the Space exists: $USER/$SPACE"
hf repo create "$USER/$SPACE" --repo-type space --space_sdk docker -y 2>/dev/null \
  || echo "    (already exists — continuing)"

echo "==> preparing a detached branch with the Space card as README.md"
BRANCH="hf-space-$(date +%s)"
git checkout -q -b "$BRANCH"
cp deploy/huggingface/README.md README.md
git add README.md
git -c user.email=noreply@example.com -c user.name="space-deploy" \
    commit -q -m "Space card" || true

echo "==> pushing to $REMOTE"
echo "    (the 170 MB of sample frames make this slow the first time)"
git push --force "$REMOTE" "$BRANCH:main"

git checkout -q -
git branch -D "$BRANCH" >/dev/null

cat <<EOF

  Pushed. The Space is building at:
    $REMOTE

  First build takes 10-25 minutes — it installs torch and ultralytics.
  Watch the Logs tab. When it is done the dashboard is at:
    https://$USER-$SPACE.hf.space

EOF
