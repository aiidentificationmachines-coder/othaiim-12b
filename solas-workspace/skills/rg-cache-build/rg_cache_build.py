#!/usr/bin/env python3
"""
Rental Guys Equipment Cache Builder
Fetches sitemap, batch-calls API in parallel, builds a local model index.
Run once to build cache, refresh weekly.

Usage: python3 rg_cache_build.py
Output: .rg_cache/equipment_index.json
"""
import json, os, sys, time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = ".rg_cache"
CACHE_FILE = os.path.join(CACHE_DIR, "equipment_index.json")
STAMP_FILE = os.path.join(CACHE_DIR, "last_built.txt")
SITEMAP_URL = "https://shop.rentalguys.com/api/sitemap"
API_BASE = "https://shop.rentalguys.com/api/equipment/"
BATCH_SIZE = 30  # parallel connections
TIMEOUT = 5  # seconds per API call

os.makedirs(CACHE_DIR, exist_ok=True)

# Step 1: Fetch sitemap
print("[1/4] Fetching sitemap...")
try:
    with urllib.request.urlopen(SITEMAP_URL, timeout=15) as resp:
        sitemap = resp.read().decode("utf-8")
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

import re
ids = list(set(re.findall(r'/equipment/details/(\d+)', sitemap)))
ids.sort(key=int)
print(f"  Found {len(ids)} equipment IDs")

# Step 2: Batch-fetch equipment details
print(f"[2/4] Fetching equipment details ({BATCH_SIZE} parallel, {TIMEOUT}s timeout)...")

def fetch_one(eid):
    try:
        url = f"{API_BASE}{eid}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "id": data.get("equipment_number", eid),
                "year": data.get("year"),
                "make": data.get("make", ""),
                "model": data.get("model", ""),
                "serial": data.get("serial_number", ""),
                "hours": data.get("meter_hours"),
                "price": data.get("list_price"),
                "city": data.get("branch_city", ""),
                "state": data.get("branch_state", ""),
                "category": data.get("category", ""),
                "images": data.get("images", [])
            }
    except Exception:
        return None

results = []
done = 0
total = len(ids)

with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
    futures = {pool.submit(fetch_one, eid): eid for eid in ids}
    for future in as_completed(futures):
        done += 1
        if done % 100 == 0:
            print(f"  Progress: {done}/{total} ({100*done//total}%)")
        r = future.result()
        if r and r.get("model"):
            results.append(r)

print(f"  Fetched {len(results)} valid equipment records")

# Step 3: Build model index
print("[3/4] Building model index...")
index = {}
for e in results:
    model = e.get("model", "").upper().strip()
    if not model:
        continue
    if model not in index:
        index[model] = []
    index[model].append(e)

# Sort each model's entries by price ascending (cheapest first)
for model in index:
    index[model].sort(key=lambda x: x.get("price") or 999999)

output = {
    "total_equipment": len(results),
    "total_models": len(index),
    "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "models": index
}

with open(CACHE_FILE, "w") as f:
    json.dump(output, f, indent=2)

print(f"  Cached {len(results)} units across {len(index)} models")

# Step 4: Write timestamp
print("[4/4] Done!")
with open(STAMP_FILE, "w") as f:
    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

print(f"  Cache: {CACHE_FILE}")
print(f"  Search: python3 -c \"import json; d=json.load(open('{CACHE_FILE}')); print(json.dumps(d['models'].get('E26',[]), indent=2))\"")
