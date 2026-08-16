#!/bin/bash
# ============================================================
# OTHAIIM-12B MASTER DEPLOYMENT SCRIPT
# Run this ONE script on the DGX to deploy everything:
#   1. Git permanent fix
#   2. Tunnel 3-layer redundancy
#   3. Automation framework + cron
#   4. Frontier builder upgrade
#   5. Full backup to GitHub
#   6. System grade assessment
# ============================================================
# Usage: bash deploy_all.sh
# Run on DGX Spark as: bash ~/deploy_all.sh
# ============================================================

set -e
REPO_DIR="$HOME/othaiim-12b"
SCRIPTS_DIR="$REPO_DIR/scripts"
LOG_FILE="$REPO_DIR/deploy_all_$(date +%Y%m%d_%H%M%S).log"
GITHUB_REPO="https://github.com/aiidentificationmachines-coder/othaiim-12b"

mkdir -p "$SCRIPTS_DIR" "$REPO_DIR/automation/grades"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

log "============================================"
log "OTHAIIM-12B MASTER DEPLOYMENT STARTING"
log "============================================"

# Step 0: Pre-flight
log "[0/7] Pre-flight checks..."
if [ ! -d "$REPO_DIR" ]; then
  log "ERROR: $REPO_DIR not found. Clone the repo first."
  exit 1
fi
log "  Repo found: $REPO_DIR"

# Step 1: Download latest scripts from GitHub
log "[1/7] Downloading latest scripts from GitHub..."
for f in git_permanent_fix.sh permanent_tunnel_fix.sh dgx_automation_framework.sh \
         frontier_builder_upgrade.py auto_train_cycle.sh system_grader.py \
         backup_to_github.sh reconstruct_dgx.sh full_backup_manifest.json; do
  url="https://raw.githubusercontent.com/aiidentificationmachines-coder/othaiim-12b/main/dgx-backup/$f"
  # Try backup dir first, then infrastructure, then automation
  for dir in dgx-backup dgx-infrastructure dgx-automation; do
    url="https://raw.githubusercontent.com/aiidentificationmachines-coder/othaiim-12b/main/$dir/$f"
    if curl -sf -o "$SCRIPTS_DIR/$f" "$url" 2>/dev/null; then
      log "  Downloaded: $f from $dir/"
      break
    fi
  done
done
chmod +x "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/*.py 2>/dev/null || true
log "  Scripts downloaded"

# Step 2: Git permanent fix
log "[2/7] Running git permanent fix..."
if [ -f "$SCRIPTS_DIR/git_permanent_fix.sh" ]; then
  bash "$SCRIPTS_DIR/git_permanent_fix.sh" 2>&1 | tee -a "$LOG_FILE" | tail -5
  log "  Git fix complete"
else
  log "  WARNING: git_permanent_fix.sh not found, doing manual fix"
  cd "$REPO_DIR" && rm -f .git/index.lock .git/index && git reset HEAD . 2>/dev/null
  git config user.email "aiidentificationmachines@gmail.com"
  git config user.name "Marcos Rivas"
  git add -A
  git commit -m "manual_git_fix_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
fi

# Step 3: Tunnel 3-layer fix
log "[3/7] Setting up 3-layer tunnel redundancy..."
if [ -f "$SCRIPTS_DIR/permanent_tunnel_fix.sh" ]; then
  log "  Running permanent tunnel fix (needs sudo for systemd)..."
  sudo bash "$SCRIPTS_DIR/permanent_tunnel_fix.sh" 2>&1 | tee -a "$LOG_FILE" | tail -10
  log "  Tunnel fix complete"
else
  log "  WARNING: permanent_tunnel_fix.sh not found"
fi

# Step 4: Install automation framework cron
log "[4/7] Installing automation cron jobs..."
# Every 6 hours: full automation cycle
(crontab -l 2>/dev/null | grep -v "dgx_automation_framework"; echo "0 */6 * * * bash $SCRIPTS_DIR/dgx_automation_framework.sh >> $REPO_DIR/automation/cron.log 2>&1") | crontab -
# Every hour: git health check
(crontab -l 2>/dev/null | grep -v "git_permanent_fix"; echo "0 * * * * bash $SCRIPTS_DIR/git_permanent_fix.sh --check-only >> $REPO_DIR/automation/git_health.log 2>&1") | crontab -
# Daily at 3am: full backup to GitHub
(crontab -l 2>/dev/null | grep -v "backup_to_github"; echo "0 3 * * * bash $SCRIPTS_DIR/backup_to_github.sh >> $REPO_DIR/automation/backup.log 2>&1") | crontab -
log "  Cron jobs installed: automation(6h), git-health(1h), backup(daily 3am)"

# Step 5: Frontier builder upgrade
log "[5/7] Deploying frontier builder upgrade..."
if [ -f "$SCRIPTS_DIR/frontier_builder_upgrade.py" ]; then
  # Install qwen2.5-coder if not present
  if ! ollama list 2>/dev/null | grep -q "qwen2.5-coder"; then
    log "  Pulling qwen2.5-coder:7b model..."
    ollama pull qwen2.5-coder:7b 2>&1 | tail -3
  fi
  log "  Frontier builder script ready at $SCRIPTS_DIR/frontier_builder_upgrade.py"
  log "  To activate: python3 $SCRIPTS_DIR/frontier_builder_upgrade.py"
else
  log "  WARNING: frontier_builder_upgrade.py not found"
fi

# Step 6: Push everything to GitHub
log "[6/7] Pushing to GitHub..."
cd "$REPO_DIR"
git remote remove origin 2>/dev/null || true
git remote add origin "$GITHUB_REPO.git"
git add -A
git commit -m "master_deployment_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
git push -u origin master:dgx-spark 2>&1 | tail -5 || log "  Push failed (may need authentication)"
log "  GitHub push attempted"

# Step 7: System grade assessment
log "[7/7] Running system grade assessment..."
if [ -f "$SCRIPTS_DIR/system_grader.py" ]; then
  python3 "$SCRIPTS_DIR/system_grader.py" 2>&1 | tee -a "$LOG_FILE" | tail -15
else
  log "  WARNING: system_grader.py not found"
fi

log "============================================"
log "MASTER DEPLOYMENT COMPLETE"
log "============================================"
log ""
log "What was deployed:"
log "  - Git permanent fix (prevents index corruption)"
log "  - 3-layer tunnel redundancy (named + Tailscale + watchdog)"
log "  - Automation cron (6h cycle, 1h git health, daily backup)"
log "  - Frontier builder upgrade script (qwen2.5-coder + multi-step planning)"
log "  - GitHub push to dgx-spark branch"
log "  - System grade assessment"
log ""
log "Next steps:"
log "  1. If Tailscale was installed, note your stable IP: tailscale ip"
log "  2. Activate frontier builder: python3 $SCRIPTS_DIR/frontier_builder_upgrade.py"
log "  3. Check cron jobs: crontab -l"
log "  4. View automation logs: tail -f $REPO_DIR/automation/cron.log"
log "  5. GitHub repo: $GITHUB_REPO"
log ""
log "Full log: $LOG_FILE"
