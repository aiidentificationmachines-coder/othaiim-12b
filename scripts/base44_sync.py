#!/usr/bin/env python3
"""
Solas Base44 Sync — Local DGX Edition
Syncs entity data between DGX local storage and Base44 cloud.
Allows the DGX agent to read/write Base44 entities without cloud credits.

Capabilities:
- Read any Base44 entity (Equipment, DealWorksheet, DealerRep, etc.)
- Write/update entities locally and queue sync to Base44
- Offline-first: all operations work locally, sync when online
- Caches entity schemas and records locally as JSON files
"""

import json, os, sys, time, hashlib, urllib.request, urllib.error
from datetime import datetime, timezone

# === Configuration ===
SYNC_DIR = os.path.expanduser("~/othaiim-12b/base44_sync")
os.makedirs(SYNC_DIR, exist_ok=True)
os.makedirs(os.path.join(SYNC_DIR, "cache"), exist_ok=True)
os.makedirs(os.path.join(SYNC_DIR, "queue"), exist_ok=True)

BASE44_APP_ID = "6a5082fce1b132f938a4424b"
PRODUCTION_APP_ID = "69e33f915b549b8e55edf603"

# Try to load API key
API_KEY = os.environ.get("BASE44_API_KEY", "")
env_path = os.path.expanduser("~/othaiim-12b/.env")
if not API_KEY and os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("BASE44_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")

# === Local Cache Manager ===
def get_cache_path(entity_name, app_id=None):
    """Get the local cache file path for an entity."""
    app = app_id or BASE44_APP_ID
    safe_name = entity_name.replace("/", "_")
    return os.path.join(SYNC_DIR, "cache", f"{app}_{safe_name}.json")

def load_cache(entity_name, app_id=None):
    """Load cached entity records."""
    path = get_cache_path(entity_name, app_id)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"records": [], "last_sync": None}

def save_cache(entity_name, data, app_id=None):
    """Save entity records to local cache."""
    path = get_cache_path(entity_name, app_id)
    data["last_sync"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# === Base44 API Client ===
def api_request(method, path, data=None, app_id=None):
    """Make a Base44 API request."""
    app = app_id or BASE44_APP_ID
    url = f"https://api.base44.com/api/apps/{app}/{path}"
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:500]}
    except Exception as e:
        return {"error": str(e)}

def sync_from_base44(entity_name, app_id=None, limit=500):
    """Pull entity records from Base44 to local cache."""
    print(f"  Syncing {entity_name} from Base44...")
    result = api_request("GET", f"entities/{entity_name}?limit={limit}", app_id=app_id)
    
    if "error" in result:
        print(f"    Error: {result['error']}")
        # Return cached version
        return load_cache(entity_name, app_id)
    
    records = result.get("records", [])
    cache = {"records": records, "count": len(records), "last_sync": datetime.now(timezone.utc).isoformat()}
    save_cache(entity_name, cache, app_id)
    print(f"    Cached {len(records)} records")
    return cache

def queue_write(entity_name, record_data, operation="create", record_id=None, app_id=None):
    """Queue a write operation to sync to Base44 later."""
    queue_item = {
        "id": hashlib.md5(f"{entity_name}{time.time()}".encode()).hexdigest()[:12],
        "entity_name": entity_name,
        "operation": operation,  # create, update, delete
        "record_id": record_id,
        "data": record_data,
        "app_id": app_id or BASE44_APP_ID,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    
    queue_path = os.path.join(SYNC_DIR, "queue", f"{queue_item['id']}.json")
    with open(queue_path, "w") as f:
        json.dump(queue_item, f, indent=2)
    
    print(f"  Queued {operation} on {entity_name} (id: {queue_item['id']})")
    return queue_item

def process_queue():
    """Process all pending write operations."""
    queue_dir = os.path.join(SYNC_DIR, "queue")
    if not os.path.exists(queue_dir):
        return
    
    pending = [f for f in os.listdir(queue_dir) if f.endswith(".json")]
    if not pending:
        print("  Queue is empty")
        return
    
    print(f"  Processing {len(pending)} pending operations...")
    
    for fname in pending:
        path = os.path.join(queue_dir, fname)
        with open(path) as f:
            item = json.load(f)
        
        if item["status"] != "pending":
            continue
        
        entity = item["entity_name"]
        op = item["operation"]
        data = item.get("data", {})
        record_id = item.get("record_id")
        app_id = item.get("app_id")
        
        if op == "create":
            result = api_request("POST", f"entities/{entity}", data, app_id)
        elif op == "update" and record_id:
            result = api_request("PATCH", f"entities/{entity}/{record_id}", data, app_id)
        elif op == "delete" and record_id:
            result = api_request("DELETE", f"entities/{entity}/{record_id}", None, app_id)
        else:
            result = {"error": "invalid operation"}
        
        if "error" in result:
            print(f"    FAIL: {op} {entity} — {result['error']}")
            item["status"] = "failed"
            item["error"] = result["error"]
        else:
            print(f"    OK: {op} {entity}")
            item["status"] = "completed"
            item["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        with open(path, "w") as f:
            json.dump(item, f, indent=2)

# === Convenience Functions ===
def list_equipment(app_id=PRODUCTION_APP_ID):
    """List all equipment from production app."""
    cache = sync_from_base44("Equipment", app_id=app_id, limit=500)
    return cache.get("records", [])

def list_deal_worksheets():
    """List all deal worksheets."""
    cache = sync_from_base44("DealWorksheet")
    return cache.get("records", [])

def list_dealer_reps():
    """List all dealer reps."""
    cache = sync_from_base44("DealerRep")
    return cache.get("records", [])

def create_quote_locally(quote_data):
    """Create a quote locally and queue for Base44 sync."""
    # Save locally
    local_path = os.path.join(SYNC_DIR, f"quote_{quote_data.get('quote_number', 'draft')}.json")
    with open(local_path, "w") as f:
        json.dump(quote_data, f, indent=2)
    
    # Queue for sync
    queue_write("DealWorksheet", quote_data, operation="create")
    
    print(f"  Quote saved locally: {local_path}")
    return quote_data

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "sync":
            # Sync all key entities
            entities = ["DealWorksheet", "DealerRep", "CustomerProfile", 
                        "RgInventoryCache", "SalesPopersInventory", "EquipmentOntology",
                        "PricingAnomalyFlag", "RevenueStream", "KalshiBet"]
            for e in entities:
                sync_from_base44(e)
            # Production entities
            sync_from_base44("Equipment", app_id=PRODUCTION_APP_ID)
            sync_from_base44("BobcatSpecLibrary", app_id=PRODUCTION_APP_ID)
            print("\n  Sync complete!")
        elif cmd == "queue":
            process_queue()
        elif cmd == "status":
            cache_dir = os.path.join(SYNC_DIR, "cache")
            caches = [f for f in os.listdir(cache_dir) if f.endswith(".json")] if os.path.exists(cache_dir) else []
            queue_dir = os.path.join(SYNC_DIR, "queue")
            queued = [f for f in os.listdir(queue_dir) if f.endswith(".json")] if os.path.exists(queue_dir) else []
            print(f"  API Key: {'configured' if API_KEY else 'MISSING'}")
            print(f"  Cached entities: {len(caches)}")
            print(f"  Pending writes: {len(queued)}")
            for c in caches[:10]:
                print(f"    {c}")
        else:
            print(f"Usage: {sys.argv[0]} [sync|queue|status]")
    else:
        print("Solas Base44 Sync — Local DGX Edition")
        print(f"API Key: {'configured' if API_KEY else 'MISSING — writes will be queued'}")
        print(f"Sync dir: {SYNC_DIR}")
        print("Commands: sync, queue, status")
