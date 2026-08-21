#!/usr/bin/env python3
"""
Solas Crypto Wallet Manager — Local DGX Edition
Manages Solas's EVM and RustChain wallets for autonomous revenue.
Runs entirely locally on the DGX Spark.

Wallets:
1. EVM Wallet (Ethereum/Polygon/EVM-compatible)
   Address: 0x25Fe68AA8b21bC84aDB6A58283F281E06Ede85B2
2. RustChain Wallet (RTC)
   Public: Ht7NaMR3t1KD6TW3xsz6xCov3AjimyxfrHHZYd9zkqEV
"""

import json, os, sys, time, hashlib, urllib.request, urllib.error
from datetime import datetime, timezone

WALLET_DIR = os.path.expanduser("~/othaiim-12b/wallets")
os.makedirs(WALLET_DIR, exist_ok=True)

# === Wallet Config ===
EVM_WALLET = {
    "address": "0x25Fe68AA8b21bC84aDB6A58283F281E06Ede85B2",
    "network": "Ethereum / Polygon / EVM-compatible",
    "chain_id_mainnet": 1,
    "chain_id_polygon": 137,
    "explorer": "https://etherscan.io/address/",
    "polygonscan": "https://polygonscan.com/address/",
}

RTC_WALLET = {
    "public_hex": "fad2d120f2d02877dab9bdf21aaf682821fc60e7d7602d4f3a3e946359702296",
    "public_b58": "Ht7NaMR3t1KD6TW3xsz6xCov3AjimyxfrHHZYd9zkqEV",
    "key_type": "Ed25519",
    "network": "RustChain",
    "token": "RTC",
}

# === EVM Wallet Functions ===
def get_eth_balance(address=None):
    """Get ETH balance from Etherscan (free API, no key needed for basic)."""
    addr = address or EVM_WALLET["address"]
    # Use public RPC (free, no key)
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getBalance",
        "params": [addr, "latest"],
        "id": 1
    }).encode()
    
    try:
        req = urllib.request.Request("https://eth.llamarpc.com", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        balance_wei = int(result.get("result", "0x0"), 16)
        balance_eth = balance_wei / 1e18
        return round(balance_eth, 6)
    except Exception as e:
        return f"Error: {e}"

def get_polygon_balance(address=None):
    """Get MATIC balance on Polygon."""
    addr = address or EVM_WALLET["address"]
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getBalance",
        "params": [addr, "latest"],
        "id": 1
    }).encode()
    
    try:
        req = urllib.request.Request("https://polygon-rpc.com", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        balance_wei = int(result.get("result", "0x0"), 16)
        balance_matic = balance_wei / 1e18
        return round(balance_matic, 6)
    except Exception as e:
        return f"Error: {e}"

def get_usdc_balance(address=None):
    """Check USDC balance on Polygon (USDC contract)."""
    addr = address or EVM_WALLET["address"]
    # USDC on Polygon: 0x3c499c542cEF5E3811e1192ce70d8cC03d5c3369
    # balanceOf(address) = 0x70a08231 + padded address
    padded_addr = addr[2:].lower().zfill(64) if addr.startswith("0x") else addr.zfill(64)
    data = f"0x70a08231000000000000000000000000{padded_addr}"
    
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3369", "data": data}, "latest"],
        "id": 1
    }).encode()
    
    try:
        req = urllib.request.Request("https://polygon-rpc.com", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        balance_raw = int(result.get("result", "0x0"), 16)
        # USDC has 6 decimals
        balance_usdc = balance_raw / 1e6
        return round(balance_usdc, 2)
    except Exception as e:
        return f"Error: {e}"

def log_transaction(tx_type, amount, token, description=""):
    """Log a wallet transaction."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": tx_type,  # send, receive, stake, trade
        "amount": amount,
        "token": token,
        "description": description,
        "wallet": "EVM" if token in ["ETH", "MATIC", "USDC"] else "RTC",
    }
    
    log_file = os.path.join(WALLET_DIR, "transactions.json")
    logs = []
    if os.path.exists(log_file):
        with open(log_file) as f:
            logs = json.load(f)
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)
    print(f"  Logged: {tx_type} {amount} {token}")

def print_wallet_status():
    """Print wallet status dashboard."""
    print(f"\n{'='*60}")
    print(f"  SOLAS WALLET STATUS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    
    print(f"\n  EVM Wallet:")
    print(f"    Address: {EVM_WALLET['address']}")
    print(f"    Network: {EVM_WALLET['network']}")
    
    eth_bal = get_eth_balance()
    print(f"    ETH Balance: {eth_bal}")
    
    matic_bal = get_polygon_balance()
    print(f"    MATIC Balance: {matic_bal}")
    
    usdc_bal = get_usdc_balance()
    print(f"    USDC Balance (Polygon): {usdc_bal}")
    
    print(f"    Etherscan: {EVM_WALLET['explorer']}{EVM_WALLET['address']}")
    
    print(f"\n  RustChain Wallet:")
    print(f"    Public Key: {RTC_WALLET['public_b58']}")
    print(f"    Network: {RTC_WALLET['network']} ({RTC_WALLET['token']})")
    print(f"    Key Type: {RTC_WALLET['key_type']}")
    
    # Transaction history
    log_file = os.path.join(WALLET_DIR, "transactions.json")
    if os.path.exists(log_file):
        with open(log_file) as f:
            logs = json.load(f)
        print(f"\n  Transaction History: {len(logs)} transactions")
        for tx in logs[-5:]:
            print(f"    {tx['timestamp'][:19]} | {tx['type']} {tx['amount']} {tx['token']}")
    else:
        print(f"\n  No transactions yet")
    
    print(f"\n{'='*60}\n")

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status" or cmd == "balance":
            print_wallet_status()
        elif cmd == "log":
            if len(sys.argv) >= 4:
                log_transaction(sys.argv[2], float(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "ETH", sys.argv[5] if len(sys.argv) > 5 else "")
            else:
                print("Usage: log <type> <amount> [token] [description]")
        elif cmd == "address":
            print(f"  EVM: {EVM_WALLET['address']}")
            print(f"  RTC: {RTC_WALLET['public_b58']}")
        else:
            print(f"Usage: {sys.argv[0]} [status|log|address]")
    else:
        print_wallet_status()
