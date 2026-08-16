#!/bin/bash
# Rental Guys Equipment Cache Builder
# Fetches sitemap, batch-calls API in parallel, builds a local model index
# Run once to build cache, then refresh weekly

set -e

CACHE_DIR=".rg_cache"
CACHE_FILE="$CACHE_DIR/equipment_index.json"
SITEMAP_FILE="$CACHE_DIR/sitemap_ids.txt"
STAMP_FILE="$CACHE_DIR/last_built.txt"

mkdir -p "$CACHE_DIR"

echo "[1/4] Fetching sitemap..."
SITEMAP=$(curl -s "https://shop.rentalguys.com/api/sitemap")

# Extract equipment IDs
echo "$SITEMAP" | grep -oP '(?<=/equipment/details/)\d+' | sort -u > "$SITEMAP_FILE"
TOTAL=$(wc -l < "$SITEMAP_FILE")
echo "  Found $TOTAL equipment IDs"

echo "[2/4] Batch-fetching equipment details (20 parallel)..."
# Fetch each equipment detail in parallel, extract key fields, filter
> "$CACHE_FILE.tmp"
cat "$SITEMAP_FILE" | xargs -P 20 -I {} bash -c '
  ID="{}"
  RESP=$(curl -s --max-time 5 "https://shop.rentalguys.com/api/equipment/$ID" 2>/dev/null || echo "")
  if [ -n "$RESP" ] && echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get(\"model\",\"\"))" 2>/dev/null; then
    echo "$RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    m = d.get(\"model\",\"\")
    if m:
        entry = {
            \"id\": d.get(\"equipment_number\", \"$ID\")),
            \"year\": d.get(\"year\"),
            \"make\": d.get(\"make\"),
            \"model\": m,
            \"serial\": d.get(\"serial_number\"),
            \"hours\": d.get(\"meter_hours\"),
            \"price\": d.get(\"list_price\"),
            \"city\": d.get(\"branch_city\"),
            \"state\": d.get(\"branch_state\"),
            \"category\": d.get(\"category\")
        }
        print(json.dumps(entry))
except: pass
" 2>/dev/null
  fi
' >> "$CACHE_FILE.tmp" 2>/dev/null

echo "[3/4] Building model index..."
# Convert to proper JSON array and index by model
python3 << 'PYEOF'
import json

entries = []
with open(".rg_cache/equipment_index.json.tmp") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except:
                pass

# Build model index
index = {}
for e in entries:
    model = (e.get("model") or "").upper()
    if not model:
        continue
    if model not in index:
        index[model] = []
    index[model].append(e)

# Sort each model's entries by price ascending
for model in index:
    index[model].sort(key=lambda x: x.get("price") or 999999)

output = {
    "total_equipment": len(entries),
    "total_models": len(index),
    "models": index
}

with open(".rg_cache/equipment_index.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"  Cached {len(entries)} units across {len(index)} models")
PYEOF

echo "[4/4] Writing timestamp..."
date -u > "$STAMP_FILE"
rm -f "$CACHE_FILE.tmp"

echo "Done! Cache at $CACHE_FILE"
echo "Usage: python3 -c \"import json; d=json.load(open('$CACHE_FILE')); print(json.dumps(d['models'].get('E26', []), indent=2))\""
