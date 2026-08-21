#!/bin/bash
# Solas DGX Suite — Master Launcher
# Starts all local Solas tools on the DGX Spark
# Usage: ./solas_dgx_suite.sh [status|start|dashboard|kalshi|brain]

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

case "$1" in
    status)
        echo "=========================================="
        echo "  SOLAS DGX SUITE — STATUS"
        echo "=========================================="
        echo ""
        echo "  Scripts deployed:"
        for f in kalshi_trading_bot_v2.py base44_sync.py revenue_manager.py \
                 wallet_manager.py email_sender.py web_search.py \
                 knowledge_base_builder.py inventory_manager.py quote_engine.py; do
            if [ -f "$f" ]; then
                SIZE=$(wc -c < "$f")
                echo "    [OK] $f (${SIZE} bytes)"
            else
                echo "    [MISSING] $f"
            fi
        done
        echo ""
        echo "  Knowledge Base:"
        if [ -f ../knowledge/solas_brain.json ]; then
            SIZE=$(wc -c < ../knowledge/solas_brain.json)
            echo "    [OK] solas_brain.json (${SIZE} bytes)"
        else
            echo "    [MISSING] solas_brain.json — run: python3 knowledge_base_builder.py"
        fi
        echo ""
        echo "  Data directories:"
        for d in ../kalshi ../inventory ../quotes ../wallets ../emails ../searches; do
            if [ -d "$d" ]; then
                COUNT=$(ls -1 "$d" 2>/dev/null | wc -l)
                echo "    [OK] $d ($COUNT files)"
            else
                echo "    [MISSING] $d"
            fi
        done
        echo ""
        echo "  Running services:"
        for port in 8878 8812 11434 8888; do
            if fuser $port/tcp >/dev/null 2>&1; then
                echo "    [UP] Port $port"
            else
                echo "    [DOWN] Port $port"
            fi
        done
        echo ""
        echo "  Agent tools:"
        curl -s --max-time 5 http://localhost:8878/health 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(f\"    Tools: {d.get('tool_count', '?')}\")
    print(f\"    Model: {d.get('model', '?')}\")
    print(f\"    Architecture: {d.get('architecture', '?')}\")
except:
    print('    Agent not responding')
" 2>/dev/null || echo "    Agent not responding"
        ;;

    brain)
        echo "Building Solas knowledge base..."
        python3 knowledge_base_builder.py
        ;;

    kalshi)
        echo "Running Kalshi daily scan..."
        python3 kalshi_trading_bot_v2.py scan
        ;;

    dashboard)
        python3 revenue_manager.py dashboard
        ;;

    wallet)
        python3 wallet_manager.py status
        ;;

    search)
        shift
        python3 web_search.py "$@"
        ;;

    quote)
        shift
        python3 quote_engine.py quote "$@"
        ;;

    sync)
        echo "Syncing from Base44..."
        python3 base44_sync.py sync
        ;;

    email)
        echo "Email system status:"
        python3 email_sender.py status
        ;;

    start)
        echo "Starting Solas DGX Suite..."
        echo ""
        echo "  1. Building knowledge base..."
        python3 knowledge_base_builder.py
        echo ""
        echo "  2. Checking services..."
        for port in 8878 8812 11434 8888; do
            if fuser $port/tcp >/dev/null 2>&1; then
                echo "    [UP] Port $port"
            else
                echo "    [DOWN] Port $port"
            fi
        done
        echo ""
        echo "  3. Revenue dashboard:"
        python3 revenue_manager.py dashboard
        ;;

    *)
        echo "Solas DGX Suite — Local copy of everything Solas does"
        echo ""
        echo "Commands:"
        echo "  status    - Show status of all tools and services"
        echo "  start     - Initialize suite (build brain, check services, show dashboard)"
        echo "  brain     - Build/rebuild knowledge base (solas_brain.json)"
        echo "  kalshi    - Run Kalshi daily scan (15 bets with A/B/C/D ratings)"
        echo "  dashboard - Show revenue stream dashboard (12 streams)"
        echo "  wallet    - Show crypto wallet status (EVM + RustChain)"
        echo "  search    - Web search (DuckDuckGo + Wikipedia)"
        echo "  quote     - Create equipment quote from natural language"
        echo "  sync      - Sync entity data from Base44 to local cache"
        echo "  email     - Check email sender status"
        echo ""
        echo "Scripts deployed in: $DIR"
        ;;
esac
