#!/bin/bash
# DGX GitHub Push Script — Pushes the entire ~/othaiim-12b repo to GitHub
# Run this on the DGX Spark terminal
# Created by Solas — Aug 16, 2026

set -e

REPO_URL="https://github.com/aiidentificationmachines-coder/othaiim-12b.git"
REPO_DIR="$HOME/othaiim-12b"

echo "============================================"
echo "DGX → GitHub Push Script"
echo "============================================"
echo ""

# Step 1: Fix git index if corrupted
cd "$REPO_DIR"
echo "[1/6] Fixing git index..."
rm -f .git/index.lock .git/index
git reset HEAD . 2>/dev/null || true
echo "  Done"

# Step 2: Stage all files
echo "[2/6] Staging files..."
git add -A
STAGED=$(git status --short | wc -l)
echo "  $STAGED files staged"

# Step 3: Configure git user
echo "[3/6] Configuring git..."
git config user.email "aiidentificationmachines@gmail.com"
git config user.name "Marcos Rivas"

# Step 4: Commit
echo "[4/6] Committing..."
git commit -m "dgx_full_repo_push_to_github_$(date +%Y%m%d_%H%M%S)" 2>&1 | tail -2

# Step 5: Add remote (use token from argument or prompt)
echo "[5/6] Adding remote..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"
echo "  Remote added: $REPO_URL"

# Step 6: Push (will prompt for username/password — use token as password)
echo "[6/6] Pushing to GitHub..."
echo "  When prompted for Username: aiidentificationmachines-coder"
echo "  When prompted for Password: paste your GitHub token"
echo ""
git push -u origin master 2>&1 | tail -5

echo ""
echo "============================================"
echo "DONE! Your repo is at:"
echo "  https://github.com/aiidentificationmachines-coder/othaiim-12b"
echo "============================================"
