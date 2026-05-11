#!/bin/bash
# Run this any time you've updated annotation positions or uploaded new diagrams.
# It commits any changed coord files, new diagram images, and the library index,
# then pushes to GitHub so Render redeploys automatically.

cd "$(dirname "$0")"

# If GIT_TOKEN is set (Render env var), configure the remote URL to include it
# so that git push works from the server without interactive credentials.
if [ -n "$GIT_TOKEN" ]; then
  REPO_URL=$(git remote get-url origin)
  # Strip any existing credentials from the URL
  REPO_URL=$(echo "$REPO_URL" | sed 's|https://[^@]*@|https://|')
  # Inject the token
  AUTH_URL=$(echo "$REPO_URL" | sed "s|https://|https://x-token-auth:${GIT_TOKEN}@|")
  git remote set-url origin "$AUTH_URL"
fi

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

# Find the main worktree. The server may be running from a Claude worktree
# (a side branch), but Render only deploys from main. If we detect that the
# current directory is not the main-branch worktree, copy the changed files
# there and push from there instead.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
MAIN_WORKTREE=$(git worktree list --porcelain 2>/dev/null | awk '
/^worktree / { wt=$2 }
/^branch refs\/heads\/main$/ { print wt; exit }
')

if [ -n "$MAIN_WORKTREE" ] && [ "$MAIN_WORKTREE" != "$(pwd)" ]; then
  echo "Server is running from a worktree branch ($CURRENT_BRANCH)."
  echo "Syncing changed files to main worktree: $MAIN_WORKTREE"
  for f in $CHANGED; do
    dir=$(dirname "$MAIN_WORKTREE/$f")
    mkdir -p "$dir"
    cp "$f" "$MAIN_WORKTREE/$f"
    echo "  copied $f"
  done
  cd "$MAIN_WORKTREE"
  echo "Now pushing from main worktree..."
fi

git add config/ diagrams/
git commit -m "Update annotation positions and diagrams"

# Pull any remote changes first so we don't get rejected for being behind
git pull --rebase origin main 2>&1 || {
  echo "Pull/rebase failed — resolve conflicts manually and re-run."
  exit 1
}

git push

# Trigger Render deploy via deploy hook URL (set RENDER_DEPLOY_HOOK_URL env var in Render dashboard)
if [ -n "$RENDER_DEPLOY_HOOK_URL" ]; then
  echo "Triggering Render deploy hook..."
  curl -s -X POST "$RENDER_DEPLOY_HOOK_URL" > /dev/null && echo "Deploy triggered." || echo "Deploy hook call failed."
fi

echo ""
echo "Done — Render will redeploy shortly."
