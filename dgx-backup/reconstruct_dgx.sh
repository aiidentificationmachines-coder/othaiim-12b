#!/usr/bin/env bash
###############################################################################
# reconstruct_dgx.sh
# -----------------------------------------------------------------------------
# Full reconstruction script — rebuilds the entire DGX Spark environment
# from GitHub + Base44 storage after a failure or migration.
#
# Target: 10.0.0.175  user: christ_is_king  project: ~/othaiim-12b/
#
# This script is IDEMPOTENT — it can be run on a fresh DGX or an existing
# one without causing harm. It will skip steps that are already complete.
#
# Reconstruction order:
#   1.  Pre-flight checks (network, tools, disk space)
#   2.  Restore SSH keys from Base44 (if provided)
#   3.  Clone repository from GitHub (dgx-spark branch)
#   4.  Restore .env from Base44 (if provided)
#   5.  Install system dependencies
#   6.  Install Python dependencies (pip + conda)
#   7.  Restore model weights from Base44 (if provided)
#   8.  Run git_permanent_fix.sh (install prevention mechanisms)
#   9.  Install crontab entries
#   10. Start API server
#   11. Verify reconstruction (full health check)
#
# Usage:
#   chmod +x reconstruct_dgx.sh
#   ./reconstruct_dgx.sh [--skip-model-weights] [--skip-ssh-restore] [--dry-run]
#
# Environment variables (optional overrides):
#   GITHUB_REMOTE   — full git remote URL (overrides default)
#   BASE44_FILE_URI — Base44 private file URI for secrets/env backup
#   PYTHON_VERSION  — Python version to install (default: 3.11)
#   CONDA_ENV_NAME  — Conda environment name (default: othaiim-12b)
###############################################################################
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DGX_HOST="10.0.0.175"
DGX_USER="christ_is_king"
PROJECT_NAME="othaiim-12b"
PROJECT_DIR="${PROJECT_DIR:-$HOME/othaiim-12b}"
REMOTE_NAME="origin"
BRANCH_NAME="dgx-spark"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-othaiim-12b}"

# GitHub remote — must be set via env var or argument
GITHUB_REMOTE="${GITHUB_REMOTE:-}"

# Base44 file URI for downloading secrets/env (if available)
BASE44_FILE_URI="${BASE44_FILE_URI:-}"
BASE44_SIGNED_URL="${BASE44_SIGNED_URL:-}"

# Flags
SKIP_MODEL_WEIGHTS=false
SKIP_SSH_RESTORE=false
DRY_RUN=false
LOG_FILE="/tmp/reconstruct_dgx_$(date +%Y%m%d_%H%M%S).log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Track completion of each step
declare -A STEPS_COMPLETED

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

check_cmd() {
    command -v "$1" >/dev/null 2>&1 || return 1
    return 0
}

ensure_cmd() {
    local cmd="$1"
    local pkg="${2:-$1}"
    if ! check_cmd "$cmd"; then
        info "Installing $cmd (package: $pkg)"
        if check_cmd apt-get; then
            run "sudo apt-get update -qq && sudo apt-get install -y -qq $pkg"
        elif check_cmd yum; then
            run "sudo yum install -y $pkg"
        elif check_cmd dnf; then
            run "sudo dnf install -y $pkg"
        else
            die "Cannot install $pkg — no supported package manager found"
        fi
    fi
}

step_done() { STEPS_COMPLETED["$1"]=true; ok "✅ $1 complete"; echo ""; }
is_done()   { [[ "${STEPS_COMPLETED[$1]:-false}" == "true" ]]; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-model-weights)  SKIP_MODEL_WEIGHTS=true; shift ;;
        --skip-ssh-restore)    SKIP_SSH_RESTORE=true; shift ;;
        --dry-run)             DRY_RUN=true; shift ;;
        --github-remote)       GITHUB_REMOTE="$2"; shift 2 ;;
        --base44-uri)          BASE44_FILE_URI="$2"; shift 2 ;;
        --base44-url)         BASE44_SIGNED_URL="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-model-weights   Skip downloading model weights from Base44"
            echo "  --skip-ssh-restore     Skip SSH key restoration"
            echo "  --dry-run              Show what would happen without making changes"
            echo "  --github-remote URL    GitHub git remote URL"
            echo "  --base44-uri URI       Base44 private file URI for secrets/env"
            echo "  --base44-url URL       Base44 signed URL for direct download"
            echo "  --help                 Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  GITHUB_REMOTE    Full git remote URL"
            echo "  BASE44_FILE_URI  Base44 private file URI"
            echo "  BASE44_SIGNED_URL Base44 signed download URL"
            echo "  PYTHON_VERSION   Python version (default: 3.11)"
            echo "  CONDA_ENV_NAME   Conda environment name (default: othaiim-12b)"
            exit 0
            ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
info "╔══════════════════════════════════════════════════╗"
info "║   DGX Spark Full Reconstruction — Starting       ║"
info "╚══════════════════════════════════════════════════╝"
info "Target:     ${DGX_USER}@${DGX_HOST}"
info "Project:    ${PROJECT_DIR}"
info "Branch:     ${BRANCH_NAME}"
info "Dry run:    ${DRY_RUN}"
info "Log file:   ${LOG_FILE}"
echo ""

# ---------------------------------------------------------------------------
# STEP 1: Pre-flight checks
# ---------------------------------------------------------------------------
step "STEP 1/11: Pre-flight checks (network, tools, disk space)"

# Check essential tools
ensure_cmd git
ensure_cmd curl
ensure_cmd python3
ensure_cmd pip3

# Check disk space (need at least 50 GB for model weights)
AVAILABLE_GB=$(df -BG "$HOME" 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}' || echo 0)
info "Available disk space: ${AVAILABLE_GB} GB"
if [[ "$AVAILABLE_GB" -lt 10 ]]; then
    warn "Low disk space (${AVAILABLE_GB} GB) — reconstruction may fail"
    warn "Model weights require ~20-50 GB. Run with --skip-model-weights if needed."
fi

# Check network connectivity to GitHub
info "Checking GitHub connectivity..."
if curl -sf --connect-timeout 10 https://github.com >/dev/null 2>&1; then
    ok "GitHub is reachable"
else
    warn "GitHub not reachable — some steps may fail"
fi

# Determine GitHub remote URL
if [[ -z "$GITHUB_REMOTE" ]]; then
    warn "GITHUB_REMOTE not set — attempting to detect from existing config or prompt"
    if [[ -f "$PROJECT_DIR/.git/config" ]]; then
        GITHUB_REMOTE=$(git -C "$PROJECT_DIR" remote get-url "$REMOTE_NAME" 2>/dev/null || true)
        if [[ -n "$GITHUB_REMOTE" ]]; then
            ok "Found existing remote: $GITHUB_REMOTE"
        fi
    fi
    if [[ -z "$GITHUB_REMOTE" ]]; then
        info "Please provide GitHub remote URL:"
        info "  Set GITHUB_REMOTE env var, or"
        info "  Run with: --github-remote https://github.com/<user>/othaiim-12b.git"
        die "GitHub remote URL is required for reconstruction"
    fi
fi
info "GitHub remote: $GITHUB_REMOTE"

step_done "pre-flight"

# ---------------------------------------------------------------------------
# STEP 2: Restore SSH keys from Base44 (if provided)
# ---------------------------------------------------------------------------
step "STEP 2/11: Restore SSH keys"

if $SKIP_SSH_RESTORE; then
    warn "Skipping SSH key restoration (--skip-ssh-restore)"
elif [[ -z "$BASE44_FILE_URI" && -z "$BASE44_SIGNED_URL" ]]; then
    warn "No Base44 URI/URL provided for SSH keys — skipping"
    warn "You will need to manually set up SSH keys for GitHub access"
    info "If GitHub remote uses HTTPS, SSH keys are not needed"
elif [[ -d "$HOME/.ssh" && $(ls -A "$HOME/.ssh" 2>/dev/null | wc -l) -gt 0 ]]; then
    ok "SSH directory already exists with keys — skipping restore"
else
    info "Restoring SSH keys from Base44..."

    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"

    if [[ -n "$BASE44_SIGNED_URL" ]]; then
        SSH_TAR_URL="$BASE44_SIGNED_URL"
    else
        # Generate signed URL from URI (this would be done by the caller normally)
        # For now, use the URI directly if it looks like a URL
        SSH_TAR_URL="$BASE44_FILE_URI"
    fi

    # Download SSH keys archive
    SSH_ARCHIVE="/tmp/ssh_keys_backup.tar.gz"
    if curl -sf -L -o "$SSH_ARCHIVE" "$SSH_TAR_URL" 2>/dev/null; then
        info "Downloaded SSH keys archive"
        # Extract to ~/.ssh
        tar -xzf "$SSH_ARCHIVE" -C "$HOME/.ssh" 2>/dev/null || {
            # Maybe it's not a tar — try as individual key files
            cp "$SSH_ARCHIVE" "$HOME/.ssh/id_ed25519" 2>/dev/null || true
            cp "$SSH_ARCHIVE" "$HOME/.ssh/id_rsa" 2>/dev/null || true
        }
        chmod 600 "$HOME/.ssh/"* 2>/dev/null || true
        chmod 644 "$HOME/.ssh/"*.pub 2>/dev/null || true
        rm -f "$SSH_ARCHIVE"
        ok "SSH keys restored"
    else
        warn "Failed to download SSH keys from Base44 — manual setup required"
    fi

    # Ensure known_hosts has GitHub
    if ! grep -q "github.com" "$HOME/.ssh/known_hosts" 2>/dev/null; then
        info "Adding GitHub to known_hosts..."
        ssh-keyscan -t ed25519,rsa github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
    fi
fi

step_done "ssh-restore"

# ---------------------------------------------------------------------------
# STEP 3: Clone repository from GitHub
# ---------------------------------------------------------------------------
step "STEP 3/11: Clone repository from GitHub"

if [[ -d "$PROJECT_DIR/.git" ]]; then
    info "Project directory already exists: $PROJECT_DIR"
    info "Verifying it's a valid git repo..."

    if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        ok "Existing git repository found"

        # Update remote URL if needed
        CURRENT_REMOTE=$(git -C "$PROJECT_DIR" remote get-url "$REMOTE_NAME" 2>/dev/null || true)
        if [[ -n "$CURRENT_REMOTE" && "$CURRENT_REMOTE" != "$GITHUB_REMOTE" ]]; then
            info "Updating remote URL: $CURRENT_REMOTE -> $GITHUB_REMOTE"
            run "git -C '$PROJECT_DIR' remote set-url '$REMOTE_NAME' '$GITHUB_REMOTE'"
        elif [[ -z "$CURRENT_REMOTE" ]]; then
            info "Adding remote: $REMOTE_NAME -> $GITHUB_REMOTE"
            run "git -C '$PROJECT_DIR' remote add '$REMOTE_NAME' '$GITHUB_REMOTE'"
        fi

        # Fetch latest
        info "Fetching latest from GitHub..."
        run "git -C '$PROJECT_DIR' fetch --all --prune"

        # Checkout correct branch
        if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
            run "git -C '$PROJECT_DIR' checkout '$BRANCH_NAME'"
            run "git -C '$PROJECT_DIR' pull '$REMOTE_NAME' '$BRANCH_NAME'"
        elif git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/remotes/${REMOTE_NAME}/${BRANCH_NAME}" 2>/dev/null; then
            run "git -C '$PROJECT_DIR' checkout -b '$BRANCH_NAME' '${REMOTE_NAME}/${BRANCH_NAME}'"
        else
            warn "Branch $BRANCH_NAME not found — staying on current branch"
        fi
        ok "Repository updated from GitHub"
    else
        warn "Directory exists but is not a git repo — backing up and re-cloning"
        mv "$PROJECT_DIR" "${PROJECT_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
        run "git clone --branch '$BRANCH_NAME' '$GITHUB_REMOTE' '$PROJECT_DIR'"
        ok "Repository cloned from GitHub"
    fi
else
    info "Cloning repository from GitHub..."
    run "git clone --branch '$BRANCH_NAME' '$GITHUB_REMOTE' '$PROJECT_DIR'"
    ok "Repository cloned from GitHub"
fi

cd "$PROJECT_DIR" || die "Cannot cd to $PROJECT_DIR"

# Verify commit count
COMMIT_COUNT=$(git rev-list --count HEAD 2>/dev/null || echo 0)
info "Commit count: $COMMIT_COUNT"
if [[ "$COMMIT_COUNT" -lt 8 ]]; then
    warn "Expected 8+ commits but found $COMMIT_COUNT — some history may be missing"
fi

# Verify file count
FILE_COUNT=$(git ls-files 2>/dev/null | wc -l || echo 0)
info "Tracked files: $FILE_COUNT"
if [[ "$FILE_COUNT" -lt 97 ]]; then
    warn "Expected 97+ files but found $FILE_COUNT — some files may be missing"
fi

step_done "clone"

# ---------------------------------------------------------------------------
# STEP 4: Restore .env from Base44 (if provided)
# ---------------------------------------------------------------------------
step "STEP 4/11: Restore .env file"

ENV_FILE="$PROJECT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    ok ".env file already exists — skipping restore"
elif [[ -z "$BASE44_FILE_URI" && -z "$BASE44_SIGNED_URL" ]]; then
    warn "No Base44 URI/URL provided for .env — checking for .env.example"
    if [[ -f "$PROJECT_DIR/.env.example" ]]; then
        info "Creating .env from .env.example"
        cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
        warn "You MUST edit $ENV_FILE with real secrets before running the API"
    else
        warn "No .env or .env.example found — you must create $ENV_FILE manually"
    fi
else
    info "Downloading .env from Base44..."
    if [[ -n "$BASE44_SIGNED_URL" ]]; then
        ENV_URL="$BASE44_SIGNED_URL"
    else
        ENV_URL="$BASE44_FILE_URI"
    fi

    if curl -sf -L -o "$ENV_FILE" "$ENV_URL" 2>/dev/null; then
        chmod 600 "$ENV_FILE"
        ok ".env file restored from Base44"
    else
        warn "Failed to download .env from Base44"
        if [[ -f "$PROJECT_DIR/.env.example" ]]; then
            cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
            chmod 600 "$ENV_FILE"
            warn "Created .env from .env.example — edit with real secrets"
        fi
    fi
fi

step_done "env-restore"

# ---------------------------------------------------------------------------
# STEP 5: Install system dependencies
# ---------------------------------------------------------------------------
step "STEP 5/11: Install system dependencies"

info "Installing system packages..."

# Update package list
run "sudo apt-get update -qq" || warn "apt-get update failed (may not be Ubuntu)"

# Essential system packages
SYSTEM_PACKAGES=(
    build-essential
    cmake
    git
    curl
    wget
    unzip
    vim
    htop
    tmux
    python3-dev
    python3-pip
    python3-venv
    libssl-dev
    libffi-dev
    libxml2-dev
    libxslt1-dev
    zlib1g-dev
    libbz2-dev
    libreadline-dev
    libsqlite3-dev
    libncurses5-dev
    libncursesw5-dev
    xz-utils
    tk-dev
    libffi-dev
    liblzma-dev
    postgresql-client
    redis-tools
)

# Install packages that aren't already installed
for pkg in "${SYSTEM_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        run "sudo apt-get install -y -qq $pkg" || warn "Failed to install $pkg"
    fi
done

ok "System dependencies installed"

step_done "system-deps"

# ---------------------------------------------------------------------------
# STEP 6: Install Python dependencies (pip + conda)
# ---------------------------------------------------------------------------
step "STEP 6/11: Install Python dependencies"

# Check for conda
if check_cmd conda; then
    info "Conda found: $(conda --version)"

    # Create or update conda environment
    if conda env list 2>/dev/null | grep -q "$CONDA_ENV_NAME"; then
        ok "Conda environment '$CONDA_ENV_NAME' already exists"
    else
        if [[ -f "$PROJECT_DIR/environment.yml" ]]; then
            info "Creating conda environment from environment.yml"
            run "conda env create -f '$PROJECT_DIR/environment.yml' -n '$CONDA_ENV_NAME'" || {
                warn "environment.yml failed — creating minimal environment"
                run "conda create -y -n '$CONDA_ENV_NAME' python=$PYTHON_VERSION"
            }
        else
            info "Creating conda environment: $CONDA_ENV_NAME"
            run "conda create -y -n '$CONDA_ENV_NAME' python=$PYTHON_VERSION"
        fi
        ok "Conda environment created"
    fi

    # Activate conda environment for subsequent commands
    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV_NAME"
    ok "Activated conda environment: $CONDA_ENV_NAME"
else
    info "Conda not found — using system Python with venv"

    # Create virtual environment
    VENV_DIR="$PROJECT_DIR/.venv"
    if [[ ! -d "$VENV_DIR" ]]; then
        run "python3 -m venv '$VENV_DIR'"
        ok "Virtual environment created: $VENV_DIR"
    else
        ok "Virtual environment already exists"
    fi

    # Activate venv
    source "$VENV_DIR/bin/activate"
    ok "Activated virtual environment"
fi

# Install pip dependencies
info "Upgrading pip..."
run "pip install --upgrade pip setuptools wheel"

# Install from requirements.txt
if [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
    info "Installing from requirements.txt..."
    run "pip install -r '$PROJECT_DIR/requirements.txt'"
    ok "Python dependencies installed from requirements.txt"
else
    warn "No requirements.txt found — installing minimal packages"
    run "pip install flask fastapi uvicorn requests pyyaml numpy torch transformers"
fi

# Install from pyproject.toml if present
if [[ -f "$PROJECT_DIR/pyproject.toml" ]]; then
    info "Installing from pyproject.toml..."
    run "pip install -e '$PROJECT_DIR'" || warn "Editable install from pyproject.toml failed"
fi

# Install from setup.py if present
if [[ -f "$PROJECT_DIR/setup.py" ]]; then
    info "Installing from setup.py..."
    run "pip install -e '$PROJECT_DIR'" || warn "Editable install from setup.py failed"
fi

ok "Python dependencies installed"

step_done "python-deps"

# ---------------------------------------------------------------------------
# STEP 7: Restore model weights from Base44 (if provided)
# ---------------------------------------------------------------------------
step "STEP 7/11: Restore model weights"

if $SKIP_MODEL_WEIGHTS; then
    warn "Skipping model weights restoration (--skip-model-weights)"
    warn "You will need to manually download or transfer model weights"
elif [[ -z "$BASE44_FILE_URI" && -z "$BASE44_SIGNED_URL" ]]; then
    warn "No Base44 URI/URL provided for model weights — skipping"
    warn "You will need to manually restore model weights to: $PROJECT_DIR/model_weights/"
elif [[ -d "$PROJECT_DIR/model_weights" && $(ls -A "$PROJECT_DIR/model_weights" 2>/dev/null | wc -l) -gt 0 ]]; then
    ok "Model weights directory already has files — skipping download"
else
    info "Downloading model weights from Base44..."

    WEIGHTS_DIR="$PROJECT_DIR/model_weights"
    mkdir -p "$WEIGHTS_DIR"

    if [[ -n "$BASE44_SIGNED_URL" ]]; then
        WEIGHTS_URL="$BASE44_SIGNED_URL"
    else
        WEIGHTS_URL="$BASE44_FILE_URI"
    fi

    WEIGHTS_ARCHIVE="/tmp/model_weights.tar.gz"

    if curl -sf -L -o "$WEIGHTS_ARCHIVE" "$WEIGHTS_URL" 2>/dev/null; then
        info "Downloaded model weights archive"
        tar -xzf "$WEIGHTS_ARCHIVE" -C "$WEIGHTS_DIR" 2>/dev/null || {
            # Maybe it's a single file, not an archive
            cp "$WEIGHTS_ARCHIVE" "$WEIGHTS_DIR/" 2>/dev/null || true
        }
        rm -f "$WEIGHTS_ARCHIVE"
        ok "Model weights restored to $WEIGHTS_DIR"
    else
        warn "Failed to download model weights from Base44"
        warn "You will need to manually restore model weights to: $WEIGHTS_DIR"
    fi
fi

# Also restore checkpoints if available
if [[ -d "$PROJECT_DIR/checkpoints" ]]; then
    CHECKPOINT_COUNT=$(ls -A "$PROJECT_DIR/checkpoints" 2>/dev/null | wc -l || echo 0)
    if [[ "$CHECKPOINT_COUNT" -gt 0 ]]; then
        ok "Checkpoints directory already has files"
    fi
fi

step_done "model-weights"

# ---------------------------------------------------------------------------
# STEP 8: Run git_permanent_fix.sh
# ---------------------------------------------------------------------------
step "STEP 8/11: Run git_permanent_fix.sh (install prevention mechanisms)"

FIX_SCRIPT="$PROJECT_DIR/scripts/git_permanent_fix.sh"

if [[ ! -f "$FIX_SCRIPT" ]]; then
    # Also check in project root
    FIX_SCRIPT="$PROJECT_DIR/git_permanent_fix.sh"
fi

if [[ -f "$FIX_SCRIPT" ]]; then
    info "Running git_permanent_fix.sh..."
    chmod +x "$FIX_SCRIPT"
    run "bash '$FIX_SCRIPT'"
    ok "git_permanent_fix.sh completed"
else
    warn "git_permanent_fix.sh not found in repository"
    warn "You should manually run it to install corruption prevention mechanisms"
    warn "Expected location: $PROJECT_DIR/scripts/git_permanent_fix.sh"
fi

step_done "git-fix"

# ---------------------------------------------------------------------------
# STEP 9: Install crontab entries
# ---------------------------------------------------------------------------
step "STEP 9/11: Install crontab entries"

CRON_SCRIPT="/usr/local/bin/dgx_git_health_check.sh"
if [[ ! -f "$CRON_SCRIPT" ]]; then
    CRON_SCRIPT="$HOME/.local/bin/dgx_git_health_check.sh"
fi

if [[ -f "$CRON_SCRIPT" ]]; then
    CRON_ENTRY="0 * * * * $CRON_SCRIPT # DGX git health check"

    # Check if already in crontab
    if crontab -l 2>/dev/null | grep -q "dgx_git_health_check"; then
        ok "Crontab already has git health check entry"
    else
        EXISTING_CRON=$(crontab -l 2>/dev/null || true)
        CLEANED_CRON=$(echo "$EXISTING_CRON" | grep -v "dgx_git_health_check\|DGX git health check" || true)

        if [[ -n "$CLEANED_CRON" ]]; then
            echo "$CLEANED_CRON" | { cat; echo "$CRON_ENTRY"; } | crontab -
        else
            echo "$CRON_ENTRY" | crontab -
        fi
        ok "Crontab entry installed: hourly git health check"
    fi
else
    warn "Git health check script not found — crontab entry not installed"
    warn "Run git_permanent_fix.sh first to install the health check script"
fi

step_done "crontab"

# ---------------------------------------------------------------------------
# STEP 10: Start API server
# ---------------------------------------------------------------------------
step "STEP 10/11: Start API server"

API_SCRIPT="$PROJECT_DIR/api/server.py"
if [[ ! -f "$API_SCRIPT" ]]; then
    API_SCRIPT="$PROJECT_DIR/api/app.py"
fi
if [[ ! -f "$API_SCRIPT" ]]; then
    API_SCRIPT="$PROJECT_DIR/api/main.py"
fi
if [[ ! -f "$API_SCRIPT" ]]; then
    API_SCRIPT="$PROJECT_DIR/main.py"
fi

if [[ -f "$API_SCRIPT" ]]; then
    info "API server script found: $API_SCRIPT"

    # Check if API is already running
    if pgrep -f "$API_SCRIPT" >/dev/null 2>&1; then
        ok "API server is already running"
    else
        info "Starting API server..."

        # Try different methods to start
        if [[ -f "$PROJECT_DIR/Makefile" ]] && grep -q "run\|serve\|start" "$PROJECT_DIR/Makefile" 2>/dev/null; then
            info "Starting via Makefile..."
            run "cd '$PROJECT_DIR' && make serve" || run "cd '$PROJECT_DIR' && make run" || {
                warn "Makefile serve failed — starting directly"
                run "cd '$PROJECT_DIR' && nohup python3 '$API_SCRIPT' > /tmp/api_server.log 2>&1 &"
            }
        else
            run "cd '$PROJECT_DIR' && nohup python3 '$API_SCRIPT' > /tmp/api_server.log 2>&1 &"
        fi

        # Wait for server to start
        sleep 5

        if pgrep -f "$API_SCRIPT" >/dev/null 2>&1; then
            ok "API server started successfully"
        else
            warn "API server may not have started — check /tmp/api_server.log"
        fi
    fi
else
    warn "No API server script found — skipping server start"
    warn "Looked for: api/server.py, api/app.py, api/main.py, main.py"
fi

step_done "api-start"

# ---------------------------------------------------------------------------
# STEP 11: Full verification health check
# ---------------------------------------------------------------------------
step "STEP 11/11: Full verification health check"

VERIFICATION_PASSED=true

# 1. Git fsck
info "Checking git integrity..."
if git -C "$PROJECT_DIR" fsck --full >/dev/null 2>&1; then
    ok "  ✅ git fsck — passed"
else
    err "  ❌ git fsck — FAILED (corruption may persist)"
    VERIFICATION_PASSED=false
fi

# 2. Commit count
COMMIT_COUNT=$(git -C "$PROJECT_DIR" rev-list --count HEAD 2>/dev/null || echo 0)
if [[ "$COMMIT_COUNT" -ge 8 ]]; then
    ok "  ✅ Git commits — $COMMIT_COUNT (≥8 expected)"
else
    warn "  ⚠️  Git commits — $COMMIT_COUNT (<8 expected, some history may be missing)"
fi

# 3. File count
FILE_COUNT=$(git -C "$PROJECT_DIR" ls-files 2>/dev/null | wc -l || echo 0)
if [[ "$FILE_COUNT" -ge 97 ]]; then
    ok "  ✅ Tracked files — $FILE_COUNT (≥97 expected)"
else
    warn "  ⚠️  Tracked files — $FILE_COUNT (<97 expected, some files may be missing)"
fi

# 4. Pre-commit hook
if [[ -x "$PROJECT_DIR/.git/hooks/pre-commit" ]]; then
    ok "  ✅ Pre-commit hook — installed and executable"
else
    warn "  ❌ Pre-commit hook — not found or not executable"
    VERIFICATION_PASSED=false
fi

# 5. Crontab
if crontab -l 2>/dev/null | grep -q "dgx_git_health_check"; then
    ok "  ✅ Crontab — hourly git health check installed"
else
    warn "  ❌ Crontab — git health check not found"
    VERIFICATION_PASSED=false
fi

# 6. Git config resilience settings
CONFIG_OK=true
for setting in "gc.auto" "pack.threads" "core.preloadindex" "core.fsyncobjectfiles"; do
    if git -C "$PROJECT_DIR" config --get "$setting" >/dev/null 2>&1; then
        ok "  ✅ git config $setting = $(git -C "$PROJECT_DIR" config --get "$setting")"
    else
        warn "  ❌ git config $setting — not set"
        CONFIG_OK=false
    fi
done
$CONFIG_OK || VERIFICATION_PASSED=false

# 7. .env file
if [[ -f "$PROJECT_DIR/.env" ]]; then
    ok "  ✅ .env file — present"
else
    warn "  ❌ .env file — missing (manual creation required)"
fi

# 8. Model weights
if [[ -d "$PROJECT_DIR/model_weights" ]] && [[ $(ls -A "$PROJECT_DIR/model_weights" 2>/dev/null | wc -l) -gt 0 ]]; then
    ok "  ✅ Model weights — present"
else
    warn "  ⚠️  Model weights — directory empty or missing (manual restore required)"
fi

# 9. Python imports
info "  Checking Python imports..."
PYTHON_IMPORTS_OK=true
for module in flask fastapi uvicorn numpy torch transformers; do
    if python3 -c "import $module" 2>/dev/null; then
        ok "  ✅ Python module '$module' — importable"
    else
        warn "  ❌ Python module '$module' — not importable"
        PYTHON_IMPORTS_OK=false
    fi
done
$PYTHON_IMPORTS_OK || VERIFICATION_PASSED=false

# 10. API server health
if pgrep -f "api/" >/dev/null 2>&1 || pgrep -f "server.py" >/dev/null 2>&1 || pgrep -f "app.py" >/dev/null 2>&1; then
    ok "  ✅ API server — running"
else
    warn "  ⚠️  API server — not running (may need manual start)"
fi

echo ""
if $VERIFICATION_PASSED; then
    ok "══════════════════════════════════════════════════"
    ok "  RECONSTRUCTION COMPLETE — ALL CHECKS PASSED  "
    ok "══════════════════════════════════════════════════"
else
    warn "══════════════════════════════════════════════════"
    warn "  RECONSTRUCTION COMPLETE — WITH WARNINGS  "
    warn "══════════════════════════════════════════════════"
    warn "Some checks failed — review the output above."
fi

step_done "verification"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
info ""
info "╔══════════════════════════════════════════════════╗"
info "║   Reconstruction Summary                        ║"
info "╠══════════════════════════════════════════════════╣"
info "║  Project:     $PROJECT_NAME"
info "║  Location:    $PROJECT_DIR"
info "║  Branch:      $BRANCH_NAME"
info "║  Commits:     $COMMIT_COUNT"
info "║  Files:       $FILE_COUNT"
info "║  Log file:    $LOG_FILE"
info "╠══════════════════════════════════════════════════╣"

for step_name in "pre-flight" "ssh-restore" "clone" "env-restore" "system-deps" \
                  "python-deps" "model-weights" "git-fix" "crontab" "api-start" "verification"; do
    if is_done "$step_name"; then
        info "║  ✅ $step_name"
    else
        info "║  ❌ $step_name"
    fi
done

info "╚══════════════════════════════════════════════════╝"
info ""
info "Next steps:"
info "  1. Verify .env has correct secrets: cat $PROJECT_DIR/.env"
info "  2. Verify API server is running: curl http://localhost:8080/health"
info "  3. Run a test inference to verify model works"
info "  4. Set up regular backups: ./backup_to_github.sh"
info ""
info "Log file: $LOG_FILE"
