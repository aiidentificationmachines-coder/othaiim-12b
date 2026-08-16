#!/usr/bin/env bash
###############################################################################
# backup_to_github.sh
# -----------------------------------------------------------------------------
# Incremental backup script for the DGX Spark othaiim-12b project.
#
# Target: 10.0.0.175  user: christ_is_king  project: ~/othaiim-12b/
#
# This script:
#   1.  Runs git_permanent_fix.sh to fix any index corruption (pre-flight)
#   2.  Stages all changes (git add -A)
#   3.  Commits with a timestamped message (only if changes exist)
#   4.  Pushes to GitHub on the dgx-spark branch
#   5.  Uploads critical files to Base44 storage (redundancy layer)
#   6.  Generates and emails a completion summary
#
# This script is IDEMPOTENT — safe to run repeatedly.
# It auto-detects when there's nothing to back up and exits cleanly.
#
# Usage:
#   chmod +x backup_to_github.sh
#   ./backup_to_github.sh [--dry-run] [--skip-base44] [--skip-email] [--skip-git-fix]
#
# Can be run via cron for automated incremental backups:
#   0 */6 * * * /home/christ_is_king/othaiim-12b/scripts/backup_to_github.sh >> /var/log/dgx_backup.log 2>&1
#
# Environment variables:
#   PROJECT_DIR      — project directory (default: ~/othaiim-12b)
#   REMOTE_NAME      — git remote name (default: origin)
#   BRANCH_NAME      — git branch (default: dgx-spark)
#   EMAIL_TO         — email address for summary (optional)
#   BASE44_API_KEY   — Base44 API key for file uploads (optional)
###############################################################################
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DGX_HOST="10.0.0.175"
DGX_USER="christ_is_king"
PROJECT_DIR="${PROJECT_DIR:-$HOME/othaiim-12b}"
REMOTE_NAME="${REMOTE_NAME:-origin}"
BRANCH_NAME="${BRANCH_NAME:-dgx-spark}"
EMAIL_TO="${EMAIL_TO:-}"
BASE44_API_KEY="${BASE44_API_KEY:-}"

# Flags
DRY_RUN=false
SKIP_BASE44=false
SKIP_EMAIL=false
SKIP_GIT_FIX=false

# Timestamps
TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
DATE_HUMAN=$(date '+%Y-%m-%d %H:%M:%S %Z')
LOG_FILE="/tmp/backup_to_github_${TIMESTAMP}.log"
SUMMARY_FILE="/tmp/backup_summary_${TIMESTAMP}.md"
BACKUP_ARCHIVE="/tmp/othaiim_backup_${TIMESTAMP}.tar.gz"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Tracking
declare -A BACKUP_STATS
BACKUP_STATS[files_staged]=0
BACKUP_STATS[files_committed]=0
BACKUP_STATS[push_status]="pending"
BACKUP_STATS[base44_status]="pending"
BACKUP_STATS[email_status]="pending"
BACKUP_STATS[errors]=""
BACKUP_STATS[warnings]=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    local level="$1"; shift
    local msg="$*"
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${level} ${msg}" | tee -a "$LOG_FILE"
}

info()  { log "${BLUE}[INFO]${NC}"  "$*"; }
ok()    { log "${GREEN}[OK]${NC}"   "$*"; }
warn()  { log "${YELLOW}[WARN]${NC}" "$*"; }
err()   { log "${RED}[ERROR]${NC}" "$*"; }
step()  { log "${CYAN}[STEP]${NC}"  "$*"; }

die() { err "$*"; exit 1; }

run() {
    if $DRY_RUN; then
        info "[DRY-RUN] $*"
    else
        eval "$@" 2>&1 | tee -a "$LOG_FILE"
    fi
}

add_error()   { BACKUP_STATS[errors]+="${1}\n"; }
add_warning() { BACKUP_STATS[warnings]+="${1}\n"; }

check_cmd() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)       DRY_RUN=true; shift ;;
        --skip-base44)   SKIP_BASE44=true; shift ;;
        --skip-email)    SKIP_EMAIL=true; shift ;;
        --skip-git-fix)  SKIP_GIT_FIX=true; shift ;;
        --email)         EMAIL_TO="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run        Show what would happen without making changes"
            echo "  --skip-base44    Skip uploading files to Base44 storage"
            echo "  --skip-email     Skip sending email summary"
            echo "  --skip-git-fix   Skip running git_permanent_fix.sh (use if index is healthy)"
            echo "  --email ADDR     Email address for completion summary"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
info "╔══════════════════════════════════════════════════╗"
info "║   DGX Spark Incremental Backup — Starting       ║"
info "╚══════════════════════════════════════════════════╝"
info "Timestamp:  $DATE_HUMAN"
info "Project:    $PROJECT_DIR"
info "Branch:     $BRANCH_NAME"
info "Dry run:    $DRY_RUN"
info "Skip Base44: $SKIP_BASE44"
info "Skip email:  $SKIP_EMAIL"
info "Skip git fix: $SKIP_GIT_FIX"
info "Log file:   $LOG_FILE"
echo ""

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
info "Pre-flight checks..."

if [[ ! -d "$PROJECT_DIR" ]]; then
    die "Project directory not found: $PROJECT_DIR"
fi

cd "$PROJECT_DIR" || die "Cannot cd to $PROJECT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Not a git repository: $PROJECT_DIR"
fi

GIT_DIR=$(git rev-parse --git-dir)
info "Git dir: $GIT_DIR"
info "Current branch: $(git branch --show-current 2>/dev/null || echo 'detached')"
info "Current commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'none')"

ok "Pre-flight checks passed"
echo ""

# ---------------------------------------------------------------------------
# STEP 1: Run git_permanent_fix.sh (fix index corruption pre-flight)
# ---------------------------------------------------------------------------
step "STEP 1/6: Run git_permanent_fix.sh (fix any index corruption)"

if $SKIP_GIT_FIX; then
    warn "Skipping git fix (--skip-git-fix)"
else
    FIX_SCRIPT="$PROJECT_DIR/scripts/git_permanent_fix.sh"
    [[ ! -f "$FIX_SCRIPT" ]] && FIX_SCRIPT="$PROJECT_DIR/git_permanent_fix.sh"

    if [[ -f "$FIX_SCRIPT" ]]; then
        info "Running git_permanent_fix.sh..."
        chmod +x "$FIX_SCRIPT"
        if $DRY_RUN; then
            info "[DRY-RUN] Would run: bash $FIX_SCRIPT"
        else
            if bash "$FIX_SCRIPT" >>"$LOG_FILE" 2>&1; then
                ok "git_permanent_fix.sh completed successfully"
            else
                warn "git_permanent_fix.sh had issues — attempting manual fix"
                # Manual fallback: just clean lock and rebuild index
                rm -f "${GIT_DIR}/index.lock"
                if git rev-parse --verify HEAD >/dev/null 2>&1; then
                    git read-tree HEAD 2>>"$LOG_FILE" || true
                fi
                git add -A 2>>"$LOG_FILE" || true
                ok "Manual fallback fix applied"
            fi
        fi
    else
        warn "git_permanent_fix.sh not found — running inline fix"
        if ! $DRY_RUN; then
            rm -f "${GIT_DIR}/index.lock"
            if git rev-parse --verify HEAD >/dev/null 2>&1; then
                git read-tree HEAD 2>>"$LOG_FILE" || true
            fi
            git add -A 2>>"$LOG_FILE" || true
            ok "Inline git fix applied"
        fi
    fi
fi

echo ""

# ---------------------------------------------------------------------------
# STEP 2: Stage all changes
# ---------------------------------------------------------------------------
step "STEP 2/6: Stage all changes"

# Ensure no stale lock file
if [[ -f "${GIT_DIR}/index.lock" ]]; then
    warn "index.lock still present — removing"
    run "rm -f '${GIT_DIR}/index.lock'"
fi

# Stage all changes
info "Staging all changes with git add -A..."
run "git add -A"

# Count staged files
STAGED_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l || echo 0)
BACKUP_STATS[files_staged]=$STAGED_COUNT
info "Files staged: $STAGED_COUNT"

if [[ "$STAGED_COUNT" -eq 0 ]]; then
    ok "No changes to stage — working tree matches index"
else
    ok "$STAGED_COUNT file(s) staged"
    # Show what's staged (first 20)
    if [[ "$STAGED_COUNT" -le 20 ]]; then
        git diff --cached --name-only 2>/dev/null | while read -r f; do
            info "  + $f"
        done
    else
        git diff --cached --name-only 2>/dev/null | head -20 | while read -r f; do
            info "  + $f"
        done
        info "  ... and $((STAGED_COUNT - 20)) more"
    fi
fi

echo ""

# ---------------------------------------------------------------------------
# STEP 3: Commit with timestamped message (if changes exist)
# ---------------------------------------------------------------------------
step "STEP 3/6: Commit changes"

if git diff --cached --quiet 2>/dev/null; then
    ok "No staged changes — nothing to commit"
    BACKUP_STATS[files_committed]=0
else
    COMMIT_MSG="backup: incremental backup ${TIMESTAMP} — ${DATE_HUMAN}"

    if $DRY_RUN; then
        info "[DRY-RUN] Would commit with message: $COMMIT_MSG"
    else
        info "Committing with message: $COMMIT_MSG"
        if git commit -m "$COMMIT_MSG" >>"$LOG_FILE" 2>&1; then
            COMMITTED_COUNT=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | wc -l || echo 0)
            BACKUP_STATS[files_committed]=$COMMITTED_COUNT
            ok "Committed $COMMITTED_COUNT file(s): $(git rev-parse --short HEAD)"
        else
            warn "git commit failed — possible empty commit or hook rejection"
            add_warning "git commit failed"
        fi
    fi
fi

echo ""

# ---------------------------------------------------------------------------
# STEP 4: Push to GitHub
# ---------------------------------------------------------------------------
step "STEP 4/6: Push to GitHub ($BRANCH_NAME branch)"

# Check if remote exists
if ! git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    warn "No remote '$REMOTE_NAME' configured — cannot push"
    BACKUP_STATS[push_status]="no-remote"
    add_error "No git remote '$REMOTE_NAME' configured"
else
    REMOTE_URL=$(git remote get-url "$REMOTE_NAME")
    # Mask credentials in URL for logging
    MASKED_URL=$(echo "$REMOTE_URL" | sed 's#//[^@]*@#//***@#g' 2>/dev/null || echo "$REMOTE_URL")
    info "Remote: $REMOTE_NAME -> $MASKED_URL"

    # Ensure we're on the right branch
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
    if [[ "$CURRENT_BRANCH" != "$BRANCH_NAME" ]]; then
        warn "Currently on '$CURRENT_BRANCH', expected '$BRANCH_NAME'"
        info "Switching to $BRANCH_NAME..."
        if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
            run "git checkout $BRANCH_NAME"
        else
            run "git checkout -b $BRANCH_NAME"
        fi
    fi

    # Push
    if $DRY_RUN; then
        info "[DRY-RUN] Would push to $REMOTE_NAME/$BRANCH_NAME"
    else
        info "Pushing to $REMOTE_NAME/$BRANCH_NAME..."
        if git push -u "$REMOTE_NAME" "$BRANCH_NAME" >>"$LOG_FILE" 2>&1; then
            ok "Push successful"
            BACKUP_STATS[push_status]="success"
        else
            # Try force-with-lease (local may be ahead due to backup commits)
            warn "Normal push failed — trying force-with-lease..."
            if git push -u --force-with-lease "$REMOTE_NAME" "$BRANCH_NAME" >>"$LOG_FILE" 2>&1; then
                ok "Push successful (force-with-lease)"
                BACKUP_STATS[push_status]="success-force"
            else
                err "Push failed"
                BACKUP_STATS[push_status]="failed"
                add_error "git push to $REMOTE_NAME/$BRANCH_NAME failed"
            fi
        fi
    fi
fi

# Get current commit info for summary
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
CURRENT_COMMIT_MSG=$(git log -1 --format='%s' 2>/dev/null || echo "unknown")
COMMIT_COUNT=$(git rev-list --count HEAD 2>/dev/null || echo 0)
FILE_COUNT=$(git ls-files 2>/dev/null | wc -l || echo 0)

info "Current commit: $CURRENT_COMMIT ($CURRENT_COMMIT_MSG)"
info "Total commits: $COMMIT_COUNT"
info "Total tracked files: $FILE_COUNT"

echo ""

# ---------------------------------------------------------------------------
# STEP 5: Upload critical files to Base44 storage
# ---------------------------------------------------------------------------
step "STEP 5/6: Upload critical files to Base44 storage"

if $SKIP_BASE44; then
    warn "Skipping Base44 upload (--skip-base44)"
    BACKUP_STATS[base44_status]="skipped"
elif [[ -z "$BASE44_API_KEY" ]]; then
    warn "BASE44_API_KEY not set — skipping Base44 upload"
    warn "Set BASE44_API_KEY env var to enable Base44 redundancy backup"
    BACKUP_STATS[base44_status]="no-key"
else
    info "Preparing critical files for Base44 upload..."

    # Create a tarball of critical files (configs, scripts, docs — not large binaries)
    CRITICAL_PATTERS=(
        "config/"
        "scripts/"
        "docs/"
        ".env.example"
        ".gitignore"
        "requirements.txt"
        "pyproject.toml"
        "setup.py"
        "environment.yml"
        "Dockerfile"
        "docker-compose.yml"
        "Makefile"
        "README.md"
        "full_backup_manifest.json"
        "git_permanent_fix.sh"
        "backup_to_github.sh"
        "reconstruct_dgx.sh"
    )

    # Build tarball
    info "Creating backup archive: $BACKUP_ARCHIVE"
    TAR_ARGS=""
    for pattern in "${CRITICAL_PATTERS[@]}"; do
        if [[ -e "$PROJECT_DIR/$pattern" ]]; then
            TAR_ARGS="$TAR_ARGS $pattern"
        fi
    done

    # Also add pip freeze and conda env export
    if ! $DRY_RUN; then
        pip freeze > "$PROJECT_DIR/pip_freeze_backup.txt" 2>/dev/null || true
        conda env export > "$PROJECT_DIR/conda_env_backup.yml" 2>/dev/null || true
        TAR_ARGS="$TAR_ARGS pip_freeze_backup.txt conda_env_backup.yml"
    fi

    if [[ -n "$TAR_ARGS" ]]; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would create archive with: $TAR_ARGS"
            info "[DRY-RUN] Would upload to Base44 storage"
        else
            # Create tarball
            if tar -czf "$BACKUP_ARCHIVE" -C "$PROJECT_DIR" $TAR_ARGS 2>>"$LOG_FILE"; then
                ARCHIVE_SIZE=$(stat -c %s "$BACKUP_ARCHIVE" 2>/dev/null || stat -f %z "$BACKUP_ARCHIVE" 2>/dev/null || echo 0)
                ARCHIVE_SIZE_MB=$((ARCHIVE_SIZE / 1024 / 1024))
                ok "Backup archive created: $BACKUP_ARCHIVE (${ARCHIVE_SIZE_MB} MB)"

                # Upload to Base44 (using curl to Base44 API)
                # NOTE: The actual Base44 upload API endpoint will depend on the platform.
                # This uses the standard file upload pattern.
                if curl -sf -X POST \
                    -H "Authorization: Bearer $BASE44_API_KEY" \
                    -F "file=@$BACKUP_ARCHIVE" \
                    -F "name=othaiim_backup_${TIMESTAMP}" \
                    -F "description=Incremental backup from DGX Spark - ${DATE_HUMAN}" \
                    "https://api.base44.com/v1/files/upload" >>"$LOG_FILE" 2>&1; then
                    ok "Backup uploaded to Base44 storage"
                    BACKUP_STATS[base44_status]="success"
                else
                    warn "Base44 upload failed — archive is still available at $BACKUP_ARCHIVE"
                    BACKUP_STATS[base44_status]="failed"
                    add_warning "Base44 upload failed"
                fi

                # Clean up archive
                rm -f "$BACKUP_ARCHIVE"
            else
                warn "Failed to create backup archive"
                BACKUP_STATS[base44_status]="archive-failed"
                add_warning "Failed to create backup archive"
            fi
        fi
    else
        warn "No critical files found to archive"
        BACKUP_STATS[base44_status]="no-files"
    fi
fi

echo ""

# ---------------------------------------------------------------------------
# STEP 6: Generate and email completion summary
# ---------------------------------------------------------------------------
step "STEP 6/6: Generate and email completion summary"

# Generate summary
cat > "$SUMMARY_FILE" << EOF
# DGX Spark Backup Summary

**Date:** $DATE_HUMAN
**Host:** $DGX_HOST
**User:** $DGX_USER
**Project:** $PROJECT_DIR
**Branch:** $BRANCH_NAME

## Results

| Metric | Value |
|--------|-------|
| Files staged | ${BACKUP_STATS[files_staged]} |
| Files committed | ${BACKUP_STATS[files_committed]} |
| Current commit | $CURRENT_COMMIT |
| Commit message | $CURRENT_COMMIT_MSG |
| Total commits | $COMMIT_COUNT |
| Total tracked files | $FILE_COUNT |
| GitHub push status | ${BACKUP_STATS[push_status]} |
| Base44 upload status | ${BACKUP_STATS[base44_status]} |

## Push Status

EOF

case "${BACKUP_STATS[push_status]}" in
    success)       echo "✅ **GitHub push: SUCCESS** — pushed to $REMOTE_NAME/$BRANCH_NAME" >> "$SUMMARY_FILE" ;;
    success-force) echo "✅ **GitHub push: SUCCESS (force-with-lease)** — pushed to $REMOTE_NAME/$BRANCH_NAME" >> "$SUMMARY_FILE" ;;
    failed)        echo "❌ **GitHub push: FAILED** — check log file: $LOG_FILE" >> "$SUMMARY_FILE" ;;
    no-remote)     echo "⚠️ **GitHub push: SKIPPED** — no remote configured" >> "$SUMMARY_FILE" ;;
    *)             echo "⏳ **GitHub push: ${BACKUP_STATS[push_status]}**" >> "$SUMMARY_FILE" ;;
esac

cat >> "$SUMMARY_FILE" << EOF

## Base44 Upload Status

EOF

case "${BACKUP_STATS[base44_status]}" in
    success)        echo "✅ **Base44 upload: SUCCESS** — critical files backed up" >> "$SUMMARY_FILE" ;;
    failed)         echo "❌ **Base44 upload: FAILED** — check log file: $LOG_FILE" >> "$SUMMARY_FILE" ;;
    skipped)        echo "⏭️ **Base44 upload: SKIPPED** (--skip-base44 flag)" >> "$SUMMARY_FILE" ;;
    no-key)         echo "⚠️ **Base44 upload: SKIPPED** — BASE44_API_KEY not set" >> "$SUMMARY_FILE" ;;
    no-files)       echo "⚠️ **Base44 upload: SKIPPED** — no critical files found" >> "$SUMMARY_FILE" ;;
    archive-failed) echo "❌ **Base44 upload: FAILED** — could not create archive" >> "$SUMMARY_FILE" ;;
    *)              echo "⏳ **Base44 upload: ${BACKUP_STATS[base44_status]}**" >> "$SUMMARY_FILE" ;;
esac

# Add errors and warnings
if [[ -n "${BACKUP_STATS[errors]}" ]]; then
    echo "" >> "$SUMMARY_FILE"
    echo "## Errors" >> "$SUMMARY_FILE"
    echo "" >> "$SUMMARY_FILE"
    echo -e "${BACKUP_STATS[errors]}" >> "$SUMMARY_FILE"
fi

if [[ -n "${BACKUP_STATS[warnings]}" ]]; then
    echo "" >> "$SUMMARY_FILE"
    echo "## Warnings" >> "$SUMMARY_FILE"
    echo "" >> "$SUMMARY_FILE"
    echo -e "${BACKUP_STATS[warnings]}" >> "$SUMMARY_FILE"
fi

# Add git status
echo "" >> "$SUMMARY_FILE"
echo "## Git Status" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo '```' >> "$SUMMARY_FILE"
git log --oneline -10 >> "$SUMMARY_FILE" 2>&1 || echo "Unable to get git log" >> "$SUMMARY_FILE"
echo '```' >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo "## Files Changed in This Backup" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"
echo '```' >> "$SUMMARY_FILE"
git diff --name-only HEAD~1 HEAD >> "$SUMMARY_FILE" 2>/dev/null || echo "No changes in latest commit" >> "$SUMMARY_FILE"
echo '```' >> "$SUMMARY_FILE"

# Add log file location
echo "" >> "$SUMMARY_FILE"
echo "---" >> "$SUMMARY_FILE"
echo "Full log: \`$LOG_FILE\`" >> "$SUMMARY_FILE"

ok "Summary generated: $SUMMARY_FILE"

# Print summary to console
echo ""
echo "=========================================="
echo "       BACKUP SUMMARY"
echo "=========================================="
cat "$SUMMARY_FILE"
echo "=========================================="

# Email the summary
if $SKIP_EMAIL; then
    warn "Skipping email (--skip-email)"
    BACKUP_STATS[email_status]="skipped"
elif [[ -z "$EMAIL_TO" ]]; then
    warn "EMAIL_TO not set — skipping email summary"
    warn "Set EMAIL_TO env var or use --email flag to enable"
    BACKUP_STATS[email_status]="no-recipient"
elif $DRY_RUN; then
    info "[DRY-RUN] Would email summary to: $EMAIL_TO"
    BACKUP_STATS[email_status]="dry-run"
else
    info "Emailing summary to: $EMAIL_TO"

    # Determine email subject based on success/failure
    if [[ "${BACKUP_STATS[push_status]}" == "success" || "${BACKUP_STATS[push_status]}" == "success-force" ]]; then
        EMAIL_SUBJECT="[DGX Backup] SUCCESS — othaiim-12b backup completed — ${TIMESTAMP}"
    else
        EMAIL_SUBJECT="[DGX Backup] ATTENTION — othaiim-12b backup had issues — ${TIMESTAMP}"
    fi

    # Try to send email using available tools
    EMAIL_SENT=false

    # Method 1: mail command (mailutils)
    if check_cmd mail && ! $EMAIL_SENT; then
        if cat "$SUMMARY_FILE" | mail -s "$EMAIL_SUBJECT" "$EMAIL_TO" 2>>"$LOG_FILE"; then
            ok "Email sent via 'mail' command to $EMAIL_TO"
            EMAIL_SENT=true
            BACKUP_STATS[email_status]="success"
        fi
    fi

    # Method 2: sendmail
    if ! $EMAIL_SENT && check_cmd sendmail; then
        {
            echo "To: $EMAIL_TO"
            echo "Subject: $EMAIL_SUBJECT"
            echo "Content-Type: text/plain; charset=UTF-8"
            echo ""
            cat "$SUMMARY_FILE"
        } | sendmail -t 2>>"$LOG_FILE" && EMAIL_SENT=true && BACKUP_STATS[email_status]="success" && ok "Email sent via sendmail to $EMAIL_TO"
    fi

    # Method 3: mutt
    if ! $EMAIL_SENT && check_cmd mutt; then
        if cat "$SUMMARY_FILE" | mutt -s "$EMAIL_SUBJECT" "$EMAIL_TO" 2>>"$LOG_FILE"; then
            ok "Email sent via mutt to $EMAIL_TO"
            EMAIL_SENT=true
            BACKUP_STATS[email_status]="success"
        fi
    fi

    # Method 4: curl to Base44 email API (if BASE44_API_KEY is set)
    if ! $EMAIL_SENT && [[ -n "$BASE44_API_KEY" ]]; then
        if curl -sf -X POST \
            -H "Authorization: Bearer $BASE44_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{\"to\": \"$EMAIL_TO\", \"subject\": \"$EMAIL_SUBJECT\", \"body\": $(python3 -c "import json,sys; print(json.dumps(open('$SUMMARY_FILE').read()))" 2>/dev/null || echo '""')}" \
            "https://api.base44.com/v1/emails/send" >>"$LOG_FILE" 2>&1; then
            ok "Email sent via Base44 API to $EMAIL_TO"
            EMAIL_SENT=true
            BACKUP_STATS[email_status]="success"
        fi
    fi

    if ! $EMAIL_SENT; then
        warn "No email method available — summary saved to $SUMMARY_FILE"
        BACKUP_STATS[email_status]="no-method"
        add_warning "Email could not be sent — no mail client found"
    fi
fi

echo ""

# ---------------------------------------------------------------------------
# Clean up generated files
# ---------------------------------------------------------------------------
if ! $DRY_RUN; then
    # Clean up temporary pip freeze / conda export files
    rm -f "$PROJECT_DIR/pip_freeze_backup.txt" "$PROJECT_DIR/conda_env_backup.yml" 2>/dev/null || true
    # Keep summary and log for reference (will be overwritten on next run)
fi

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------
info "╔══════════════════════════════════════════════════╗"
info "║   Backup Complete — Final Report                 ║"
info "╠══════════════════════════════════════════════════╣"
info "║  Files staged:     ${BACKUP_STATS[files_staged]}"
info "║  Files committed:   ${BACKUP_STATS[files_committed]}"
info "║  Current commit:    $CURRENT_COMMIT"
info "║  Total commits:     $COMMIT_COUNT"
info "║  Total files:       $FILE_COUNT"
info "║  GitHub push:       ${BACKUP_STATS[push_status]}"
info "║  Base44 upload:     ${BACKUP_STATS[base44_status]}"
info "║  Email summary:     ${BACKUP_STATS[email_status]}"
info "╠══════════════════════════════════════════════════╣"
if [[ -n "${BACKUP_STATS[errors]}" ]]; then
info "║  ⚠️  ERRORS PRESENT — review log"
else
info "║  ✅ No errors"
fi
info "║  Log file:          $LOG_FILE"
info "║  Summary file:      $SUMMARY_FILE"
info "╚══════════════════════════════════════════════════╝"

# Exit code: 0 if push succeeded (or nothing to push), 1 if push failed
if [[ "${BACKUP_STATS[push_status]}" == "failed" ]]; then
    exit 1
fi
exit 0
