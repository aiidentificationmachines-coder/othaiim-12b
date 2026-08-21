#!/usr/bin/env python3
"""
Solas Quote Engine — Local DGX Edition
Full quote creation for heavy equipment, running entirely on the DGX.
Implements the quote routing logic from Solas's rules.

Capabilities:
- Parse equipment quote requests
- Resolve categories and find equipment
- Apply pricing rules (used/new/Joe Johnson/ag tax)
- Calculate tax, margins, totals
- Generate quote HTML with Iconic Machinery branding
- Create DealWorksheet records (local + queue for Base44)
"""

import json, os, sys, re, hashlib
from datetime import datetime, timedelta, timezone

# Import inventory manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inventory_manager import resolve_category, get_model_prefix, search_equipment, load_inventory

QUOTE_DIR = os.path.expanduser("~/othaiim-12b/quotes")
os.makedirs(QUOTE_DIR, exist_ok=True)

# Logo path (base64 embedded)
LOGO_PATH = os.path.expanduser("~/othaiim-12b/assets/iconic_machinery_logo.png")

# === Pricing Rules ===
DEFAULT_TAX_USED = 0.0725  # Butte County
DEFAULT_TAX_NEW = 0.0925  # Contra Costa County
DEFAULT_MARGIN_NEW = 0.18  # 18% gross margin
JOE_JOHNSON_MARKUP = 1.24
AG_TAX = 0.02

# === Customer Profiles ===
CUSTOMER_PROFILES = {
    "chris harnden": {"tax": AG_TAX, "margin": 0.16, "models": ["E35", "WC8B"]},
    "joe johnson": {"markup": JOE_JOHNSON_MARKUP, "tax": DEFAULT_TAX_USED, "location": "Honolulu, HI"},
}

def parse_quote_request(text):
    """Parse a natural language quote request."""
    text_lower = text.lower().strip()
    
    # Extract model code (e.g., T450, E35, S570)
    model_match = re.search(r'\b([A-Z]{1,2}\d{1,4}[a-z]?)\b', text.upper())
    model = model_match.group(1) if model_match else None
    
    # Extract stock number (e.g., #207078)
    stock_match = re.search(r'#?(\d{5,8})', text)
    stock_number = stock_match.group(1) if stock_match else None
    
    # Detect condition
    condition = None
    if "used" in text_lower:
        condition = "used"
    elif "new" in text_lower:
        condition = "new"
    
    # Detect special instructions
    tax_rate = None
    if "ag tax" in text_lower or "2% ag" in text_lower:
        tax_rate = AG_TAX
    elif re.search(r'tax\s+(\d+(?:\.\d+)?)\s*%', text_lower):
        tax_match = re.search(r'tax\s+(\d+(?:\.\d+)?)\s*%', text_lower)
        tax_rate = float(tax_match.group(1)) / 100
    
    # Detect customer name (usually at the end after "for")
    customer = None
    for_match = re.search(r'\bfor\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', text)
    if for_match:
        customer = for_match.group(1)
    
    # Detect cheapest/newest/lowest hours
    sort_pref = None
    if "cheapest" in text_lower or "best deal" in text_lower:
        sort_pref = "price_asc"
    elif "newest" in text_lower:
        sort_pref = "year_desc"
    elif "lowest hours" in text_lower:
        sort_pref = "hours_asc"
    
    return {
        "model": model,
        "stock_number": stock_number,
        "condition": condition,
        "tax_rate": tax_rate,
        "customer": customer,
        "sort_pref": sort_pref,
        "raw": text,
    }

def calculate_pricing(item, condition="used", customer=None, tax_rate=None, margin=None, markup=None):
    """Calculate pricing for an equipment item."""
    # Get customer profile
    profile = None
    if customer:
        profile = CUSTOMER_PROFILES.get(customer.lower())
    
    # Determine selling price
    if condition == "new":
        cost = float(item.get("machine_cost_with_ro", item.get("dealerCost", 0)) or 0)
        if markup:
            selling_price = cost * markup
        elif margin:
            selling_price = cost / (1 - margin)
        elif profile and "margin" in (profile or {}):
            selling_price = cost / (1 - profile["margin"])
        else:
            selling_price = cost / (1 - DEFAULT_MARGIN_NEW)
    else:
        # Used: AS-IS, no margin
        selling_price = float(item.get("listPrice", item.get("suggestedPrice", 0)) or 0)
    
    selling_price = round(selling_price, 2)
    
    # Determine tax rate
    if tax_rate is not None:
        final_tax = tax_rate
    elif profile and "tax" in profile:
        final_tax = profile["tax"]
    elif profile and "markup" in profile:
        final_tax = profile.get("tax", DEFAULT_TAX_USED)
    elif condition == "new":
        final_tax = DEFAULT_TAX_NEW
    else:
        final_tax = DEFAULT_TAX_USED
    
    tax_amount = round(selling_price * final_tax, 2)
    total = round(selling_price + tax_amount, 2)
    
    return {
        "selling_price": selling_price,
        "tax_rate": final_tax,
        "tax_amount": tax_amount,
        "total": total,
        "condition": condition,
    }

def generate_quote_number(stock_number, model, customer):
    """Generate a quote number."""
    customer_last = "CUSTOMER"
    if customer:
        parts = customer.split()
        if len(parts) >= 2:
            customer_last = parts[-1].upper()
    
    return f"Q-{stock_number}-{model}-{customer_last}"

def generate_quote_html(quote_data):
    """Generate quote HTML with Iconic Machinery branding."""
    quote_num = quote_data["quote_number"]
    customer = quote_data.get("customer_name", "Customer")
    model = quote_data.get("model", "")
    year = quote_data.get("year", "")
    stock = quote_data.get("stock_number", "")
    serial = quote_data.get("serial", "")
    hours = quote_data.get("hours", "")
    location = quote_data.get("location", "")
    selling = quote_data["pricing"]["selling_price"]
    tax_rate = quote_data["pricing"]["tax_rate"]
    tax_amount = quote_data["pricing"]["tax_amount"]
    total = quote_data["pricing"]["total"]
    date = datetime.now().strftime("%B %d, %Y")
    expiration = (datetime.now() + timedelta(days=7)).strftime("%B %d, %Y")
    prepared_by = quote_data.get("prepared_by", "Solas AI")
    
    # Logo base64
    logo_b64 = ""
    if os.path.exists(LOGO_PATH):
        import base64
        with open(LOGO_PATH, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
    
    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; border-bottom: 3px solid #FF4500; padding-bottom: 15px; margin-bottom: 20px; }}
.header img {{ max-width: 200px; margin-bottom: 10px; }}
.quote-info {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
.quote-box {{ border: 2px solid #333; padding: 15px; margin: 15px 0; }}
.specs {{ background: #f5f5f5; padding: 15px; margin: 15px 0; border-left: 4px solid #FF4500; }}
.total-box {{ background: #FF4500; color: white; padding: 15px; text-align: center; font-size: 1.5em; }}
.disclaimer {{ font-size: 10px; color: #999; margin-top: 20px; text-align: center; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #333; color: white; }}
</style>
</head>
<body>
<div class="header">
  {'<img src="data:image/png;base64,' + logo_b64 + '">' if logo_b64 else '<h1>ICONIC MACHINERY</h1>'}
  <p>Iconic Machinery | Chico, CA | (530) 555-0123</p>
</div>

<div class="quote-info">
  <div>
    <strong>Quote:</strong> {quote_num}<br>
    <strong>Date:</strong> {date}<br>
    <strong>Prepared By:</strong> {prepared_by}<br>
    <strong>Valid Until:</strong> {expiration}
  </div>
  <div>
    <strong>Customer:</strong> {customer}<br>
    <strong>Equipment:</strong> {year} {model}<br>
    <strong>Stock:</strong> {stock}
  </div>
</div>

<div class="quote-box">
  <h3>Equipment Details</h3>
  <table>
    <tr><th>Model</th><td>{model}</td></tr>
    <tr><th>Year</th><td>{year}</td></tr>
    <tr><th>Stock Number</th><td>{stock}</td></tr>
    <tr><th>Serial</th><td>{serial}</td></tr>
    <tr><th>Hours</th><td>{hours}</td></tr>
    <tr><th>Location</th><td>{location}</td></tr>
  </table>
</div>

<div class="quote-box">
  <h3>Pricing</h3>
  <table>
    <tr><th>Selling Price</th><td>${selling:,.2f}</td></tr>
    <tr><th>Sales Tax ({tax_rate*100:.2f}%)</th><td>${tax_amount:,.2f}</td></tr>
    <tr><th><strong>Total (Out the Door)</strong></th><td><strong>${total:,.2f}</strong></td></tr>
  </table>
</div>

<div class="total-box">
  Total: ${total:,.2f}
</div>

<div class="disclaimer">
  This quote is provided as a non-binding estimate only. Prices, availability, and specifications
  are subject to change without notice. Final pricing will be confirmed at the time of sale.
  Contact Iconic Machinery for current availability and terms.
</div>

</body>
</html>"""
    
    return html

def create_quote(text, rep_name="Solas", customer=None, tax_rate=None, margin=None, markup=None):
    """Create a quote from a natural language request."""
    parsed = parse_quote_request(text)
    
    if not parsed["model"] and not parsed["stock_number"]:
        return {"error": "Could not identify equipment model or stock number"}
    
    # Search for equipment
    if parsed["stock_number"]:
        # Direct mode — search by stock number
        inventory = load_inventory()
        items = [i for i in inventory if i.get("stockNumber") == parsed["stock_number"]]
    else:
        sort = parsed["sort_pref"] or "price_asc"
        condition = parsed["condition"]
        items = search_equipment(parsed["model"], condition=condition, sort_by=sort, limit=5)
    
    if not items:
        return {"error": f"No equipment found for '{parsed['model'] or parsed['stock_number']}'"}
    
    if len(items) > 1 and not parsed["sort_pref"] and not parsed["stock_number"]:
        return {
            "status": "disambiguate",
            "items": items,
            "message": f"Found {len(items)} matches. Which one?",
        }
    
    item = items[0]
    condition = parsed["condition"] or "used"
    customer_name = customer or parsed["customer"] or "Customer"
    final_tax = tax_rate or parsed["tax_rate"]
    final_margin = margin
    final_markup = markup
    
    # Joe Johnson special case
    if "joe" in customer_name.lower() and "johnson" in customer_name.lower():
        final_markup = JOE_JOHNSON_MARKUP
        final_tax = DEFAULT_TAX_USED
    
    pricing = calculate_pricing(item, condition, customer_name, final_tax, final_margin, final_markup)
    
    stock = item.get("stockNumber", "00000")
    model = item.get("model", item.get("searchModel", parsed["model"] or "UNKNOWN"))
    quote_number = generate_quote_number(stock, model, customer_name)
    
    quote_data = {
        "quote_number": quote_number,
        "customer_name": customer_name,
        "model": model,
        "year": item.get("year", ""),
        "stock_number": stock,
        "serial": item.get("serialNumber", item.get("serial", "")),
        "hours": item.get("hours", item.get("engHours", "")),
        "location": f"{item.get('city', '?')}, {item.get('state', '')}",
        "condition": condition,
        "pricing": pricing,
        "prepared_by": rep_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "expiration": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
    }
    
    # Generate HTML
    html = generate_quote_html(quote_data)
    
    # Save locally
    html_file = os.path.join(QUOTE_DIR, f"{quote_number}.html")
    with open(html_file, "w") as f:
        f.write(html)
    
    json_file = os.path.join(QUOTE_DIR, f"{quote_number}.json")
    with open(json_file, "w") as f:
        json.dump(quote_data, f, indent=2)
    
    return {
        "status": "created",
        "quote_number": quote_number,
        "selling_price": pricing["selling_price"],
        "tax": pricing["tax_amount"],
        "total": pricing["total"],
        "html_file": html_file,
        "json_file": json_file,
        "item": {
            "model": model,
            "year": item.get("year", ""),
            "stock": stock,
            "location": quote_data["location"],
            "hours": quote_data["hours"],
        }
    }

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "quote":
            text = " ".join(sys.argv[2:])
            result = create_quote(text)
            if result.get("status") == "created":
                print(f"\n  Quote Created: {result['quote_number']}")
                print(f"  {result['item']['year']} {result['item']['model']} - Stock {result['item']['stock']}")
                print(f"  ${result['selling_price']:,.2f} + ${result['tax']:,.2f} tax = ${result['total']:,.2f} OTD")
                print(f"  Location: {result['item']['location']}")
                print(f"  Hours: {result['item']['hours']}")
                print(f"  HTML: {result['html_file']}")
            elif result.get("status") == "disambiguate":
                print(f"\n  {result['message']}")
                for i, item in enumerate(result["items"], 1):
                    print(f"  {i}. {item.get('year', '?')} {item.get('model', '?')} - "
                          f"{item.get('city', '?')}, {item.get('state', '')} - "
                          f"{item.get('hours', item.get('engHours', '?'))} hrs - "
                          f"${item.get('listPrice', item.get('suggestedPrice', 0))}")
            else:
                print(f"  Error: {result.get('error', 'unknown')}")
        elif cmd == "parse":
            text = " ".join(sys.argv[2:])
            result = parse_quote_request(text)
            print(json.dumps(result, indent=2))
        elif cmd == "status":
            quotes = [f for f in os.listdir(QUOTE_DIR) if f.endswith(".json")]
            print(f"  Quotes: {len(quotes)}")
            print(f"  Dir: {QUOTE_DIR}")
        else:
            print(f"Usage: {sys.argv[0]} [quote|parse|status] [text]")
    else:
        print("Solas Quote Engine — Local DGX Edition")
        quotes = [f for f in os.listdir(QUOTE_DIR) if f.endswith(".json")]
        print(f"  Quotes: {len(quotes)}")
        print(f"  Commands: quote, parse, status")
