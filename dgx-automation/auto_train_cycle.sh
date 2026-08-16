#!/usr/bin/env bash
# ============================================================================
# auto_train_cycle.sh — Automated Training Pipeline for Othaiim-12B
# ============================================================================
# Detects when training completes, gathers new data from ChatMessage logs,
# successful quotes, and conversation history, builds training examples,
# starts the next training cycle, merges LoRA weights, creates a new Ollama
# model, restarts the agent, and pushes to GitHub.
#
# Requirements:
#   pip install unsloth datasets transformers peft trl
#   ollama (running)
#   Python 3.10+
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
export OTHAIIM_HOME="${OTHAIIM_HOME:-$HOME/othaiim-12b}"
export AUTOMATION_DIR="${OTHAIIM_HOME}/automation"
export LOG_DIR="${AUTOMATION_DIR}/logs"
export DATA_DIR="${OTHAIIM_HOME}/data"
export MODELS_DIR="${OTHAIIM_HOME}/models"
export TRAINING_DIR="${OTHAIIM_HOME}/training"
export DATASETS_DIR="${TRAINING_DIR}/datasets"

# Service endpoints
AGENT_PORT="${AGENT_PORT:-8878}"
BASE44_API="${BASE44_API:-http://localhost:8890}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# Models
BASE_MODEL="qwen2.5:7b"
CODER_MODEL="qwen2.5-coder:7b"
EMBED_MODEL="embeddinggemma"

# LoRA training config
LORA_RANK="${LORA_RANK:-32}"
LORA_ALPHA="${LORA_ALPHA:-64}"
LORA_DROPOUT=0.05
TRAIN_EPOCHS="${TRAIN_EPOCHS:-3}"
LEARNING_RATE="2e-4"
MAX_SEQ_LEN="${MAX_SEQ_LEN:-4096}"
BATCH_SIZE=2
GRAD_ACCUM=4

# Ollama model naming
MODEL_PREFIX="othaiim"
MODEL_TAG="latest"

# GitHub
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

# Cycle ID
CYCLE_ID="${2:-$(date +%Y%m%d_%H%M%S)}"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log() {
    local level="$1"; shift
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] [$level] $*" | tee -a "${LOG_DIR}/training_${CYCLE_ID}.log"
}
info()  { log "INFO" "$*"; }
warn()  { log "WARN" "$*"; }
error() { log "ERROR" "$*"; }

# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------
ensure_dirs() {
    mkdir -p \
        "$AUTOMATION_DIR" "$LOG_DIR" "$DATA_DIR" "$MODELS_DIR" \
        "$TRAINING_DIR" "$DATASETS_DIR" "${MODELS_DIR}/lora" "${MODELS_DIR}/merged"
}

# ---------------------------------------------------------------------------
# Step 1: Detect if training is currently running
# ---------------------------------------------------------------------------
is_training_running() {
    local pid
    pid=$(pgrep -f "unsloth.*train\|train_othaiim\|sft_trainer\|auto_train" | head -1 || true)
    if [[ -n "$pid" && "$pid" != "$$" ]]; then
        return 0  # training is running
    fi
    return 1  # not running
}

wait_for_training() {
    local max_wait=3600  # 1 hour max
    local waited=0
    while is_training_running; do
        sleep 30
        waited=$((waited + 30))
        if (( waited >= max_wait )); then
            warn "Waited ${max_wait}s for existing training — proceeding anyway."
            return 1
        fi
        info "Waiting for existing training to finish... (${waited}s)"
    done
    info "No training running — proceeding."
    return 0
}

# ---------------------------------------------------------------------------
# Step 2: Gather training data from multiple sources
# ---------------------------------------------------------------------------
gather_training_data() {
    info "=== Gathering training data ==="

    local data_file="${DATASETS_DIR}/train_${CYCLE_ID}.jsonl"
    local raw_dir="${DATA_DIR}/raw_${CYCLE_ID}"
    mkdir -p "$raw_dir"

    local total_examples=0

    # 2a. Gather ChatMessage logs from Base44 API
    info "Fetching ChatMessage logs from Base44 API..."
    local chat_file="${raw_dir}/chat_messages.json"
    if curl -s "${BASE44_API}/api/entities/ChatMessage?limit=500" -o "$chat_file" 2>/dev/null; then
        local count
        count=$(jq '. | length' "$chat_file" 2>/dev/null || echo "0")
        info "  Retrieved $count ChatMessage records"
    else
        warn "  Could not fetch ChatMessage logs from Base44 API"
        echo "[]" > "$chat_file"
    fi

    # 2b. Gather successful quotes/interactions
    info "Fetching successful quote interactions..."
    local quotes_file="${raw_dir}/quotes.json"
    if curl -s "${BASE44_API}/api/entities/Quote?limit=200" -o "$quotes_file" 2>/dev/null; then
        local qcount
        qcount=$(jq '. | length' "$quotes_file" 2>/dev/null || echo "0")
        info "  Retrieved $qcount Quote records"
    else
        warn "  Could not fetch Quote records"
        echo "[]" > "$quotes_file"
    fi

    # 2c. Gather conversation history from agent
    info "Fetching conversation history from agent..."
    local conv_file="${raw_dir}/conversations.json"
    if curl -s "http://localhost:${AGENT_PORT}/api/conversations?limit=200" -o "$conv_file" 2>/dev/null; then
        local ccount
        ccount=$(jq '. | length' "$conv_file" 2>/dev/null || echo "0")
        info "  Retrieved $ccount conversation records"
    else
        warn "  Could not fetch conversation history"
        echo "[]" > "$conv_file"
    fi

    # 2d. Gather local conversation logs
    info "Scanning local log files..."
    local local_logs_file="${raw_dir}/local_logs.jsonl"
    find "${OTHAIIM_HOME}/logs" "${AUTOMATION_DIR}/logs" -name "*.log" -newer "${DATASETS_DIR}/last_train_marker" 2>/dev/null \
        | head -50 > /dev/null || true
    # Touch marker for next cycle
    touch "${DATASETS_DIR}/last_train_marker"

    # 2e. Build training examples using Python script
    info "Building training examples from gathered data..."
    python3 - << 'PYEOF'
import json
import os
import sys
import random
from pathlib import Path

cycle_id = os.environ.get("CYCLE_ID", "unknown")
raw_dir = Path(os.environ["RAW_DIR"]) if "RAW_DIR" in os.environ else Path(f"data/raw_{cycle_id}")
output_file = Path(os.environ["OUTPUT_FILE"]) if "OUTPUT_FILE" in os.environ else Path(f"training/datasets/train_{cycle_id}.jsonl")

output_file.parent.mkdir(parents=True, exist_ok=True)

examples = []

def load_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "items" in data:
            return data["items"]
        return []
    except Exception:
        return []

# --- Source 1: ChatMessage logs ---
chat_file = raw_dir / "chat_messages.json"
chat_messages = load_json(chat_file)

# Group messages by conversation_id
conversations = {}
for msg in chat_messages:
    conv_id = msg.get("conversation_id", msg.get("sessionId", "default"))
    conversations.setdefault(conv_id, []).append(msg)

for conv_id, msgs in conversations.items():
    msgs.sort(key=lambda m: m.get("timestamp", m.get("created_date", "")))

    # Build instruction-response pairs
    for i in range(0, len(msgs) - 1, 2):
        user_msg = msgs[i] if msgs[i].get("role", msgs[i].get("sender")) in ("user", "human") else None
        if not user_msg:
            # Try to find the user message
            for m in msgs[i:i+2]:
                role = m.get("role", m.get("sender", ""))
                if role in ("user", "human"):
                    user_msg = m
                    break

        if not user_msg:
            continue

        # Find the assistant response
        assistant_msg = None
        for m in msgs[i+1:i+3]:
            role = m.get("role", m.get("sender", ""))
            if role in ("assistant", "bot", "ai"):
                assistant_msg = m
                break

        if not assistant_msg:
            continue

        instruction = user_msg.get("content", user_msg.get("text", user_msg.get("message", "")))
        response = assistant_msg.get("content", assistant_msg.get("text", assistant_msg.get("message", "")))

        if instruction and response and len(instruction) > 5 and len(response) > 10:
            examples.append({
                "instruction": instruction,
                "input": "",
                "output": response,
                "source": "chat_log",
                "conversation_id": conv_id
            })

print(f"  From ChatMessages: {len([e for e in examples if e['source'] == 'chat_log'])} examples")

# --- Source 2: Successful quotes ---
quotes_file = raw_dir / "quotes.json"
quotes = load_json(quotes_file)

for quote in quotes:
    # Transform quote into instruction-response pair
    customer_req = quote.get("request", quote.get("customer_request", quote.get("query", "")))
    quote_text = quote.get("quote_text", quote.get("response", quote.get("quote", "")))

    if customer_req and quote_text:
        examples.append({
            "instruction": f"Generate a quote for: {customer_req}",
            "input": "",
            "output": quote_text,
            "source": "successful_quote"
        })

print(f"  From Quotes: {len([e for e in examples if e['source'] == 'successful_quote'])} examples")

# --- Source 3: Conversation history ---
conv_file = raw_dir / "conversations.json"
conversations_data = load_json(conv_file)

for conv in conversations_data:
    messages = conv.get("messages", conv.get("turns", []))
    for i in range(0, len(messages) - 1, 2):
        user = messages[i] if isinstance(messages[i], dict) else {"content": str(messages[i])}
        assistant = messages[i+1] if isinstance(messages[i+1], dict) else {"content": str(messages[i+1])}

        user_role = user.get("role", user.get("sender", ""))
        asst_role = assistant.get("role", assistant.get("sender", ""))

        if user_role in ("user", "human") and asst_role in ("assistant", "bot", "ai"):
            instruction = user.get("content", user.get("text", ""))
            output = assistant.get("content", assistant.get("text", ""))
            if instruction and output and len(instruction) > 5 and len(output) > 10:
                examples.append({
                    "instruction": instruction,
                    "input": "",
                    "output": output,
                    "source": "conversation_history"
                })

print(f"  From Conversations: {len([e for e in examples if e['source'] == 'conversation_history'])} examples")

# --- Source 4: Synthetic instruction-response pairs from logs ---
# Parse conversation logs for Q&A patterns
log_dir = raw_dir.parent / "logs"
if log_dir.exists():
    for log_file in log_dir.glob("*.log"):
        try:
            content = log_file.read_text(errors="ignore")
            # Find Q&A patterns in logs
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if "User:" in line or "Question:" in line:
                    q = line.split(":", 1)[-1].strip()
                    if i + 1 < len(lines):
                        a_line = lines[i + 1]
                        if "Assistant:" in a_line or "Answer:" in a_line or "Response:" in a_line:
                            a = a_line.split(":", 1)[-1].strip()
                            if q and a and len(q) > 5 and len(a) > 10:
                                examples.append({
                                    "instruction": q,
                                    "input": "",
                                    "output": a,
                                    "source": "log_file"
                                })
        except Exception:
            pass

print(f"  From Log files: {len([e for e in examples if e['source'] == 'log_file'])} examples")

# --- Deduplicate ---
seen = set()
unique_examples = []
for ex in examples:
    key = hash(ex["instruction"] + ex["output"])
    if key not in seen:
        seen.add(key)
        unique_examples.append(ex)

# --- Quality filter: remove very short or very long examples ---
filtered = []
for ex in unique_examples:
    output_len = len(ex["output"])
    if 20 < output_len < 8000:  # reasonable length
        filtered.append(ex)

# --- Format for unsloth (Alpaca-style) ---
with open(output_file, "w") as f:
    for ex in filtered:
        # Build the alpaca prompt format
        prompt = f"### Instruction:\n{ex['instruction']}\n\n"
        if ex.get("input"):
            prompt += f"### Input:\n{ex['input']}\n\n"
        prompt += f"### Response:\n{ex['output']}"
        f.write(json.dumps({"text": prompt, **{k: v for k, v in ex.items() if k != "instruction" and k != "input" and k != "output"}}) + "\n")

print(f"\nTotal: {len(examples)} raw -> {len(unique_examples)} unique -> {len(filtered)} filtered")
print(f"Written to: {output_file}")
PYEOF

    # Pass env vars to Python script
    RAW_DIR="$raw_dir" OUTPUT_FILE="$data_file" CYCLE_ID="$CYCLE_ID" \
        python3 - << 'PYEOF'
import json, os, sys, random
from pathlib import Path

raw_dir = Path(os.environ["RAW_DIR"])
output_file = Path(os.environ["OUTPUT_FILE"])
output_file.parent.mkdir(parents=True, exist_ok=True)

examples = []

def load_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list): return data
        elif isinstance(data, dict) and "items" in data: return data["items"]
        return []
    except Exception:
        return []

# ChatMessage logs -> instruction-response pairs
chat_messages = load_json(raw_dir / "chat_messages.json")
conversations = {}
for msg in chat_messages:
    conv_id = msg.get("conversation_id", msg.get("sessionId", "default"))
    conversations.setdefault(conv_id, []).append(msg)

for conv_id, msgs in conversations.items():
    msgs.sort(key=lambda m: m.get("timestamp", m.get("created_date", "")))
    for i in range(0, len(msgs) - 1, 2):
        user_msg = msgs[i] if msgs[i].get("role", msgs[i].get("sender")) in ("user", "human") else None
        if not user_msg:
            for m in msgs[i:i+2]:
                if m.get("role", m.get("sender", "")) in ("user", "human"):
                    user_msg = m; break
        if not user_msg: continue
        assistant_msg = None
        for m in msgs[i+1:i+3]:
            if m.get("role", m.get("sender", "")) in ("assistant", "bot", "ai"):
                assistant_msg = m; break
        if not assistant_msg: continue
        instruction = user_msg.get("content", user_msg.get("text", user_msg.get("message", "")))
        response = assistant_msg.get("content", assistant_msg.get("text", assistant_msg.get("message", "")))
        if instruction and response and len(instruction) > 5 and len(response) > 10:
            examples.append({"instruction": instruction, "input": "", "output": response, "source": "chat_log"})

# Quotes
quotes = load_json(raw_dir / "quotes.json")
for q in quotes:
    req = q.get("request", q.get("customer_request", q.get("query", "")))
    resp = q.get("quote_text", q.get("response", q.get("quote", "")))
    if req and resp:
        examples.append({"instruction": f"Generate a quote for: {req}", "input": "", "output": resp, "source": "quote"})

# Conversations
convs = load_json(raw_dir / "conversations.json")
for conv in convs:
    messages = conv.get("messages", conv.get("turns", []))
    for i in range(0, len(messages) - 1, 2):
        u = messages[i] if isinstance(messages[i], dict) else {"content": str(messages[i])}
        a = messages[i+1] if isinstance(messages[i+1], dict) else {"content": str(messages[i+1])}
        if u.get("role", u.get("sender", "")) in ("user", "human") and a.get("role", a.get("sender", "")) in ("assistant", "bot", "ai"):
            inst = u.get("content", u.get("text", ""))
            out = a.get("content", a.get("text", ""))
            if inst and out and len(inst) > 5 and len(out) > 10:
                examples.append({"instruction": inst, "input": "", "output": out, "source": "conversation"})

# Deduplicate
seen = set()
unique = []
for ex in examples:
    key = hash(ex["instruction"] + ex["output"])
    if key not in seen:
        seen.add(key); unique.append(ex)

# Quality filter
filtered = [e for e in unique if 20 < len(e["output"]) < 8000]

# Write JSONL in Alpaca format
with open(output_file, "w") as f:
    for ex in filtered:
        prompt = f"### Instruction:\n{ex['instruction']}\n\n### Response:\n{ex['output']}"
        f.write(json.dumps({"text": prompt}) + "\n")

print(f"Total: {len(examples)} raw -> {len(unique)} unique -> {len(filtered)} filtered")
print(f"Written to: {output_file}")
PYEOF

    total_examples=$(wc -l < "$data_file" 2>/dev/null || echo "0")
    info "Total training examples: $total_examples"

    if (( total_examples < 10 )); then
        warn "Too few training examples ($total_examples) — adding synthetic data..."
        generate_synthetic_data "$data_file"
        total_examples=$(wc -l < "$data_file")
        info "After synthetic augmentation: $total_examples examples"
    fi

    echo "$data_file"
}

# ---------------------------------------------------------------------------
# Generate synthetic training data when real data is scarce
# ---------------------------------------------------------------------------
generate_synthetic_data() {
    local data_file="$1"
    info "Generating synthetic training data using Ollama..."

    python3 - << PYEOF
import json, os, requests, sys

ollama = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
output_file = "${data_file}"
model = "qwen2.5:3b"  # use light model for speed

topics = [
    "Explain how to create a REST API endpoint",
    "Write a function to validate email addresses",
    "Describe the benefits of using TypeScript",
    "Explain database normalization",
    "Write a React component for a todo list",
    "Explain the difference between SQL and NoSQL",
    "Write a Python function to parse JSON",
    "Explain how JWT authentication works",
    "Write a SQL query to join two tables",
    "Explain the SOLID principles",
    "Write a function to generate a UUID",
    "Explain how to handle errors in async/await",
    "Write a CSS flexbox layout for a card grid",
    "Describe how to implement rate limiting",
    "Write a function to debounce API calls",
    "Explain the difference between REST and GraphQL",
    "Write a Docker Compose file for a web app",
    "Explain how to implement pagination in an API",
    "Write a regex to validate phone numbers",
    "Describe best practices for API security",
]

existing = 0
try:
    with open(output_file) as f:
        existing = sum(1 for _ in f)
except FileNotFoundError:
    pass

with open(output_file, "a") as f:
    for topic in topics:
        try:
            resp = requests.post(f"{ollama}/api/generate", json={
                "model": model,
                "prompt": f"Provide a detailed, helpful answer: {topic}",
                "stream": False,
                "options": {"temperature": 0.5, "num_ctx": 2048}
            }, timeout=60)
            if resp.status_code == 200:
                answer = resp.json().get("response", "")
                if answer and len(answer) > 50:
                    prompt = f"### Instruction:\n{topic}\n\n### Response:\n{answer}"
                    f.write(json.dumps({"text": prompt}) + "\n")
        except Exception as e:
            print(f"  Skip '{topic}': {e}", file=sys.stderr)

print(f"Synthetic data appended to {output_file}")
PYEOF
}

# ---------------------------------------------------------------------------
# Step 3: Run training with unsloth + LoRA
# ---------------------------------------------------------------------------
run_training() {
    local data_file="$1"
    local lora_output="${MODELS_DIR}/lora/${CYCLE_ID}"
    mkdir -p "$lora_output"

    info "=== Starting training with unsloth + LoRA ==="
    info "Data file: $data_file"
    info "LoRA output: $lora_output"
    info "Base model: $BASE_MODEL"
    info "LoRA rank: $LORA_RANK, alpha: $LORA_ALPHA, epochs: $TRAIN_EPOCHS"

    python3 - << PYEOF
import json
import os
import sys
from pathlib import Path

data_file = "${data_file}"
lora_output = "${lora_output}"
base_model_hf = "Qwen/Qwen2.5-7B-Instruct"  # HuggingFace model ID
lora_rank = int("${LORA_RANK}")
lora_alpha = int("${LORA_ALPHA}")
lora_dropout = float("${LORA_DROPOUT}")
epochs = int("${TRAIN_EPOCHS}")
lr = float("${LEARNING_RATE}")
max_seq = int("${MAX_SEQ_LEN}")
batch_size = int("${BATCH_SIZE}")
grad_accum = int("${GRAD_ACCUM}")

print(f"Loading unsloth...")
try:
    from unsloth import FastLanguageModel
    from datasets import Dataset
    from transformers import TrainingArguments
except ImportError as e:
    print(f"ERROR: Required libraries not installed: {e}")
    print("Install with: pip install unsloth datasets transformers peft trl")
    sys.exit(1)

print(f"Loading base model: {base_model_hf}")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=base_model_hf,
    max_seq_length=max_seq,
    dtype=None,  # auto-detect
    load_in_4bit=True,
)

print(f"Adding LoRA adapters (rank={lora_rank}, alpha={lora_alpha})")
model = FastLanguageModel.get_peft_model(
    model,
    r=lora_rank,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=lora_alpha,
    lora_dropout=lora_dropout,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
    use_rslora=False,
    loftq_config=None,
)

# Load training data
print(f"Loading training data from {data_file}")
with open(data_file) as f:
    data = [json.loads(line) for line in f if line.strip()]

if not data:
    print("ERROR: No training data found")
    sys.exit(1)

dataset = Dataset.from_list(data)

# Format using the model's chat template
def formatting_prompts_func(examples):
    return {"text": examples["text"]}

dataset = dataset.map(formatting_prompts_func, batched=True)

print(f"Training on {len(dataset)} examples for {epochs} epochs")

# Set up trainer
from trl import SFTTrainer

training_args = TrainingArguments(
    per_device_train_batch_size=batch_size,
    gradient_accumulation_steps=grad_accum,
    warmup_ratio=0.1,
    num_train_epochs=epochs,
    learning_rate=lr,
    fp16=not torch.cuda.is_bf16_supported() if "torch" in sys.modules else True,
    bf16=torch.cuda.is_bf16_supported() if "torch" in sys.modules else False,
    logging_steps=10,
    optim="adamw_8bit",
    weight_decay=0.01,
    lr_scheduler_type="cosine",
    seed=3407,
    output_dir=lora_output,
    save_strategy="epoch",
    report_to="none",
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq,
    args=training_args,
    packing=False,
)

print("Starting training...")
trainer.train()

print(f"Saving LoRA adapter to {lora_output}")
model.save_pretrained(lora_output)
tokenizer.save_pretrained(lora_output)

# Save training stats
stats = {
    "cycle_id": "${CYCLE_ID}",
    "base_model": base_model_hf,
    "lora_rank": lora_rank,
    "lora_alpha": lora_alpha,
    "epochs": epochs,
    "examples": len(dataset),
    "lora_path": lora_output,
    "timestamp": "$(date -Iseconds)",
}
stats_file = Path(lora_output) / "training_stats.json"
with open(stats_file, "w") as f:
    json.dump(stats, f, indent=2)

print("Training complete!")
PYEOF

    local train_status=$?
    if (( train_status != 0 )); then
        error "Training failed with exit code $train_status"
        return $train_status
    fi

    info "Training completed successfully."
    echo "$lora_output"
}

# ---------------------------------------------------------------------------
# Step 4: Merge LoRA weights and create Ollama model
# ---------------------------------------------------------------------------
merge_and_create_model() {
    local lora_path="$1"
    local merged_path="${MODELS_DIR}/merged/${CYCLE_ID}"
    mkdir -p "$merged_path"

    info "=== Merging LoRA weights ==="
    info "LoRA path: $lora_path"
    info "Merged output: $merged_path"

    python3 - << PYEOF
import json
import os
import sys
from pathlib import Path

lora_path = "${lora_path}"
merged_path = "${merged_path}"
base_model_hf = "Qwen/Qwen2.5-7B-Instruct"

try:
    from unsloth import FastLanguageModel
except ImportError:
    print("ERROR: unsloth not installed")
    sys.exit(1)

print(f"Loading LoRA model from {lora_path}")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=base_model_hf,
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,
)

# Load LoRA adapter
from peft import PeftModel
model = PeftModel.from_pretrained(model, lora_path)

print("Merging LoRA weights into base model...")
model = model.merge_and_unload()

print(f"Saving merged model to {merged_path}")
model.save_pretrained(merged_path)
tokenizer.save_pretrained(merged_path)

# Create a Modelfile for Ollama
modelfile_content = f"""FROM {merged_path}

TEMPLATE \"\"\"{{{{ if .System }}}{{{{ .System }}}}{{{{ end }}}}<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
<|im_start|>assistant
{{{{ .Response }}}}<|im_end|>\"\"\"

PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER temperature 0.7
PARAMETER top_p 0.8
PARAMETER num_ctx 4096

SYSTEM \"\"\"You are Othaiim-12B, a helpful AI assistant specialized in software development, quotes, and technical guidance. You provide clear, accurate, and actionable responses.\"\"\"
"""

modelfile_path = Path(merged_path) / "Modelfile"
modelfile_path.write_text(modelfile_content)
print(f"Modelfile created at {modelfile_path}")
print("Merge complete!")
PYEOF

    if (( $? != 0 )); then
        error "LoRA merge failed"
        return 1
    fi

    info "=== Creating new Ollama model ==="
    local new_model_name="${MODEL_PREFIX}:${MODEL_TAG}"

    # Create model from Modelfile
    if ollama create "$new_model_name" -f "${merged_path}/Modelfile" 2>&1 | tee -a "${LOG_DIR}/training_${CYCLE_ID}.log"; then
        info "New Ollama model created: $new_model_name"
    else
        error "Failed to create Ollama model"
        return 1
    fi

    # Also create a versioned model
    local versioned_name="${MODEL_PREFIX}:${CYCLE_ID}"
    ollama create "$versioned_name" -f "${merged_path}/Modelfile" 2>/dev/null \
        && info "Versioned model created: $versioned_name" \
        || warn "Could not create versioned model"

    echo "$new_model_name"
}

# ---------------------------------------------------------------------------
# Step 5: Restart the agent with the new model
# ---------------------------------------------------------------------------
restart_agent() {
    local new_model="$1"
    info "=== Restarting agent with new model: $new_model ==="

    # Try to find and restart the agent process
    local agent_pid
    agent_pid=$(pgrep -f "python.*agent\|uvicorn.*8878\|gunicorn.*8878" | head -1 || true)

    if [[ -n "$agent_pid" ]]; then
        info "Stopping current agent (PID $agent_pid)..."
        kill "$agent_pid" 2>/dev/null || true
        sleep 3
        # Force kill if still running
        kill -9 "$agent_pid" 2>/dev/null || true
        sleep 2
    fi

    # Update agent config to use new model
    local config_file="${OTHAIIM_HOME}/config/agent_config.yaml"
    if [[ -f "$config_file" ]]; then
        sed -i "s|model:.*|model: ${new_model}|" "$config_file" 2>/dev/null \
            && info "Updated agent config with new model" \
            || warn "Could not update agent config"
    fi

    # Restart agent
    local agent_script="${OTHAIIM_HOME}/agent_server.py"
    if [[ -f "$agent_script" ]]; then
        nohup python3 "$agent_script" --port "$AGENT_PORT" --model "$new_model" \
            > "${LOG_DIR}/agent_restart_${CYCLE_ID}.log" 2>&1 &
        local new_pid=$!
        info "Agent restarted with PID $new_pid on port $AGENT_PORT using model $new_model"

        # Wait for it to come up
        sleep 5
        if curl -s "http://localhost:${AGENT_PORT}/" >/dev/null 2>&1; then
            info "Agent is responding on port $AGENT_PORT ✓"
        else
            warn "Agent may not be responding yet — check logs"
        fi
    else
        warn "Agent script not found at $agent_script — manual restart needed"
    fi
}

# ---------------------------------------------------------------------------
# Step 6: Push everything to GitHub
# ---------------------------------------------------------------------------
push_to_github() {
    info "=== Pushing to GitHub ==="
    cd "$OTHAIIM_HOME"

    git config user.name >/dev/null 2>&1 || git config user.name "DGX Automation"
    git config user.email >/dev/null 2>&1 || git config user.email "aiidentificationmachines@gmail.com"

    # Add training artifacts
    git add -A 2>/dev/null || true

    if git diff --cached --quiet; then
        info "No changes to commit."
        return 0
    fi

    git commit -m "Training cycle ${CYCLE_ID}: new LoRA weights + merged model

- LoRA rank: $LORA_RANK, alpha: $LORA_ALPHA
- Epochs: $TRAIN_EPOCHS
- Base model: $BASE_MODEL
- New Ollama model: ${MODEL_PREFIX}:${MODEL_TAG}
- Data: training/datasets/train_${CYCLE_ID}.jsonl

Auto-generated by auto_train_cycle.sh
" 2>/dev/null || warn "Git commit failed"

    git push origin "$GITHUB_BRANCH" 2>/dev/null \
        && info "Pushed to GitHub" \
        || warn "Git push failed — will retry next cycle"
}

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cycle-id) CYCLE_ID="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: $0 [--cycle-id ID]"
                exit 0 ;;
            *) shift ;;
        esac
    done

    ensure_dirs

    info "╔════════════════════════════════════════════╗"
    info "║  Auto Training Cycle — $CYCLE_ID  ║"
    info "╚════════════════════════════════════════════╝"

    # Step 1: Wait for any existing training to finish
    wait_for_training || warn "Proceeding despite existing training"

    # Step 2: Gather training data
    local data_file
    data_file=$(gather_training_data)

    # Step 3: Run training
    local lora_path
    lora_path=$(run_training "$data_file") || {
        error "Training failed — aborting cycle"
        push_to_github  # still push any data changes
        exit 1
    }

    # Step 4: Merge LoRA and create Ollama model
    local new_model
    new_model=$(merge_and_create_model "$lora_path") || {
        error "Model merge/creation failed"
        push_to_github
        exit 1
    }

    # Step 5: Restart agent with new model
    restart_agent "$new_model"

    # Step 6: Push to GitHub
    push_to_github

    # Record cycle completion
    echo "$CYCLE_ID" > "${TRAINING_DIR}/last_completed_cycle.txt"
    echo "{\"cycle_id\": \"${CYCLE_ID}\", \"model\": \"${new_model}\", \"timestamp\": \"$(date -Iseconds)\", \"status\": \"complete\"}" \
        > "${TRAINING_DIR}/last_cycle_report.json"

    info "╔════════════════════════════════════════════╗"
    info "║  Training cycle ${CYCLE_ID} COMPLETE          ║"
    info "║  New model: ${new_model}                      ║"
    info "╚════════════════════════════════════════════╝"
}

main "$@"
