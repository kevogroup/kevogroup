#!/usr/bin/env bash
# =============================================================
# One-command setup for your GitHub profile showcase.
#
# What this does:
#   1. Creates the "Kevotech" repo on GitHub (if it doesn't exist)
#   2. Initializes git in this folder
#   3. Pushes everything to GitHub
#   4. Triggers the workflow so your README updates immediately
#
# Prerequisites:
#   - GitHub CLI (gh) installed and authenticated
#     Install: https://cli.github.com
#     Auth:    gh auth login
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================

set -euo pipefail

USERNAME="kevogroup"
REPO="$USERNAME"

echo ""
echo "  GitHub Profile Showcase — Setup"
echo "  ================================"
echo ""

# --- Check that gh CLI is available and authenticated ---
if ! command -v gh &> /dev/null; then
    echo "ERROR: GitHub CLI (gh) is not installed."
    echo "  Install it from https://cli.github.com then run:"
    echo "    gh auth login"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "ERROR: GitHub CLI is not authenticated."
    echo "  Run:  gh auth login"
    exit 1
fi

echo "[1/4] Checking if repo '$USERNAME/$REPO' exists on GitHub..."

if gh repo view "$USERNAME/$REPO" &> /dev/null; then
    echo "  Repo already exists — will push to it."
else
    echo "  Creating repo '$REPO'..."
    gh repo create "$REPO" --public --description "My GitHub profile README" --confirm || true
fi

echo "[2/4] Initializing git..."

git init -b main 2>/dev/null || git init && git checkout -b main 2>/dev/null || true
git add -A
git commit -m "feat: add self-updating GitHub profile README" 2>/dev/null || echo "  (nothing new to commit)"

echo "[3/4] Pushing to GitHub..."

# Set remote (update if it already exists)
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$USERNAME/$REPO.git"
git push -u origin main --force

echo "[4/4] Triggering the workflow..."

# Give GitHub a moment to register the workflow file
sleep 3
gh workflow run "Update Profile README" --repo "$USERNAME/$REPO" 2>/dev/null || {
    echo "  Could not trigger workflow automatically."
    echo "  Go to https://github.com/$USERNAME/$REPO/actions and click 'Run workflow'."
}

echo ""
echo "  Done! Your profile is live at:"
echo "  https://github.com/$USERNAME"
echo ""
echo "  The 'Latest Projects' table will populate within ~1 minute."
echo "  After that, it auto-updates every day at 6 AM UTC."
echo ""
