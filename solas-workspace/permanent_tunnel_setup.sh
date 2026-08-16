#!/bin/bash
# Permanent Cloudflare Named Tunnel Setup for DGX Spark
# This replaces the temporary trycloudflare.com URL with a permanent one
# that never changes, auto-reconnects on network drops, and survives reboots.

set -e

CFD="cloudflared"
HOME_DIR="/home/christ_is_king"
CF_DIR="$HOME_DIR/.cloudflared"
TUNNEL_NAME="othaiim-spark"

echo "============================================"
echo "PERMANENT TUNNEL SETUP — DGX Spark"
echo "============================================"
echo ""

# Step 0: Check if already authenticated
if [ -f "$CF_DIR/cert.pem" ]; then
    echo "[OK] Already authenticated with Cloudflare"
else
    echo "[STEP 1] Authentication required."
    echo "Run this command first:"
    echo "  $CFD tunnel login"
    echo ""
    echo "This opens a browser. Select your domain to authorize."
    echo "After login completes, re-run this script."
    echo ""
    exit 1
fi

# Step 1: Create the named tunnel
echo "[STEP 2] Creating permanent tunnel: $TUNNEL_NAME"
if $CFD tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
    echo "[OK] Tunnel '$TUNNEL_NAME' already exists"
else
    $CFD tunnel create "$TUNNEL_NAME"
    echo "[OK] Tunnel created"
fi

# Get tunnel ID
TUNNEL_ID=$($CFD tunnel list 2>/dev/null | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "[INFO] Tunnel ID: $TUNNEL_ID"

# Step 2: Create config.yml
echo "[STEP 3] Creating config file"
mkdir -p "$CF_DIR"
cat > "$CF_DIR/config.yml" << YAMLEOF
tunnel: $TUNNEL_ID
credentials-file: $CF_DIR/$TUNNEL_ID.json

ingress:
  - hostname: othaiim.spark.local
    service: http://localhost:8888
  - hostname: api.othaiim.spark.local
    service: http://localhost:8890
  - hostname: builder.othaiim.spark.local
    service: http://localhost:8891
  - hostname: agent.othaiim.spark.local
    service: http://localhost:8878
  - hostname: files.othaiim.spark.local
    service: http://localhost:8882
  - service: http_status:404
YAMLEOF
echo "[OK] Config written to $CF_DIR/config.yml"

# Step 3: Route DNS
echo "[STEP 4] Routing DNS"
echo "You need a domain registered on Cloudflare for this step."
echo ""
echo "If you have a domain (e.g., mydomain.com), run:"
echo "  $CFD tunnel route dns $TUNNEL_NAME othaiim.mydomain.com"
echo ""
echo "This creates a CNAME record pointing othaiim.mydomain.com to your tunnel."
echo "The URL becomes permanent and never changes."
echo ""

# Step 4: Install as systemd service
echo "[STEP 5] Installing as systemd service"
echo "Run these commands:"
echo "  sudo $CFD service install"
echo "  sudo systemctl enable $CFD"
echo "  sudo systemctl start $CFD"
echo ""
echo "This makes the tunnel:"
echo "  - Start automatically on boot"
echo "  - Auto-restart if it crashes"
echo "  - Survive network drops (reconnects within seconds)"
echo "  - Never change its URL"
echo ""

# Step 5: Kill old temporary tunnel
echo "[STEP 6] Stopping temporary tunnel"
echo "Run these to stop the old setup:"
echo "  tmux kill-session -t tunnel 2>/dev/null"
echo "  tmux kill-session -t watchdog 2>/dev/null"
echo "  pkill -f 'trycloudflare' 2>/dev/null"
echo ""

# Step 6: Verify
echo "[STEP 7] Verify the permanent tunnel"
echo "After setup, check with:"
echo "  sudo systemctl status $CFD"
echo "  curl -s https://othaiim.YOURDOMAIN.com/health"
echo ""

echo "============================================"
echo "DONE! Your permanent tunnel URL will be:"
echo "  https://othaiim.YOURDOMAIN.com"
echo ""
echo "It never changes, never drops, survives reboots."
echo "No watchdog script needed anymore."
echo "============================================"
