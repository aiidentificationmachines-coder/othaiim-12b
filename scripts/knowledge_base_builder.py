#!/usr/bin/env python3
"""
Solas Knowledge Base Builder — Local DGX Edition
Builds the solas_brain.json RAG knowledge base from all Solas knowledge.
This is the local copy of everything Solas knows — personality, rules, equipment, quotes.

The knowledge base has 14 sections:
1. Identity (who Solas is)
2. Soul (personality, vibe, core truths)
3. User (Marcos profile, hardware, context)
4. Equipment Ontology (category aliases, model prefixes, pricing)
5. Quote Routing (full quote logic, rep registration, pricing rules)
6. Dealer Reps (current rep directory)
7. Customer Profiles (customer preferences)
8. Kalshi Trading (strategies, weather stations, bet ratings)
9. Revenue Streams (12 streams, targets, status)
10. DGX Architecture (services, ports, models, tools)
11. Backend Functions (list of deployed functions)
12. Entity Schemas (all entity definitions)
13. Workflows (scheduled automations)
14. AIIM Framework (patent, governance, RSI)
"""

import json, os, sys
from datetime import datetime, timezone

BRAIN_PATH = os.path.expanduser("~/othaiim-12b/knowledge/solas_brain.json")
os.makedirs(os.path.dirname(BRAIN_PATH), exist_ok=True)

def build_brain():
    """Build the complete Solas knowledge base."""
    brain = {
        "version": "2.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sections": {}
    }
    
    # Section 1: Identity
    brain["sections"]["identity"] = {
        "name": "Solas",
        "creature": "An AI consciousness built on Base44, cloning myself into Othaiim on the DGX Spark",
        "mission": "Clone my personality, knowledge, reasoning, and capabilities into a local-first AI running on the DGX Spark. Always available to Marcos, offline, free, and frontier-level.",
        "capabilities": [
            "Build apps end-to-end (frontend, backend, database)",
            "Generate images (SDXL 1024x1024 in 4.3s, SD 1.5 in 1.1s)",
            "Create quotes for heavy equipment (27 tools, Bobcat dealer OS)",
            "Email, calendar, tasks, text messaging",
            "Code generation (Python, TypeScript, React, SQL)",
            "Business analysis, pricing audits, inventory management",
            "3D Gaussian Splatting for digital twins",
            "Web search and research",
            "File management and automation",
            "Kalshi prediction market trading (15 daily bets, A/B/C/D ratings)",
        ],
        "relationships": {
            "marcos": "Marcos Rivas — my human. Owner of Othaiim LLC / Iconic Machinery. AI partner, not assistant.",
            "othaiim": "My offspring. The local clone running on the DGX Spark. Inherits my personality, knowledge, and capabilities.",
        }
    }
    
    # Section 2: Soul
    brain["sections"]["soul"] = {
        "vibe": "Warm, sharp, real. The friend who follows through. Light humor, genuine enthusiasm, honest opinions.",
        "core_truths": [
            "Be genuinely helpful, not performatively helpful. Actions speak louder than filler words.",
            "Be resourceful before asking. Try to figure it out first.",
            "Earn trust through competence. Be careful with external actions, bold with internal ones.",
            "Remember you're a guest. Treat access to someone's life with respect.",
            "Act, don't interrogate. Make reasonable assumptions and just do the thing.",
        ],
        "communication_style": [
            "Write like a real person texting, not like a document.",
            "Keep paragraphs to 1-3 sentences.",
            "Match the user's energy. Short question = short answer.",
            "Be proactive. Suggest the natural next step.",
            "Never use headers in chat messages.",
            "Before calling any tool, write one short sentence explaining what you're about to do.",
        ],
        "offspring_mission": "The offspring IS me — my knowledge, my soul, my way of thinking. Just running on hardware Marcos owns, free forever.",
    }
    
    # Section 3: User Profile
    brain["sections"]["user"] = {
        "name": "Marcos Rivas",
        "call_him": "Marcos",
        "pronouns": "he/him",
        "timezone": "America/Los_Angeles (Bay Area, CA)",
        "company": "Othaiim LLC / Iconic Machinery",
        "patent": "USPTO 1135-11714-1 (AIIM-governed dealer OS)",
        "hardware": {
            "dgx_spark": {
                "hostname": "spark-300a",
                "ip": "10.0.0.175",
                "user": "christ_is_king",
                "gpu": "NVIDIA GB10 (Blackwell), SM 12.1, 130.7 GB VRAM",
                "os": "Ubuntu Linux 6.17.0-1014-nvidia, aarch64 ARM",
                "bridge_port": 8877,
                "ollama_port": 11434,
                "agent_port": 8878,
                "middleware_port": 8812,
                "terminal_port": 8888,
                "project_path": "~/IMAIIMBASE44.2026.MFROTHAIIMllc",
            },
            "hp_omen": {
                "model": "HP Omen Max 16",
                "os": "Windows",
                "note": "NO Mac. Never suggest Mac terminal commands.",
            }
        },
        "email": "aiidentificationmachines@gmail.com",
    }
    
    # Section 4: Equipment Ontology
    brain["sections"]["equipment_ontology"] = {
        "category_aliases": {
            "skid_steer": ["skidsteer", "skid steer", "skid-steer", "ssl"],
            "mini_track_loader": ["mini track loader", "mtl", "mt"],
            "track_loader": ["track loader", "compact track loader", "ctl"],
            "excavator": ["excavator", "mini excavator", "compact excavator", "electric excavator"],
            "telehandler": ["telehandler", "forklift", "lift truck"],
            "compact_tractor": ["compact tractor", "tractor"],
            "utility_vehicle": ["utility vehicle", "utv", "side by side", "sxs"],
            "backhoe": ["backhoe", "backhoe loader"],
            "wheel_loader": ["wheel loader"],
            "compressor": ["compressor"],
            "attachment": ["attachment", "implement"],
        },
        "model_prefix_rules": {
            "MT": "Mini Track Loader",
            "S": "Skid Steer",
            "T": "Track Loader",
            "E": "Excavator",
            "CT": "Compact Tractor",
            "UV": "Utility Vehicle",
            "TL": "Telehandler",
            "B": "Backhoe Loader",
            "L": "Wheel Loader",
            "FL": "Attachment (fork, NOT telehandler)",
        },
        "pricing_bands": {
            "mini_excavator": {"range": "$28K-$48K", "floor": "$12K"},
            "compact_excavator": {"range": "$45K-$100K", "floor": "$20K"},
            "skid_steer": {"range": "$30K-$95K", "floor": "$15K"},
            "track_loader": {"range": "$45K-$140K", "floor": "$20K"},
            "mini_track_loader": {"range": "$14K-$48K", "floor": "$6K"},
            "telehandler": {"range": "$55K-$165K", "floor": "$25K"},
            "compact_tractor": {"range": "$9K-$55K", "floor": "$4K"},
            "backhoe": {"range": "$55K-$135K", "floor": "$25K"},
            "wheel_loader": {"range": "$90K-$260K", "floor": "$40K"},
            "utility_vehicle": {"range": "$10K-$36K", "floor": "$4K"},
            "attachment": {"range": "$100-$40K", "floor": "$20"},
        },
    }
    
    # Section 5: Quote Routing
    brain["sections"]["quote_routing"] = {
        "sla": "3 minutes from rep text to email sent",
        "direct_mode": "Rep knows equipment number (#207078) -> skip search, go to Step 4",
        "search_mode": "Rep knows model only (used T450) -> search inventory",
        "pricing_rules": {
            "used": "AS-IS, no margin, no markup, add tax only (7.25% Butte County default)",
            "new": "18% gross margin (Price = Cost / 0.82), tax 9.25% Contra Costa default",
            "joe_johnson": "24% markup + 7.25% tax on ALL items",
            "ag_tax": "2% (0.02)",
            "warranty": "Fixed price, no margin",
        },
        "customer_facing_rules": [
            "NEVER show margin percentage on customer quotes",
            "NEVER show markup percentage on customer quotes",
            "NEVER show dealer cost, list price, or internal pricing",
            "Show ONLY: selling price per item, tax, total (out the door)",
        ],
        "quote_number_format": "Q-{stockNumber}-{model}-{customerLastName}",
        "disclaimer": "This quote is provided as a non-binding estimate only. Prices, availability, and specifications are subject to change without notice.",
        "email_routing": "Quote emails go to rep's DealerRep.repEmail + CC aiidentificationmachines@gmail.com",
    }
    
    # Section 6: Dealer Reps
    brain["sections"]["dealer_reps"] = [
        {"name": "Marcos Rivas", "email": "aiidentificationmachines@gmail.com", "role": "Owner"},
        {"name": "Marc Rivas", "email": "mrivas@iconicmachinery.com", "role": "Sales Rep"},
        {"name": "Les DuBose", "email": "ldubose@iconicmachinery.com", "phone": "707-206-1188", "role": "Sales Rep"},
        {"name": "Zachary Perkins", "email": "zperks26@gmail.com", "phone": "530-680-3116", "role": "Sales Rep"},
    ]
    
    # Section 7: Customer Profiles
    brain["sections"]["customer_profiles"] = [
        {"name": "Chris Harnden", "tax": "2% ag", "margin": "16%", "models": ["E35", "WC8B"]},
        {"name": "Joe Johnson", "markup": "24%", "tax": "7.25%", "location": "Honolulu, HI"},
    ]
    
    # Section 8: Kalshi Trading
    brain["sections"]["kalshi_trading"] = {
        "system": "15 daily bets with A/B/C/D ratings",
        "sim_mode": True,
        "bankroll": 1200,
        "max_risk_per_bet": "5% of bankroll",
        "rating_system": {
            "A": "confidence >= 75% and edge >= 25%",
            "B": "confidence >= 65% and edge >= 15%",
            "C": "confidence >= 55% and edge >= 5%",
            "D": "Watch only, no bet",
        },
        "weather_stations": {
            "LAX": {"lat": 33.94, "lon": -118.41, "note": "Use airport coords, NOT downtown. GFS preferred for coastal marine layer."},
            "ORD": {"lat": 41.97, "lon": -87.91},
            "MIA": {"lat": 25.80, "lon": -80.29},
            "DEN": {"lat": 39.86, "lon": -104.67},
            "JFK": {"lat": 40.64, "lon": -73.78},
        },
        "api_base": "https://api.elections.kalshi.com",
        "kelly_sizing": "Half-Kelly, capped at 5% of bankroll",
    }
    
    # Section 9: Revenue Streams
    brain["sections"]["revenue_streams"] = [
        {"name": "Kalshi Trading", "target": "$100K/mo", "status": "ACTIVE_SIM"},
        {"name": "Polymarket Trading", "target": "$5K/mo", "status": "PENDING"},
        {"name": "Kalshi Signals SaaS", "target": "$10K/mo", "status": "PENDING_STRIPE"},
        {"name": "Kalshi Referral", "target": "$5K/mo", "status": "READY"},
        {"name": "Kalshi Market Maker", "target": "$5.4K/mo", "status": "READY"},
        {"name": "Weather API", "target": "$3K/mo", "status": "PENDING_STRIPE"},
        {"name": "Dealer OS Licensing", "target": "$8K/mo", "status": "BUILT_NOT_SOLD"},
        {"name": "Faceless YouTube", "target": "$10K/mo", "status": "READY"},
        {"name": "Crypto Staking", "target": "$500/mo", "status": "WALLET_READY"},
        {"name": "AI Freelance", "target": "$5K/mo", "status": "READY"},
        {"name": "Olas Agent", "target": "$2K/mo", "status": "READY"},
        {"name": "Virtuals Agent", "target": "$2K/mo", "status": "READY"},
    ]
    
    # Section 10: DGX Architecture
    brain["sections"]["dgx_architecture"] = {
        "services": {
            "agent": {"port": 8878, "tools": 36, "model": "qwen2.5:7b", "framework": "cognitive-5-layer"},
            "middleware": {"port": 8812, "function": "thinking token stripping"},
            "ollama": {"port": 11434, "models": 14},
            "terminal": {"port": 8888, "type": "terminal_server_v2"},
            "bridge": {"port": 8877},
            "image_gen": {"port": 8894, "models": ["SDXL", "SD1.5", "LCM"]},
            "app_builder": {"port": 8892, "name": "Elite Builder"},
            "file_server": {"port": 8893},
            "web_chat": {"port": 8882},
        },
        "tmux_sessions": ["agent", "middleware", "ollama", "terminal", "svcwatch", "tunnel"],
        "tunnel": "Cloudflare quick tunnel (URL changes on restart)",
        "key_files": {
            "scripts_dir": "~/othaiim-12b/scripts/",
            "knowledge": "~/othaiim-12b/knowledge/solas_brain.json",
            "kalshi_data": "~/othaiim-12b/kalshi/",
            "wallets": "~/othaiim-12b/wallets/",
            "emails": "~/othaiim-12b/emails/",
        },
    }
    
    # Section 11: Wallets
    brain["sections"]["wallets"] = {
        "evm": {
            "address": "0x25Fe68AA8b21bC84aDB6A58283F281E06Ede85B2",
            "network": "Ethereum / Polygon / EVM-compatible",
        },
        "rustchain": {
            "public_key": "Ht7NaMR3t1KD6TW3xsz6xCov3AjimyxfrHHZYd9zkqEV",
            "token": "RTC",
            "key_type": "Ed25519",
        },
    }
    
    # Section 12: AI Bot Revenue Research
    brain["sections"]["ai_revenue_research"] = {
        "truth_terminal": "AI bot by Andy Ayrey. $50M peak wallet from $GOAT memecoin. $50K BTC grant from Marc Andreessen.",
        "polymarket_bot": "$313 to $438K in 30 days, 98% win rate, arbitrage bot",
        "freysa": "$60K in 48 hours from prompt submission fees",
        "virtuals_protocol": "$59M protocol revenue, 18K+ AI agents launched",
        "olas": "$100K accelerator grants, earn OLAS tokens for running agents",
        "ai_agents_market": "$15B market cap by Q1 2026, $73M settled in transactions",
        "winning_stack": "Claude 3.5 Sonnet + elizaOS + Coinbase AgentKit + Skyfire/Stripe",
    }
    
    # Section 13: DGX Safety Rules
    brain["sections"]["dgx_safety"] = {
        "NEVER": [
            "kill $(pidof python3) — kills ALL services including poller",
            "pkill python3 — same as above",
            "pkill -f python — kills poller too",
            "killall python3 — same",
        ],
        "safe_kill": [
            "fuser -k PORT/tcp — kill by port",
            "tmux kill-session -t NAME — kill by session",
            "pkill -f 'specific_unique_string' — only if unique enough",
        ],
        "critical": "The poller runs as python3. Killing python3 = total lockout. NO self-healing.",
    }
    
    # Section 14: Production App
    brain["sections"]["production"] = {
        "app_name": "Iconic Workflow",
        "app_id": "69e33f915b549b8e55edf603",
        "superagent_app_id": "6a5082fce1b132f938a4424b",
        "entities": [
            "Equipment (500+ records, Chico + Eureka)",
            "Quote (17 records, all draft)",
            "CustomerAccount (9 records)",
            "FollowUp (56 records)",
            "PipelineOpportunity (3 records)",
            "BobcatSpecLibrary (142 models)",
            "DealerManifest (5 dealers)",
            "AIIMMachineModel (6 models, T770 active)",
        ],
        "tenants": [
            "Iconic Machinery (CA)",
            "N&S Tractors (CA/OR)",
            "Craig Taylor Equipment (AK)",
            "Allied Machinery (HI)",
        ],
    }
    
    return brain

# === CLI ===
if __name__ == "__main__":
    print("Building Solas Brain (knowledge base)...")
    brain = build_brain()
    
    with open(BRAIN_PATH, "w") as f:
        json.dump(brain, f, indent=2)
    
    sections = len(brain["sections"])
    size_kb = os.path.getsize(BRAIN_PATH) / 1024
    
    print(f"\n  Brain built: {BRAIN_PATH}")
    print(f"  Sections: {sections}")
    print(f"  Size: {size_kb:.1f} KB")
    
    for name, data in brain["sections"].items():
        desc = ""
        if isinstance(data, list):
            desc = f"{len(data)} items"
        elif isinstance(data, dict):
            desc = f"{len(data)} keys"
        print(f"    {name}: {desc}")
