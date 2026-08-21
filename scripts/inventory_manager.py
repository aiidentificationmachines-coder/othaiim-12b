#!/usr/bin/env python3
"""
Solas Inventory Manager — Local DGX Edition
Searches and manages equipment inventory locally on the DGX.
Uses cached Base44 entity data + RgInventoryCache + EquipmentOntology.

Capabilities:
- Search equipment by model, category, stock number
- Category resolution using ontology (aliases + model prefixes)
- Pricing sanity checks (market-value audit)
- Find cheapest/best deal/newest/lowest hours
- Filter by condition (used/new)
- Sort by price, hours, year, location
"""

import json, os, sys, re
from datetime import datetime, timezone

# === Paths ===
DATA_DIR = os.path.expanduser("~/othaiim-12b/inventory")
os.makedirs(DATA_DIR, exist_ok=True)

# === Category Resolution ===
CATEGORY_ALIASES = {
    "skidsteer": "Skid Steer", "skid steer": "Skid Steer", "skid-steer": "Skid Steer", "ssl": "Skid Steer",
    "mini track loader": "Mini Track Loader", "mtl": "Mini Track Loader", "mt": "Mini Track Loader",
    "track loader": "Track Loader", "compact track loader": "Track Loader", "ctl": "Track Loader",
    "excavator": "Excavator", "mini excavator": "Excavator", "compact excavator": "Excavator",
    "telehandler": "Telehandler", "forklift": "Telehandler",
    "compact tractor": "Compact Tractor", "tractor": "Compact Tractor",
    "utility vehicle": "Utility Vehicle", "utv": "Utility Vehicle", "side by side": "Utility Vehicle",
    "backhoe": "Backhoe Loader", "backhoe loader": "Backhoe Loader",
    "wheel loader": "Wheel Loader",
    "compressor": "Compressor",
    "attachment": "Attachment", "implement": "Attachment",
}

MODEL_PREFIX_RULES = {
    "MT": "Mini Track Loader",
    "S": "Skid Steer", "T": "Track Loader",
    "E": "Excavator", "CT": "Compact Tractor",
    "UV": "Utility Vehicle", "TL": "Telehandler",
    "B": "Backhoe Loader", "L": "Wheel Loader",
    "FL": "Attachment",
}

def resolve_category(query):
    """Resolve a free-text query to an equipment category."""
    q_lower = query.lower().strip()
    
    # Direct alias match
    for alias, category in CATEGORY_ALIASES.items():
        if alias == q_lower or alias in q_lower:
            return category
    
    # Model prefix match
    for prefix, category in MODEL_PREFIX_RULES.items():
        pattern = f"^{prefix}\\d"
        if re.match(pattern, query.upper()):
            return category
    
    return None

def get_model_prefix(model):
    """Get the category from a model code prefix."""
    model_upper = model.upper().strip()
    for prefix, category in sorted(MODEL_PREFIX_RULES.items(), key=lambda x: -len(x[0])):
        if model_upper.startswith(prefix):
            # Make sure next char is a digit
            rest = model_upper[len(prefix):]
            if rest and rest[0].isdigit():
                return category
    return None

def load_inventory():
    """Load cached inventory data."""
    cache_file = os.path.join(DATA_DIR, "equipment_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    return []

def load_ontology():
    """Load equipment ontology."""
    ont_file = os.path.join(DATA_DIR, "ontology_cache.json")
    if os.path.exists(ont_file):
        with open(ont_file) as f:
            return json.load(f)
    return []

def search_equipment(query, condition=None, sort_by="price_asc", limit=10):
    """Search equipment inventory."""
    inventory = load_inventory()
    if not inventory:
        return {"error": "No inventory data. Run sync first."}
    
    results = []
    category = resolve_category(query)
    model_code = None
    
    # Extract model code from query (e.g., "T450", "E35")
    model_match = re.search(r'\b([A-Z]{1,2}\d{1,4}[a-z]?)\b', query.upper())
    if model_match:
        model_code = model_match.group(1)
        if not category:
            category = get_model_prefix(model_code)
    
    for item in inventory:
        # Filter by model code
        if model_code:
            item_model = item.get("searchModel", item.get("model", "")).upper()
            if model_code not in item_model:
                continue
        
        # Filter by category
        if category:
            item_cat = item.get("category", item.get("modelCategory", ""))
            if category.lower() not in item_cat.lower():
                # Try model prefix as fallback
                prefix_cat = get_model_prefix(item.get("searchModel", item.get("model", "")))
                if prefix_cat != category:
                    continue
        
        # Filter by condition
        if condition:
            item_cond = item.get("condition", "used").lower()
            if condition.lower() not in item_cond:
                continue
        
        # Filter out sold items
        if item.get("isSold", False) or item.get("status", "").lower() == "sold":
            continue
        
        # Filter out unsellable
        if item.get("isSellable") is False:
            continue
        
        results.append(item)
    
    # Sort
    if sort_by == "price_asc":
        results.sort(key=lambda x: float(x.get("listPrice", x.get("suggestedPrice", 0)) or 0))
    elif sort_by == "price_desc":
        results.sort(key=lambda x: float(x.get("listPrice", x.get("suggestedPrice", 0)) or 0), reverse=True)
    elif sort_by == "hours_asc":
        results.sort(key=lambda x: float(x.get("hours", x.get("engHours", 999999)) or 999999))
    elif sort_by == "year_desc":
        results.sort(key=lambda x: int(x.get("year", 0) or 0), reverse=True)
    
    return results[:limit]

def find_cheapest(query, condition=None):
    """Find the cheapest equipment matching the query."""
    return search_equipment(query, condition=condition, sort_by="price_asc", limit=1)

def find_newest(query, condition=None):
    """Find the newest equipment matching the query."""
    return search_equipment(query, condition=condition, sort_by="year_desc", limit=1)

def find_lowest_hours(query, condition=None):
    """Find equipment with lowest hours."""
    return search_equipment(query, condition=condition, sort_by="hours_asc", limit=1)

def pricing_audit(inventory=None):
    """Run a pricing sanity check on inventory."""
    items = inventory or load_inventory()
    ontology = load_ontology()
    
    flags = []
    for item in items:
        price = float(item.get("suggestedPrice", item.get("listPrice", 0)) or 0)
        cost = float(item.get("dealerCost", 0) or 0)
        category = item.get("category", item.get("modelCategory", "Other"))
        model = item.get("model", item.get("searchModel", "?"))
        stock = item.get("stockNumber", "?")
        
        # Find ontology entry
        ont_entry = None
        for o in ontology:
            if o.get("modelCode", "").upper() == model.upper():
                ont_entry = o
                break
        
        if not ont_entry:
            continue
        
        min_price = float(ont_entry.get("minPrice", 0) or 0)
        max_price = float(ont_entry.get("maxPrice", 0) or 0)
        
        if min_price > 0:
            low_floor = min_price * 0.35
            high_ceiling = max_price * 1.35
            
            if price > 0 and price < low_floor:
                flags.append({
                    "stock": stock, "model": model, "category": category,
                    "price": price, "floor": low_floor,
                    "severity": "CRITICAL",
                    "reason": f"Price ${price} below floor ${low_floor:.0f}",
                })
            elif cost > 0 and cost < (min_price * 0.15):
                flags.append({
                    "stock": stock, "model": model, "category": category,
                    "cost": cost, "min_expected": min_price * 0.15,
                    "severity": "CRITICAL",
                    "reason": f"Cost ${cost} below 15% of min price ${min_price}",
                })
            elif price > high_ceiling:
                flags.append({
                    "stock": stock, "model": model, "category": category,
                    "price": price, "ceiling": high_ceiling,
                    "severity": "HIGH",
                    "reason": f"Price ${price} above ceiling ${high_ceiling:.0f}",
                })
    
    return flags

def print_results(results, query):
    """Print search results."""
    print(f"\n  Search: '{query}' — {len(results)} results\n")
    for i, item in enumerate(results, 1):
        model = item.get("model", item.get("searchModel", "?"))
        year = item.get("year", "?")
        price = item.get("listPrice", item.get("suggestedPrice", 0))
        hours = item.get("hours", item.get("engHours", "?"))
        city = item.get("city", "?")
        state = item.get("state", "")
        stock = item.get("stockNumber", "?")
        
        print(f"  {i}. {year} {model} - {city}, {state} - {hours} hrs - ${price}")
        print(f"     Stock: {stock}")

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "search":
            query = " ".join(sys.argv[2:])
            results = search_equipment(query)
            print_results(results, query)
        elif cmd == "cheapest":
            query = " ".join(sys.argv[2:])
            results = find_cheapest(query)
            print_results(results, f"cheapest {query}")
        elif cmd == "newest":
            query = " ".join(sys.argv[2:])
            results = find_newest(query)
            print_results(results, f"newest {query}")
        elif cmd == "lowest-hours":
            query = " ".join(sys.argv[2:])
            results = find_lowest_hours(query)
            print_results(results, f"lowest hours {query}")
        elif cmd == "audit":
            flags = pricing_audit()
            print(f"\n  Pricing Audit: {len(flags)} flags\n")
            for f in flags[:20]:
                print(f"  [{f['severity']}] {f['stock']} {f['model']}: {f['reason']}")
        elif cmd == "category":
            query = " ".join(sys.argv[2:])
            cat = resolve_category(query)
            print(f"  '{query}' -> {cat or 'Unknown'}")
        elif cmd == "status":
            inv = load_inventory()
            ont = load_ontology()
            print(f"  Inventory items: {len(inv)}")
            print(f"  Ontology entries: {len(ont)}")
            print(f"  Data dir: {DATA_DIR}")
        else:
            print(f"Usage: {sys.argv[0]} [search|cheapest|newest|lowest-hours|audit|category|status] [query]")
    else:
        print("Solas Inventory Manager — Local DGX Edition")
        inv = load_inventory()
        print(f"  Inventory items: {len(inv)}")
        print(f"  Commands: search, cheapest, newest, lowest-hours, audit, category, status")
