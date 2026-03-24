#!/bin/bash
# Run this any time you've updated annotation positions or uploaded new diagrams.
# It commits any changed coord files, new diagram images, and the library index,
# then pushes to GitHub so Render redeploys automatically.

cd "$(dirname "$0")"

# Rebuild the diagram library so newly-uploaded images are registered
python3 -c "
import sys
sys.path.insert(0, '.')
from utils.diagram_library import build_library_from_source
build_library_from_source()
print('Library rebuilt.')
" 2>&1

# Collect everything that changed or is new
CHANGED=$(
  git diff --name-only config/ diagrams/Uploaded/ && \
  git ls-files --others --exclude-standard config/ diagrams/Uploaded/
)

if [ -z "$CHANGED" ]; then
  echo "No changes to push."
  exit 0
fi

echo "Changed files:"
echo "$CHANGED"
echo ""

git add config/ diagrams/
git commit -m "Update annotation positions and diagrams"
git push

# Trigger Render deploy via deploy hook URL (set RENDER_DEPLOY_HOOK_URL env var in Render dashboard)
if [ -n "$RENDER_DEPLOY_HOOK_URL" ]; then
  echo "Triggering Render deploy hook..."
  curl -s -X POST "$RENDER_DEPLOY_HOOK_URL" > /dev/null && echo "Deploy triggered." || echo "Deploy hook call failed."
fi

echo ""
echo "Done — Render will redeploy shortly."
