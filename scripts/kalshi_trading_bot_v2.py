#!/usr/bin/env python3
"""
Solas Kalshi Trading Bot v2 — Local DGX Edition
Runs entirely on the DGX Spark. No cloud credits needed.
"""

import json, os, sys, time, subprocess, urllib.request, urllib.error, re
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.expanduser("~/othaiim-12b/kalshi")
os.makedirs(DATA_DIR, exist_ok=True)

KALSHI_API_BASE = "https://api.elections.kalshi.com"
KALSHI_SANDBOX = "https://sandbox-api.elections.kalshi.com"

KALSHI_KEY_ID = os.environ.get("KALSHI_KEY_ID", "")
KALSHI_PRIVATE_KEY = os.environ.get("KALSHI_PRIVATE_KEY", "")

env_path = os.path.expanduser("~/othaiim-12b/.env")
if not KALSHI_KEY_ID and os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("KALSHI_KEY_ID="):
                KALSHI_KEY_ID = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("KALSHI_PRIVATE_KEY="):
                KALSHI_PRIVATE_KEY = line.split("=", 1)[1].strip().strip('"')

SIM_MODE = not (KALSHI_KEY_ID and KALSHI_PRIVATE_KEY)
BANKROLL = 1200
MAX_DAILY_BETS = 15
MAX_RISK_PER_BET = 0.05

class KalshiClient:
    def __init__(self, key_id="", private_key="", sandbox=False):
        self.key_id = key_id
        self.private_key = private_key
        self.base_url = KALSHI_API_BASE  # Always use prod for market data
        self.sandbox = sandbox
    
    def get_markets(self, category="", status="open", limit=100):
        url = f"{self.base_url}/trade-api/v2/markets?status={status}&limit={limit}"
        if category:
            url += f"&category={category}"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Solas-Kalshi-Bot/2.0")
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            return data.get("markets", [])
        except Exception as e:
            print(f"  Kalshi API error: {e}")
            return []
    
    def get_market_prices(self, ticker):
        url = f"{self.base_url}/trade-api/v2/markets/{ticker}/orderbook"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Solas-Kalshi-Bot/2.0")
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}
    
    def get_weather_markets(self):
        return self.get_markets(category="weather")
    
    def get_financial_markets(self):
        all_markets = self.get_markets(limit=200)
        keywords = ["fed", "rate", "bitcoin", "btc", "s&p", "sp500",
                    "treasury", "gold", "oil", "cpi", "gdp", "unemployment"]
        return [m for m in all_markets if any(
            kw in m.get("title", "").lower() or kw in m.get("subtitle", "").lower()
            for kw in keywords
        )]

def get_weather_forecast(lat, lon, station_name=""):
    """Get weather forecast from NWS API (free, no key needed)."""
    try:
        url = f"https://api.weather.gov/points/{lat},{lon}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Solas-Kalshi-Bot/2.0")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        
        # Use the simple forecast endpoint
        forecast_url = data.get("properties", {}).get("forecast", "")
        if forecast_url:
            req2 = urllib.request.Request(forecast_url, method="GET")
            req2.add_header("User-Agent", "Solas-Kalshi-Bot/2.0")
            resp2 = urllib.request.urlopen(req2, timeout=10)
            fdata = json.loads(resp2.read())
            periods = fdata.get("properties", {}).get("periods", [])
            if periods:
                today = periods[0]
                temp_f = today.get("temperature", 0)
                return [{"station": station_name, "temp_f": temp_f,
                        "source": "NWS", "forecast": today.get("shortForecast", ""),
                        "name": today.get("name", "")}]
        
        # Try grid data
        forecast_url = data.get("properties", {}).get("forecastGridData", "")
        if forecast_url:
            req2 = urllib.request.Request(forecast_url, method="GET")
            req2.add_header("User-Agent", "Solas-Kalshi-Bot/2.0")
            resp2 = urllib.request.urlopen(req2, timeout=10)
            gdata = json.loads(resp2.read())
            temps = gdata.get("properties", {}).get("temperature", {}).get("values", [])
            if temps:
                temp_k = temps[0].get("value", 273.15)
                temp_f = (temp_k - 273.15) * 9/5 + 32
                return [{"station": station_name, "temp_f": round(temp_f, 1),
                        "source": "NWS-GFS"}]
        
        return []
    except Exception as e:
        print(f"  Weather API error: {e}")
        return []

AIRPORTS = {
    "LAX": (33.94, -118.41),
    "ORD": (41.97, -87.91),
    "MIA": (25.80, -80.29),
    "DEN": (39.86, -104.67),
    "JFK": (40.64, -73.78),
    "DFW": (32.90, -97.04),
    "ATL": (33.64, -84.44),
    "SEA": (47.45, -122.31),
    "PHX": (33.43, -112.01),
    "IAH": (29.98, -95.36),
}

def analyze_weather_markets(client):
    markets = client.get_weather_markets()
    opportunities = []
    
    for m in markets[:20]:
        ticker = m.get("ticker", "")
        title = m.get("title", "")
        
        temp_match = re.findall(r'(\d+)\s*°?F', title)
        if not temp_match:
            temp_match = re.findall(r'(\d+)\s*degrees?', title)
        
        if temp_match:
            target_temp = int(temp_match[0])
            city = ""
            for code in AIRPORTS:
                if code.lower() in title.lower():
                    city = code
                    break
            
            if city:
                lat, lon = AIRPORTS[city]
                forecast = get_weather_forecast(lat, lon, city)
                if forecast and "temp_f" in forecast[0]:
                    forecast_temp = forecast[0]["temp_f"]
                    diff = abs(forecast_temp - target_temp)
                    confidence = max(0, 1 - (diff / 20))
                    
                    if confidence > 0.5:
                        opportunities.append({
                            "ticker": ticker,
                            "title": title,
                            "category": "weather",
                            "city": city,
                            "target_temp": target_temp,
                            "forecast_temp": forecast_temp,
                            "confidence": round(confidence, 3),
                            "edge_pct": round((confidence - 0.5) * 100, 1),
                            "source": "NWS-GFS",
                        })
    
    return opportunities

def analyze_financial_markets(client):
    markets = client.get_financial_markets()
    opportunities = []
    for m in markets[:15]:
        opportunities.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "category": "financial",
            "confidence": 0.0,
            "edge_pct": 0,
            "source": "needs_research",
        })
    return opportunities

def rate_bet(confidence, edge_pct):
    if confidence >= 0.75 and edge_pct >= 25:
        return "A"
    elif confidence >= 0.65 and edge_pct >= 15:
        return "B"
    elif confidence >= 0.55 and edge_pct >= 5:
        return "C"
    else:
        return "D"

def kelly_sizing(win_prob, odds_decimal, bankroll, max_frac=0.05):
    if win_prob <= 0 or odds_decimal <= 1:
        return 0
    kelly = (win_prob * odds_decimal - 1) / (odds_decimal - 1)
    half_kelly = kelly / 2
    bet_frac = min(half_kelly, max_frac)
    return round(max(0, bankroll * bet_frac), 2)

def run_daily_scan():
    print(f"\n{'='*60}")
    print(f"  SOLAS KALSHI DAILY SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'SIMULATION' if SIM_MODE else 'LIVE'}")
    print(f"  Bankroll: ${BANKROLL}")
    print(f"{'='*60}\n")
    
    client = KalshiClient()  # Always use prod API for market data
    
    print("1. Scanning weather markets...")
    weather_ops = analyze_weather_markets(client)
    print(f"   Found {len(weather_ops)} weather opportunities")
    
    print("2. Scanning financial markets...")
    fin_ops = analyze_financial_markets(client)
    print(f"   Found {len(fin_ops)} financial opportunities")
    
    all_ops = weather_ops + fin_ops
    all_ops.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    top_15 = all_ops[:MAX_DAILY_BETS]
    
    bets = []
    for i, op in enumerate(top_15, 1):
        confidence = op.get("confidence", 0)
        edge_pct = op.get("edge_pct", 0)
        rating = rate_bet(confidence, edge_pct)
        bet_amount = kelly_sizing(confidence, 2.0, BANKROLL, MAX_RISK_PER_BET)
        
        bet = {
            "bet_number": i,
            "ticker": op.get("ticker"),
            "title": op.get("title", "")[:80],
            "category": op.get("category"),
            "rating": rating,
            "confidence": confidence,
            "edge_pct": edge_pct,
            "bet_amount": bet_amount if rating in ["A", "B", "C"] else 0,
            "source": op.get("source"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "SIM" if SIM_MODE else "LIVE",
        }
        bets.append(bet)
        
        action = "BET" if rating in ["A", "B", "C"] else "WATCH"
        print(f"  #{i:2d} [{rating}] {action:5s} ${bet_amount:6.2f} | {bet['title']}")
    
    a_bets = [b for b in bets if b["rating"] == "A"]
    b_bets = [b for b in bets if b["rating"] == "B"]
    c_bets = [b for b in bets if b["rating"] == "C"]
    d_bets = [b for b in bets if b["rating"] == "D"]
    total_deployed = sum(b["bet_amount"] for b in bets)
    
    print(f"\n{'='*60}")
    print(f"  SUMMARY: {len(bets)} bets | A:{len(a_bets)} B:{len(b_bets)} C:{len(c_bets)} D:{len(d_bets)}")
    print(f"  Deployed: ${total_deployed:.2f} / ${BANKROLL} ({total_deployed/BANKROLL*100:.1f}%)")
    print(f"{'='*60}\n")
    
    output = {
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "scan_time": datetime.now().isoformat(),
        "mode": "SIM" if SIM_MODE else "LIVE",
        "bankroll": BANKROLL,
        "total_bets": len(bets),
        "total_deployed": total_deployed,
        "ratings": {"A": len(a_bets), "B": len(b_bets), "C": len(c_bets), "D": len(d_bets)},
        "bets": bets,
    }
    
    output_file = os.path.join(DATA_DIR, f"scan_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved: {output_file}")
    
    return output

def check_yesterday_results():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday_file = os.path.join(DATA_DIR, f"scan_{yesterday}.json")
    
    if not os.path.exists(yesterday_file):
        print(f"  No scan found for {yesterday}")
        return None
    
    with open(yesterday_file) as f:
        scan = json.load(f)
    
    print(f"\n  Yesterday's scan: {scan['total_bets']} bets, ${scan['total_deployed']} deployed")
    for bet in scan.get("bets", []):
        print(f"    #{bet['bet_number']} [{bet['rating']}] {bet['title'][:60]}")
    return scan

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "scan":
            run_daily_scan()
        elif sys.argv[1] == "results":
            check_yesterday_results()
        elif sys.argv[1] == "status":
            print(f"Mode: {'SIMULATION' if SIM_MODE else 'LIVE'}")
            print(f"Bankroll: ${BANKROLL}")
            print(f"API Keys: {'configured' if KALSHI_KEY_ID else 'MISSING'}")
            print(f"Data dir: {DATA_DIR}")
            scans = [f for f in os.listdir(DATA_DIR) if f.startswith("scan_")]
            print(f"Past scans: {len(scans)}")
        else:
            print(f"Usage: {sys.argv[0]} [scan|results|status]")
    else:
        run_daily_scan()
