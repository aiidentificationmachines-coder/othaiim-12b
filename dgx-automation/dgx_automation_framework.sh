#!/usr/bin/env bash
# ============================================================================
# dgx_automation_framework.sh — Master Automation Orchestrator for DGX Spark
# ============================================================================
# Runs on cron every 6 hours. Orchestrates training cycles, GitHub pushes,
# Red Hat audit, technical spec generation, system grading, and email reports.
#
# Environment:
#   - Ubuntu ARM64 (DGX Spark)
#   - Python 3.10+
#   - Ollama running on localhost:11434
#   - Othaiim agent on port 8878
#   - Elite app builder on port 8891
#   - Local Base44 API on port 8890
#   - File server on port 8882
#
# Install:
#   chmod +x dgx_automation_framework.sh
#   crontab -e
#   # Add: 0 */6 * * * /home/$USER/othaiim-12b/automation/dgx_automation_framework.sh >> ~/othaiim-12b/automation/cron.log 2>&1
#
# Requirements:
#   pip install ollama requests pyyaml
#   sudo apt install -y mutt ssmtp jq
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
export OTHAIIM_HOME="${OTHAIIM_HOME:-$HOME/othaiim-12b}"
export AUTOMATION_DIR="${OTHAIIM_HOME}/automation"
export LOG_DIR="${AUTOMATION_DIR}/logs"
export GRADES_DIR="${AUTOMATION_DIR}/grades"
export SPECS_DIR="${AUTOMATION_DIR}/specs"
export DATA_DIR="${AUTOMATION_DIR}/data"
export CONFIG_FILE="${AUTOMATION_DIR}/config.yaml"

# Service endpoints
AGENT_PORT="${AGENT_PORT:-8878}"
BUILDER_PORT="${BUILDER_PORT:-8891}"
BASE44_API_PORT="${BASE44_API_PORT:-8890}"
FILE_SERVER_PORT="${FILE_SERVER_PORT:-8882}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# GitHub
GITHUB_REPO="${GITHUB_REPO:-https://github.com/aiidentificationmachines/othaiim-12b.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

# Email
EMAIL_TO="aiidentificationmachines@gmail.com"
SMTP_CONFIG="${HOME}/.ssmtp/ssmtp.conf"

# Models
CHAT_MODEL="qwen2.5:7b"
CODER_MODEL="qwen2.5-coder:7b"   # pulled via: ollama pull qwen2.5-coder:7b
LIGHT_MODEL="qwen2.5:3b"
HEAVY_MODEL="gpt-oss:120b"
EMBED_MODEL="embeddinggemma"
EMBEDDING_MODEL="${EMBED_MODEL}"

# Training
LORA_RANK=32
LORA_ALPHA=64
TRAINING_EPOCHS=3
MAX_SEQ_LEN=4096

# Runtime flags
DRY_RUN=false
VERBOSE=true
CYCLE_ID="$(date +%Y%m%d_%H%M%S)"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] [$level] $msg" | tee -a "${LOG_DIR}/framework_${CYCLE_ID}.log"
}

info()  { log "INFO" "$*"; }
warn()  { log "WARN" "$*"; }
error() { log "ERROR" "$*"; }
fatal() { log "FATAL" "$*"; exit 1; }

ensure_dirs() {
    mkdir -p "$AUTOMATION_DIR" "$LOG_DIR" "$GRADES_DIR" "$SPECS_DIR" "$DATA_DIR"
}

send_email() {
    local subject="$1"
    local body_file="$2"
    local attachment="${3:-}"

    if [[ ! -f "$SMTP_CONFIG" ]]; then
        warn "SMTP config not found at $SMTP_CONFIG — skipping email."
        return 0
    fi

    local attach_flag=""
    if [[ -n "$attachment" && -f "$attachment" ]]; then
        attach_flag="-a $attachment"
    fi

    echo "$(cat "$body_file")" | mutt -s "$subject" $attach_flag -- "$EMAIL_TO" 2>/dev/null \
        && info "Email sent to $EMAIL_TO" \
        || warn "Email send failed (non-fatal)"
}

http_check() {
    local port="$1"
    local name="$2"
    local resp
    resp=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/" 2>/dev/null || echo "000")
    if [[ "$resp" == "000" ]]; then
        warn "$name (port $port) is NOT responding"
        return 1
    else
        info "$name (port $port) responding with HTTP $resp"
        return 0
    fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

preflight() {
    info "=== Pre-flight checks for cycle $CYCLE_ID ==="

    # Check required commands
    local cmds=(python3 git curl jq ollama)
    for cmd in "${cmds[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            fatal "Required command not found: $cmd"
        fi
    done

    # Check Ollama is alive
    if ! curl -s "$OLLAMA_HOST/api/tags" &>/dev/null; then
        fatal "Ollama is not responding at $OLLAMA_HOST"
    fi
    info "Ollama is live at $OLLAMA_HOST"

    # Check required models
    local models
    models=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}')
    local required_models=("$CHAT_MODEL" "$LIGHT_MODEL" "$EMBED_MODEL")
    for model in "${required_models[@]}"; do
        if echo "$models" | grep -q "$model"; then
            info "Model present: $model"
        else
            warn "Model missing: $model — attempting pull"
            ollama pull "$model" || warn "Could not pull $model"
        fi
    done

    # Check coder model
    if echo "$models" | grep -q "$CODER_MODEL"; then
        info "Coder model present: $CODER_MODEL"
    else
        warn "Coder model missing: $CODER_MODEL — pulling..."
        ollama pull "$CODER_MODEL" || warn "Could not pull $CODER_MODEL"
    fi

    # Check heavy model (optional — may be large)
    if echo "$models" | grep -q "$HEAVY_MODEL"; then
        info "Heavy model present: $HEAVY_MODEL"
    else
        warn "Heavy model missing: $HEAVY_MODEL (optional for this cycle)"
    fi

    # Check service ports
    http_check "$AGENT_PORT" "Othaiim Agent"
    http_check "$BUILDER_PORT" "Elite App Builder"
    http_check "$BASE44_API_PORT" "Base44 API"
    http_check "$FILE_SERVER_PORT" "File Server"

    info "Pre-flight checks complete."
}

# ---------------------------------------------------------------------------
# Training orchestration
# ---------------------------------------------------------------------------

check_training_status() {
    # Look for a running unsloth training process
    local pid
    pid=$(pgrep -f "unsloth.*train\|train_lora\|auto_train_cycle" | head -1 || true)

    if [[ -n "$pid" ]]; then
        info "Training is currently running (PID $pid) — will wait for completion."
        return 1  # training in progress
    fi

    info "No training process detected — ready to start next cycle."
    return 0  # idle
}

run_training_cycle() {
    info "=== Starting automated training cycle ==="

    local train_script="${AUTOMATION_DIR}/auto_train_cycle.sh"

    if [[ ! -x "$train_script" ]]; then
        chmod +x "$train_script" 2>/dev/null || warn "Could not make $train_script executable"
    fi

    if [[ ! -f "$train_script" ]]; then
        warn "Training script not found: $train_script — skipping training."
        return 1
    fi

    # Run in background so we can monitor
    nohup bash "$train_script" --cycle-id "$CYCLE_ID" \
        > "${LOG_DIR}/training_${CYCLE_ID}.log" 2>&1 &

    local train_pid=$!
    info "Training started with PID $train_pid"

    # Wait up to 4 hours (configurable)
    local max_wait=14400  # 4 hours in seconds
    local waited=0
    local wait_interval=30

    while kill -0 "$train_pid" 2>/dev/null; do
        sleep "$wait_interval"
        waited=$((waited + wait_interval))
        if (( waited >= max_wait )); then
            warn "Training exceeded max wait of 4 hours — leaving running in background."
            return 1
        fi
    done

    info "Training cycle completed (waited ${waited}s)"

    # Check exit code
    if wait "$train_pid" 2>/dev/null; then
        info "Training cycle exited successfully."
        return 0
    else
        warn "Training cycle may have had issues — check training log."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# GitHub operations
# ---------------------------------------------------------------------------

git_commit_and_push() {
    info "=== Git commit and push ==="

    cd "$OTHAIIM_HOME"

    # Configure git if needed
    git config user.name >/dev/null 2>&1 || git config user.name "DGX Automation"
    git config user.email >/dev/null 2>&1 || git config user.email "$EMAIL_TO"

    # Stage all changes
    git add -A

    # Check if there's anything to commit
    if git diff --cached --quiet; then
        info "No changes to commit."
        return 0
    fi

    local commit_msg="Auto-commit: Training cycle $CYCLE_ID

- Training data updated
- LoRA weights merged
- Model artifacts updated
- System grade: $(cat "${GRADES_DIR}/latest_score.txt" 2>/dev/null || echo 'N/A')

Generated by dgx_automation_framework.sh
"

    git commit -m "$commit_msg"

    # Push
    if [[ -n "$GITHUB_TOKEN" ]]; then
        local remote_url
        remote_url=$(git remote get-url origin 2>/dev/null || echo "")
        if [[ "$remote_url" == *"github.com"* ]] && [[ "$remote_url" != *"@"* ]]; then
            # Inject token
            git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@${remote_url#https://}"
        fi
    fi

    git push origin "$GITHUB_BRANCH" 2>/dev/null \
        && info "Pushed to GitHub ($GITHUB_BRANCH)" \
        || warn "Git push failed — will retry next cycle"

    # Restore remote URL if we modified it
    if [[ -n "$GITHUB_TOKEN" ]] && [[ -n "$remote_url" ]]; then
        git remote set-url origin "$remote_url" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Red Hat audit
# ---------------------------------------------------------------------------

run_redhat_audit() {
    info "=== Red Hat / Ubuntu System Audit ==="

    local audit_file="${LOG_DIR}/audit_${CYCLE_ID}.txt"

    {
        echo "=============================================="
        echo "DGX System Audit — $(date)"
        echo "Cycle ID: $CYCLE_ID"
        echo "=============================================="
        echo ""

        echo "--- 1. System Info ---"
        uname -a
        echo ""

        echo "--- 2. CPU Info ---"
        lscpu | head -20
        echo ""

        echo "--- 3. Memory ---"
        free -h
        echo ""

        echo "--- 4. Disk Usage ---"
        df -h / /home 2>/dev/null || df -h /
        echo ""

        echo "--- 5. GPU Info ---"
        if command -v nvidia-smi &>/dev/null; then
            nvidia-smi
        else
            echo "nvidia-smi not found (ARM64 DGX Spark)"
        fi
        echo ""

        echo "--- 6. Ollama Models ---"
        ollama list
        echo ""

        echo "--- 7. Running Processes (AI-related) ---"
        ps aux | grep -E "ollama|python|node|unsloth" | grep -v grep
        echo ""

        echo "--- 8. Network Ports ---"
        ss -tlnp 2>/dev/null | grep -E "${AGENT_PORT}|${BUILDER_PORT}|${BASE44_API_PORT}|${FILE_SERVER_PORT}|11434" || \
            netstat -tlnp 2>/dev/null | grep -E "${AGENT_PORT}|${BUILDER_PORT}|${BASE44_API_PORT}|${FILE_SERVER_PORT}|11434"
        echo ""

        echo "--- 9. Docker (if running) ---"
        if command -v docker &>/dev/null; then
            docker ps 2>/dev/null || echo "Docker installed but not running"
        else
            echo "Docker not installed"
        fi
        echo ""

        echo "--- 10. Security Check ---"
        echo "Open ports:"
        ss -tlnp 2>/dev/null | wc -l || echo "N/A"
        echo "Failed SSH attempts (last 24h):"
        journalctl -u ssh --since "24 hours ago" 2>/dev/null | grep -c "Failed password" || echo "0"
        echo ""

        echo "--- 11. Ollama Health ---"
        curl -s "$OLLAMA_HOST/api/tags" | jq '.models | length' 2>/dev/null && echo " models available" || echo "Ollama API check failed"
        echo ""

        echo "--- 12. Training Artifacts ---"
        ls -la "${OTHAIIM_HOME}/models/" 2>/dev/null || echo "No models directory"
        ls -la "${OTHAIIM_HOME}/data/" 2>/dev/null || echo "No data directory"
        echo ""

        echo "--- 13. Automation Log Summary ---"
        echo "Last 10 log entries:"
        tail -10 "${LOG_DIR}/framework_${CYCLE_ID}.log" 2>/dev/null || echo "No log yet"
        echo ""

        echo "=============================================="
        echo "Audit complete: $(date)"
        echo "=============================================="
    } > "$audit_file"

    info "Audit written to $audit_file"
    echo "$audit_file"
}

# ---------------------------------------------------------------------------
# Technical spec + improvement roadmap generation
# ---------------------------------------------------------------------------

generate_tech_spec() {
    info "=== Generating technical spec and improvement roadmap ==="

    local spec_file="${SPECS_DIR}/spec_${CYCLE_ID}.md"
    local grade_file="${GRADES_DIR}/grade_${CYCLE_ID}.json"
    local latest_grade="${GRADES_DIR}/latest_score.txt"

    # Read current grade if available
    local overall_score="N/A"
    if [[ -f "$grade_file" ]]; then
        overall_score=$(jq -r '.overall_score // "N/A"' "$grade_file" 2>/dev/null || echo "N/A")
    fi

    # Use the heavy model for spec generation, fall back to chat model
    local spec_model="$HEAVY_MODEL"
    if ! ollama list 2>/dev/null | grep -q "$spec_model"; then
        spec_model="$CHAT_MODEL"
    fi

    local prompt="You are a senior AI systems architect. Generate a comprehensive technical specification
and improvement roadmap for the Othaiim-12B AI agent system running on DGX Spark.

Current system state:
- Overall grade: $overall_score
- Cycle ID: $CYCLE_ID
- Models: $CHAT_MODEL (chat), $CODER_MODEL (code), $LIGHT_MODEL (fast), $HEAVY_MODEL (reasoning), $EMBED_MODEL (embeddings)
- Training: unsloth + LoRA, rank=$LORA_RANK, alpha=$LORA_ALPHA, epochs=$TRAINING_EPOCHS
- Agent port: $AGENT_PORT, Builder port: $BUILDER_PORT, Base44 API: $BASE44_API_PORT, File server: $FILE_SERVER_PORT
- Framework: multi-file project generation with live preview, RAG over entities, multi-model routing

Generate a markdown document with these sections:
1. Executive Summary
2. Current System Architecture
3. Training Pipeline Status
4. Model Performance Assessment
5. Builder Capabilities Assessment
6. Identified Gaps and Risks
7. Improvement Roadmap (prioritized, with estimated effort)
8. Next Cycle Recommendations
9. Appendix: Metrics and KPIs

Be specific and actionable. Focus on reaching commercial frontier-grade quality."

    info "Generating spec using $spec_model..."

    local response
    response=$(curl -s "$OLLAMA_HOST/api/generate" \
        -d "$(jq -n \
            --arg model "$spec_model" \
            --arg prompt "$prompt" \
            '{model: $model, prompt: $prompt, stream: false, options: {temperature: 0.3, num_ctx: 8192}}')" \
        | jq -r '.response // "Error generating spec"')

    cat > "$spec_file" << EOF
# Othaiim-12B Technical Specification & Improvement Roadmap

**Cycle:** $CYCLE_ID  
**Generated:** $(date)  
**Overall Grade:** $overall_score  

---

$response

---

## Raw Metrics

- Cycle ID: $CYCLE_ID
- Chat Model: $CHAT_MODEL
- Coder Model: $CODER_MODEL
- Light Model: $LIGHT_MODEL
- Heavy Model: $HEAVY_MODEL
- Embedding Model: $EMBED_MODEL
- LoRA Rank: $LORA_RANK, Alpha: $LORA_ALPHA
- Training Epochs: $TRAINING_EPOCHS
- Max Seq Len: $MAX_SEQ_LEN
- Agent Port: $AGENT_PORT
- Builder Port: $BUILDER_PORT
- Base44 API Port: $BASE44_API_PORT
- File Server Port: $FILE_SERVER_PORT

EOF

    info "Technical spec written to $spec_file"
    echo "$spec_file"
}

# ---------------------------------------------------------------------------
# System grading
# ---------------------------------------------------------------------------

run_system_grader() {
    info "=== Running system grader ==="

    local grader_script="${AUTOMATION_DIR}/system_grader.py"
    local grade_file="${GRADES_DIR}/grade_${CYCLE_ID}.json"

    if [[ ! -f "$grader_script" ]]; then
        warn "System grader script not found: $grader_script"
        echo "N/A"
        return
    fi

    python3 "$grader_script" \
        --cycle-id "$CYCLE_ID" \
        --output-dir "$GRADES_DIR" \
        --agent-port "$AGENT_PORT" \
        --builder-port "$BUILDER_PORT" \
        --base44-port "$BASE44_API_PORT" \
        --file-server-port "$FILE_SERVER_PORT" \
        --ollama-host "$OLLAMA_HOST" \
        --chat-model "$CHAT_MODEL" \
        --coder-model "$CODER_MODEL" \
        --light-model "$LIGHT_MODEL" \
        --heavy-model "$HEAVY_MODEL" \
        --embed-model "$EMBED_MODEL" \
        2>&1 | tee -a "${LOG_DIR}/grader_${CYCLE_ID}.log"

    # Extract overall score for latest_score
    if [[ -f "$grade_file" ]]; then
        local score
        score=$(jq -r '.overall_score // "N/A"' "$grade_file" 2>/dev/null || echo "N/A")
        echo "$score" > "${GRADES_DIR}/latest_score.txt"
        info "System grade: $score / 100"
    fi
}

# ---------------------------------------------------------------------------
# Email report
# ---------------------------------------------------------------------------

send_cycle_report() {
    info "=== Sending cycle report email ==="

    local subject="[DGX Automation] Cycle $CYCLE_ID Report"
    local body_file="${LOG_DIR}/email_body_${CYCLE_ID}.txt"
    local grade_file="${GRADES_DIR}/grade_${CYCLE_ID}.json"
    local spec_file="${SPECS_DIR}/spec_${CYCLE_ID}.md"
    local audit_file="${LOG_DIR}/audit_${CYCLE_ID}.txt"

    local overall_score
    overall_score=$(cat "${GRADES_DIR}/latest_score.txt" 2>/dev/null || echo "N/A")

    local grade_letter="N/A"
    if [[ "$overall_score" =~ ^[0-9]+$ ]]; then
        if (( overall_score >= 90 )); then grade_letter="A"
        elif (( overall_score >= 80 )); then grade_letter="B"
        elif (( overall_score >= 70 )); then grade_letter="C"
        elif (( overall_score >= 60 )); then grade_letter="D"
        else grade_letter="F"
        fi
    fi

    cat > "$body_file" << EOF
DGX Automation Framework — Cycle Report
========================================

Cycle ID:      $CYCLE_ID
Timestamp:     $(date)
Overall Grade: $overall_score / 100 ($grade_letter)

--- Pillar Scores ---
EOF

    if [[ -f "$grade_file" ]]; then
        jq -r '.pillars | to_entries[] | "  \(.key): \(.value.score)/100 (\(.value.grade))"' "$grade_file" >> "$body_file" 2>/dev/null
    else
        echo "  Grade file not available" >> "$body_file"
    fi

    cat >> "$body_file" << EOF

--- Cycle Summary ---
- Pre-flight: Completed
- Training: See training log
- Git Push: See framework log
- System Audit: See attached
- Tech Spec: See attached
- System Grade: See attached

--- Key Findings ---
EOF

    # Append improvement roadmap highlights if available
    if [[ -f "$grade_file" ]]; then
        jq -r '.improvement_roadmap[]? | "- \(.)"' "$grade_file" >> "$body_file" 2>/dev/null
    fi

    cat >> "$body_file" << EOF

--- Next Steps ---
1. Review pillar scores below 80
2. Check training log for data quality
3. Review tech spec for roadmap items
4. Monitor next cycle for improvement trends

Logs: ${LOG_DIR}/framework_${CYCLE_ID}.log
Grades: ${GRADES_DIR}/
Specs: ${SPECS_DIR}/

This is an automated message from the DGX Automation Framework.
EOF

    # Send with attachments
    local attachments=""
    [[ -f "$audit_file" ]] && attachments="$attachments -a $audit_file"
    [[ -f "$spec_file" ]] && attachments="$attachments -a $spec_file"
    [[ -f "$grade_file" ]] && attachments="$attachments -a $grade_file"

    if command -v mutt &>/dev/null; then
        echo "$(cat "$body_file")" | mutt -s "$subject" $attachments -- "$EMAIL_TO" 2>/dev/null \
            && info "Email sent to $EMAIL_TO" \
            || warn "Email send failed (non-fatal)"
    else
        warn "mutt not installed — email skipped. Report saved at $body_file"
    fi
}

# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)    DRY_RUN=true; shift ;;
            --cycle-id)   CYCLE_ID="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: $0 [--dry-run] [--cycle-id ID]"
                exit 0 ;;
            *) shift ;;
        esac
    done

    ensure_dirs

    info "╔══════════════════════════════════════════════╗"
    info "║  DGX Automation Framework — Cycle $CYCLE_ID  ║"
    info "╚══════════════════════════════════════════════╝"

    # 1. Pre-flight
    preflight

    if $DRY_RUN; then
        info "DRY RUN — skipping execution steps."
        run_redhat_audit
        generate_tech_spec
        send_cycle_report
        info "Dry run complete."
        exit 0
    fi

    # 2. Check training status & run cycle if idle
    if check_training_status; then
        run_training_cycle || warn "Training cycle had issues — continuing"
    else
        info "Training in progress — will check next cycle."
    fi

    # 3. Git commit and push
    git_commit_and_push

    # 4. Red Hat audit
    local audit_file
    audit_file=$(run_redhat_audit)

    # 5. Run system grader
    run_system_grader

    # 6. Generate technical spec + roadmap
    generate_tech_spec

    # 7. Send email report
    send_cycle_report

    info "╔══════════════════════════════════════════════╗"
    info "║  Cycle $CYCLE_ID COMPLETE                       ║"
    info "╚══════════════════════════════════════════════╝"
}

main "$@"
