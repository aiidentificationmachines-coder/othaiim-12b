#!/bin/bash
# Solas Git Fix + GitHub Push Script
# Run on DGX: bash ~/othaiim-12b/git_fix_push.sh
# Does everything: fix index, stage, commit, push to GitHub

set -e
cd ~/othaiim-12b

echo "=== STEP 1: Clean git locks ==="
rm -f .git/index.lock .git/index
git reset HEAD . 2>/dev/null || true
echo "Done"

echo "=== STEP 2: Configure git ==="
git config user.email "aiidentificationmachines@gmail.com"
git config user.name "Marcos Rivas"
echo "Done"

echo "=== STEP 3: Stage all files ==="
git add -A
COUNT=$(git status --short | wc -l)
echo "Staged $COUNT files"

echo "=== STEP 4: Commit ==="
git commit -m "dgx_full_backup_$(date +%Y%m%d_%H%M%S)" 2>&1 | tail -3

echo "=== STEP 5: Add GitHub remote ==="
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/aiidentificationmachines-coder/othaiim-12b.git
echo "Remote added"

echo "=== STEP 6: Push to dgx-spark branch ==="
git push -u origin master:dgx-spark 2>&1 | tail -5

echo ""
echo "========================================"
echo "DONE! Your DGX repo is now on GitHub:"
echo "  https://github.com/aiidentificationmachines-coder/othaiim-12b"
echo "  Branch: dgx-spark"
echo "  Branch: main (Solas workspace files)"
echo "========================================"
