#!/bin/bash
# Run this any time you've updated annotation positions in the dashboard.
# It commits any changed coord files and pushes to Render automatically.

cd "$(dirname "$0")"

CHANGED=$(git diff --name-only config/annotation_coords/ && git ls-files --others --exclude-standard config/annotation_coords/)

if [ -z "$CHANGED" ]; then
  echo "No coord changes to push."
  exit 0
fi

echo "Changed files:"
echo "$CHANGED"
echo ""

git add config/annotation_coords/
git commit -m "Update annotation positions"
git push

echo ""
echo "Done — Render will redeploy in ~1 minute."
