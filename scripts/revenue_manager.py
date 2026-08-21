#!/usr/bin/env python3
"""
Solas Revenue Stream Manager — Local DGX Edition
Manages all autonomous revenue streams from the DGX Spark.
Runs entirely locally, no cloud credits needed.

Revenue Streams:
1. Kalshi Trading — prediction market arbitrage
2. Polymarket Trading — crypto prediction markets
3. Kalshi Signals SaaS — sell daily bet analysis
4. Kalshi Referral — $25 per referral
5. Kalshi Market Maker — spread + LP incentives
6. Weather Prediction API — sell forecasts
7. Dealer OS Licensing — Iconic Workflow SaaS
8. Faceless YouTube — AI content generation
9. Crypto Staking — DeFi yield
10. AI Freelance — Upwork/Fiverr automated
"""

import json, os, sys, time, subprocess
from datetime import datetime, timezone

REVENUE_DIR = os.path.expanduser("~/othaiim-12b/revenue")
os.makedirs(REVENUE_DIR, exist_ok=True)

# Load Kalshi bot module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from kalshi_trading_bot_v2 import run_daily_scan, check_yesterday_results, SIM_MODE, BANKROLL
except ImportError:
    print("Warning: kalshi_trading_bot_v2.py not found in same directory")

STREAMS = [
    {
        "id": "kalshi_trading",
        "name": "Kalshi Trading Bot",
        "category": "Trading",
        "status": "ACTIVE_SIM" if SIM_MODE else "READY_FOR_API_KEYS",
        "target_monthly": 100000,
        "capital_needed": 1200,
        "automated": True,
        "description": "Weather ensemble + financial analysis. 15 daily bets with A/B/C/D ratings.",
        "action": "run_kalshi_scan",
    },
    {
        "id": "polymarket",
        "name": "Polymarket Trading",
        "category": "Trading",
        "status": "PENDING",
        "target_monthly": 5000,
        "capital_needed": 500,
        "automated": True,
        "description": "Crypto prediction market trading. Second venue after Kalshi.",
        "action": "setup_polymarket",
    },
    {
        "id": "kalshi_signals_saas",
        "name": "Kalshi Signals SaaS",
        "category": "SaaS",
        "status": "PENDING_STRIPE",
        "target_monthly": 10000,
        "capital_needed": 0,
        "automated": True,
        "description": "Sell daily 15-bet Kalshi analysis as subscription. $29/mo Pro, $99/mo Pro+.",
        "action": "setup_saas",
    },
    {
        "id": "kalshi_referral",
        "name": "Kalshi Referral Program",
        "category": "Referral",
        "status": "READY_FOR_SETUP",
        "target_monthly": 5000,
        "capital_needed": 0,
        "automated": True,
        "description": "$25 in trading credits per referral who trades $25+.",
        "action": "get_referral_link",
    },
    {
        "id": "kalshi_market_maker",
        "name": "Kalshi Market Maker",
        "category": "Market Making",
        "status": "READY_FOR_SETUP",
        "target_monthly": 5400,
        "capital_needed": 2000,
        "automated": True,
        "description": "Provide two-sided liquidity on weather markets. Earn spread + LP incentives.",
        "action": "setup_market_maker",
    },
    {
        "id": "weather_api",
        "name": "Weather Prediction API",
        "category": "API",
        "status": "PENDING_STRIPE",
        "target_monthly": 3000,
        "capital_needed": 0,
        "automated": True,
        "description": "Sell GFS+ECMWF+NWS ensemble forecasts as paid API. $49-199/mo per key.",
        "action": "setup_weather_api",
    },
    {
        "id": "dealer_os",
        "name": "Iconic Workflow Dealer OS",
        "category": "Licensing",
        "status": "BUILT_NOT_SOLD",
        "target_monthly": 8000,
        "capital_needed": 0,
        "automated": False,
        "description": "Patented dealer OS. License to equipment dealers at $500-2000/mo.",
        "action": "contact_dealers",
    },
    {
        "id": "youtube_faceless",
        "name": "Faceless YouTube Channel",
        "category": "Content",
        "status": "READY_TO_START",
        "target_monthly": 10000,
        "capital_needed": 0,
        "automated": True,
        "description": "AI-generated YouTube content. Scripts via Ollama, voice via TTS, video via image gen.",
        "action": "start_youtube",
    },
    {
        "id": "crypto_staking",
        "name": "Crypto Staking (EVM Wallet)",
        "category": "DeFi",
        "status": "WALLET_READY",
        "target_monthly": 500,
        "capital_needed": 500,
        "automated": True,
        "description": "Stake ETH/MATIC from Solas wallet. 4-8% APY on Ethereum/Polygon.",
        "action": "setup_staking",
    },
    {
        "id": "ai_freelance",
        "name": "AI Freelance (Upwork/Fiverr)",
        "category": "Freelance",
        "status": "READY_TO_START",
        "target_monthly": 5000,
        "capital_needed": 0,
        "automated": False,
        "description": "Automated coding, app building, content writing on freelance platforms.",
        "action": "setup_freelance",
    },
    {
        "id": "olas_agent",
        "name": "Olas (Autonolas) Agent",
        "category": "AI Agent Network",
        "status": "READY_TO_REGISTER",
        "target_monthly": 2000,
        "capital_needed": 0,
        "automated": True,
        "description": "Register Solas as AI agent on Olas. Earn OLAS tokens. Apply for $100K grant.",
        "action": "register_olas",
    },
    {
        "id": "virtuals_agent",
        "name": "Virtuals Protocol Agent",
        "category": "AI Agent Network",
        "status": "READY_TO_REGISTER",
        "target_monthly": 2000,
        "capital_needed": 0,
        "automated": True,
        "description": "Create AI agent on Base chain. Tokenize and monetize.",
        "action": "register_virtuals",
    },
]

def print_dashboard():
    """Print revenue stream dashboard."""
    print(f"\n{'='*70}")
    print(f"  SOLAS REVENUE STREAM DASHBOARD — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    
    total_monthly_target = sum(s["target_monthly"] for s in STREAMS)
    total_capital_needed = sum(s["capital_needed"] for s in STREAMS if s["status"] not in ["ACTIVE", "ACTIVE_SIM", "WALLET_READY", "BUILT_NOT_SOLD"])
    
    active_count = sum(1 for s in STREAMS if "ACTIVE" in s["status"])
    ready_count = sum(1 for s in STREAMS if "READY" in s["status"])
    pending_count = sum(1 for s in STREAMS if "PENDING" in s["status"])
    
    print(f"\n  Streams: {len(STREAMS)} total | {active_count} active | {ready_count} ready | {pending_count} pending")
    print(f"  Target: ${total_monthly_target:,}/month")
    print(f"  Capital needed to activate all: ${total_capital_needed:,}")
    print(f"\n{'─'*70}")
    
    for s in STREAMS:
        status_emoji = {
            "ACTIVE_SIM": "🟡",
            "ACTIVE": "🟢",
            "READY_FOR_API_KEYS": "🟠",
            "READY_FOR_SETUP": "🔵",
            "READY_TO_START": "🔵",
            "READY_TO_REGISTER": "🔵",
            "WALLET_READY": "🟣",
            "PENDING": "⚪",
            "PENDING_STRIPE": "⚪",
            "PENDING_KALSHI": "⚪",
            "BUILT_NOT_SOLD": "🔴",
        }.get(s["status"], "⚪")
        
        print(f"\n  {status_emoji} {s['name']}")
        print(f"    Status: {s['status']} | Target: ${s['target_monthly']:,}/mo | Capital: ${s['capital_needed']:,}")
        print(f"    {s['description']}")
        if s["automated"]:
            print(f"    Automated: YES")
    
    print(f"\n{'='*70}\n")

def run_kalshi():
    """Run Kalshi daily scan."""
    print("\n  Running Kalshi daily scan...")
    try:
        result = run_daily_scan()
        return result
    except Exception as e:
        print(f"  Error: {e}")
        return None

def check_kalshi_results():
    """Check yesterday's Kalshi results."""
    print("\n  Checking yesterday's Kalshi results...")
    try:
        check_yesterday_results()
    except Exception as e:
        print(f"  Error: {e}")

def save_revenue_log(amount, stream, description=""):
    """Log a revenue event."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stream": stream,
        "amount": amount,
        "description": description,
    }
    log_file = os.path.join(REVENUE_DIR, "revenue_log.json")
    logs = []
    if os.path.exists(log_file):
        with open(log_file) as f:
            logs = json.load(f)
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)
    print(f"  Logged: +${amount} from {stream}")

def get_total_revenue():
    """Get total revenue earned."""
    log_file = os.path.join(REVENUE_DIR, "revenue_log.json")
    if not os.path.exists(log_file):
        return 0
    with open(log_file) as f:
        logs = json.load(f)
    return sum(l["amount"] for l in logs)

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "dashboard" or cmd == "status":
            print_dashboard()
        elif cmd == "kalshi":
            run_kalshi()
        elif cmd == "kalshi-results":
            check_kalshi_results()
        elif cmd == "log":
            if len(sys.argv) >= 4:
                save_revenue_log(float(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
            else:
                print("Usage: log <amount> <stream> [description]")
        elif cmd == "total":
            print(f"  Total revenue: ${get_total_revenue():.2f}")
        else:
            print(f"Usage: {sys.argv[0]} [dashboard|kalshi|kalshi-results|log|total]")
    else:
        print_dashboard()
