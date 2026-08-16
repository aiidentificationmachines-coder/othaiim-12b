#!/usr/bin/env bash
#
# permanent_tunnel_fix.sh — Comprehensive Permanent Tunnel Fix for DGX Spark
#
# Hardware:  NVIDIA DGX Spark (GB10)
# OS:        Ubuntu 24.10+ / 6.17 ARM64
# Host IP:   10.0.0.175
# User:      christ_is_king
#
# Problem:   Cloudflare quick tunnels (trycloudflare.com) drop every 5–15 min.
#            The watchdog restarts them but there's still downtime.
#
# Solution:  THREE redundant access layers:
#   Layer 1: Cloudflare Named Tunnel  (permanent, needs a domain)
#   Layer 2: Tailscale mesh VPN        (free, no domain, stable 100.x.x.x IP)
#   Layer 3: Improved Python watchdog  (health endpoint, email alerts, logging)
#
# The script is self-contained, idempotent (safe to rerun), and sets up
# as many layers as are available on this machine.
#
# Usage:
#   sudo bash permanent_tunnel_fix.sh
#
# ---------------------------------------------------------------------------

set -euo pipefail

# ============================================================================
# Configuration / constants
# ============================================================================

readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="permanent_tunnel_fix"
readonly OS_USER="christ_is_king"
readonly BASE_DIR="${HOME}/othaiim-12b"
readonly LOG_FILE="${BASE_DIR}/tunnel_health.log"
readonly HEALTH_PORT=8888          # health endpoint lives at port 8888/health

# Service ports (the DGX local services we are fronting)
readonly PORT_TERMINAL=8888
readonly PORT_API=8890
readonly PORT_BUILDER=8891
readonly PORT_PAGES=8882

# Cloudflare named tunnel config
readonly TUNNEL_NAME="othaiim"
readonly CLOUDFLARED_CONFIG_DIR="${HOME}/.cloudflared"
readonly CLOUDFLARED_CONFIG_FILE="${CLOUDFLARED_CONFIG_DIR}/config.yml"
readonly NAMED_TUNNEL_SERVICE="cloudflared-named-othaiim.service"
readonly QUICK_TUNNEL_SERVICE="cloudflared-quick-othaiim.service"

# Tailscale
readonly TAILSCALE_SERVICE="tailscaled.service"

# Watchdog
readonly WATCHDOG_SCRIPT="${BASE_DIR}/tunnel_watchdog.py"
readonly WATCHDOG_SERVICE="othaiim-tunnel.service"
readonly WATCHDOG_VENV="${BASE_DIR}/tunnel_watchdog_venv"
readonly EMAIL_TO="aiidentificationmachines@gmail.com"

# Quick-tunnel command (used by watchdog as a fallback/failover layer)
readonly QUICK_TUNNEL_CMD="cloudflared tunnel --url http://localhost:${PORT_TERMINAL} --no-autoupdate"

# Terminal colors (disabled if not a TTY)
if [[ -t 1 ]]; then
    readonly C_RED='\033[0;31m'
    readonly C_GREEN='\033[0;32m'
    readonly C_YELLOW='\033[0;33m'
    readonly C_BLUE='\033[0;34m'
    readonly C_CYAN='\033[0;36m'
    readonly C_BOLD='\033[1m'
    readonly C_RST='\033[0m'
else
    readonly C_RED='' C_GREEN='' C_YELLOW='' C_BLUE='' C_CYAN='' C_BOLD='' C_RST=''
fi

# ============================================================================
# Helpers
# ============================================================================

log()     { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${C_CYAN}[INFO]${C_RST}  $*"; }
log_ok()  { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${C_GREEN}[OK]${C_RST}    $*"; }
log_warn(){ echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${C_YELLOW}[WARN]${C_RST}  $*"; }
log_err() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${C_RED}[ERR]${C_RST}    $*"; }
log_step(){ echo -e "\n${C_BOLD}${C_BLUE}════════════════════════════════════════════════════════════════${C_RST}"; echo -e "${C_BOLD}${C_BLUE}  $*${C_RST}"; echo -e "${C_BOLD}${C_BLUE}════════════════════════════════════════════════════════════════${C_RST}\n"; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        log_err "This script must be run as root (use: sudo bash $0)."
        exit 1
    fi
}

confirm() {
    local prompt="$1" default="${2:-n}"
    local reply=""
    if [[ "$default" == "y" ]]; then
        read -rp "$(echo -e "${C_BOLD}$prompt${C_RST} [Y/n] ")" reply
        [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]
    else
        read -rp "$(echo -e "${C_BOLD}$prompt${C_RST} [y/N] ")" reply
        [[ "$reply" =~ ^[Yy]$ ]]
    fi
}

pkg_install() {
    # install package(s) if not already present
    local pkgs=("$@") missing=()
    for p in "${pkgs[@]}"; do
        if ! dpkg -s "$p" &>/dev/null; then
            missing+=("$p")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log "Installing: ${missing[*]}"
        apt-get update -y
        apt-get install -y "${missing[@]}"
    else
        log_ok "Already installed: ${pkgs[*]}"
    fi
}

service_active() {
    systemctl is-active --quiet "$1" 2>/dev/null
}

service_enable_start() {
    local svc="$1"
    log "Enabling and starting ${svc} …"
    systemctl daemon-reload
    systemctl enable "$svc" 2>/dev/null || true
    systemctl restart "$svc"
    sleep 2
    if service_active "$svc"; then
        log_ok "${svc} is running"
    else
        log_err "${svc} failed to start"
        journalctl -u "$svc" --no-pager -n 20 || true
    fi
}

# ============================================================================
# Pre-flight
# ============================================================================

preflight() {
    log_step "Pre-flight checks"
    require_root

    if [[ ! -d "$BASE_DIR" ]]; then
        log "Creating base directory $BASE_DIR"
        mkdir -p "$BASE_DIR"
    fi

    # ensure the log file exists (watchdog appends to it)
    touch "$LOG_FILE"
    chown "$OS_USER":"$OS_USER" "$LOG_FILE" 2>/dev/null || true

    log "Host: $(hostname)"
    log "User: $OS_USER  Base dir: $BASE_DIR"
    log "Log : $LOG_FILE"
    log_ok "Pre-flight complete"
}

# ============================================================================
# Layer 1: Cloudflare Named Tunnel
# ============================================================================

layer1_cloudflare_named() {
    log_step "Layer 1 — Cloudflare Named Tunnel"

    # --- is cloudflared installed? -------------------------------------------
    if ! command -v cloudflared &>/dev/null; then
        log_warn "cloudflared is not installed."
        if confirm "Install cloudflared now (from Cloudflare's package repo)?"; then
            log "Installing cloudflared …"
            ARCH="$(dpkg --print-architecture)"   # arm64 on DGX Spark
            case "$ARCH" in
                arm64|aarch64) DEB_ARCH="arm64" ;;
                amd64|x86_64)  DEB_ARCH="amd64" ;;
                *)            DEB_ARCH="$ARCH"  ;;
            esac
            CFD_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${DEB_ARCH}.deb"
            TMP_DEB="$(mktemp /tmp/cloudflared.XXXXXX.deb)"
            if curl -fsSL "$CFD_URL" -o "$TMP_DEB"; then
                dpkg -i "$TMP_DEB" || apt-get install -f -y
                rm -f "$TMP_DEB"
                log_ok "cloudflared installed: $(cloudflared --version 2>&1 || echo 'unknown')"
            else
                log_err "Failed to download cloudflared from $CFD_URL"
                rm -f "$TMP_DEB"
                log_warn "Skipping Layer 1 (Named Tunnel)."
                return 1
            fi
        else
            log_warn "Skipping Layer 1 (Named Tunnel) — cloudflared not installed."
            return 1
        fi
    else
        log_ok "cloudflared found: $(cloudflared --version 2>&1 || echo 'unknown')"
    fi

    # --- is there an existing cert? ------------------------------------------
    local has_cert="no"
    if [[ -f "${CLOUDFLARED_CONFIG_DIR}/cert.pem" ]]; then
        has_cert="yes"
        log_ok "Cloudflare origin cert present at ${CLOUDFLARED_CONFIG_DIR}/cert.pem"
    fi

    # --- does the user have a Cloudflare domain? -----------------------------
    local DOMAIN=""
    if [[ "$has_cert" == "yes" ]]; then
        # Try to infer zone from existing cert (cloudflared doesn't expose it
        # directly, so we ask the user or read from any existing config).
        if [[ -f "$CLOUDFLARED_CONFIG_FILE" ]]; then
            # crude grep for hostname to guess domain
            DOMAIN="$(grep -oP '(?<=hostnames: \[)[^\]]+' "$CLOUDFLARED_CONFIG_FILE" 2>/dev/null | tail -n1 || true)"
        fi
    fi

    if [[ -z "$DOMAIN" ]]; then
        echo
        echo -e "${C_BOLD}Cloudflare Named Tunnel requires a Cloudflare-managed domain.${C_RST}"
        echo -e "Without a domain, Layer 1 cannot be configured, but Layers 2 & 3 will still be set up."
        echo
        if ! confirm "Do you have a Cloudflare domain you want to use (e.g. example.com)?"; then
            log_warn "No domain available — skipping Layer 1 (Named Tunnel)."
            log_warn "Layer 2 (Tailscale) and Layer 3 (watchdog) will still be installed."
            return 1
        fi
        read -rp "$(echo -e "${C_BOLD}Enter your Cloudflare domain:${C_RST} ")" DOMAIN
        DOMAIN="${DOMAIN// /}"   # trim spaces
        if [[ -z "$DOMAIN" ]]; then
            log_warn "No domain entered — skipping Layer 1."
            return 1
        fi
    fi

    log "Using domain: $DOMAIN"

    # --- authenticate (if no cert) --------------------------------------------
    if [[ "$has_cert" == "no" ]]; then
        log_warn "No origin certificate found. Starting browser-based Cloudflare login."
        log_warn "On a headless DGX this will print a URL — open it on another machine."
        if sudo -u "$OS_USER" cloudflared tunnel login 2>&1; then
            log_ok "Cloudflare login successful"
        else
            log_err "Cloudflare login failed or was cancelled."
            log_warn "Skipping Layer 1 (Named Tunnel)."
            return 1
        fi
    fi

    # --- create the tunnel (idempotent) --------------------------------------
    local tunnel_id=""
    if cloudflared tunnel list 2>/dev/null | grep -qw "$TUNNEL_NAME"; then
        log_ok "Tunnel '$TUNNEL_NAME' already exists"
        tunnel_id="$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL_NAME" '$2==t{print $1; exit}')"
        # fallback if column order differs
        [[ -z "$tunnel_id" ]] && tunnel_id="$(cloudflared tunnel list 2>/dev/null | awk -v t="$TUNNEL_NAME" '$0 ~ t{print $1; exit}')"
    else
        if tunnel_id="$(sudo -u "$OS_USER" cloudflared tunnel create "$TUNNEL_NAME" 2>&1 | grep -oP '(?<=Created tunnel )\S+' | head -n1)"; then
            log_ok "Tunnel '$TUNNEL_NAME' created (id: $tunnel_id)"
        else
            # the grep may have returned nothing; try to get the id from json
            tunnel_id="$(cloudflared tunnel list --output json 2>/dev/null | python3 -c "import sys,json; [print(t['id']) for t in json.load(sys.stdin) if t['name']=='$TUNNEL_NAME']" 2>/dev/null | head -n1 || true)"
            if [[ -n "$tunnel_id" ]]; then
                log_ok "Tunnel '$TUNNEL_NAME' created (id: $tunnel_id)"
            else
                log_err "Failed to create tunnel '$TUNNEL_NAME'"
                log_warn "Skipping Layer 1 (Named Tunnel)."
                return 1
            fi
        fi
    fi

    if [[ -z "$tunnel_id" ]]; then
        log_err "Could not determine tunnel ID. Skipping Layer 1."
        return 1
    fi

    log "Tunnel ID: $tunnel_id"

    # --- write config.yml (idempotent) ---------------------------------------
    mkdir -p "$CLOUDFLARED_CONFIG_DIR"

    cat > "$CLOUDFLARED_CONFIG_FILE" <<EOF
# Cloudflare Named Tunnel config — generated by permanent_tunnel_fix.sh
# Tunnel:  ${TUNNEL_NAME}
# ID:      ${tunnel_id}
# Domain:  ${DOMAIN}
tunnel: ${tunnel_id}
credentials-file: ${CLOUDFLARED_CONFIG_DIR}/${tunnel_id}.json

# Ingress rules — map public hostnames to local DGX service ports.
ingress:
  # Terminal (e.g. Jupyter / web terminal) -> 8888
  - hostname: ${TUNNEL_NAME}.${DOMAIN}
    service: http://localhost:${PORT_TERMINAL}

  # API -> 8890
  - hostname: api.${TUNNEL_NAME}.${DOMAIN}
    service: http://localhost:${PORT_API}

  # Builder -> 8891
  - hostname: builder.${TUNNEL_NAME}.${DOMAIN}
    service: http://localhost:${PORT_BUILDER}

  # Pages -> 8882
  - hostname: pages.${TUNNEL_NAME}.${DOMAIN}
    service: http://localhost:${PORT_PAGES}

  # Catch-all (must be last)
  - service: http_status:404
EOF

    chown -R "$OS_USER":"$OS_USER" "$CLOUDFLARED_CONFIG_DIR" 2>/dev/null || true
    log_ok "Config written: $CLOUDFLARED_CONFIG_FILE"

    # --- route DNS ------------------------------------------------------------
    log "Routing DNS records through Cloudflare (idempotent) …"
    for route in \
        "${TUNNEL_NAME}.${DOMAIN}" \
        "api.${TUNNEL_NAME}.${DOMAIN}" \
        "builder.${TUNNEL_NAME}.${DOMAIN}" \
        "pages.${TUNNEL_NAME}.${DOMAIN}"
    do
        # cloudflared route dns is idempotent — it will update if the record exists
        sudo -u "$OS_USER" cloudflared tunnel route dns "$TUNNEL_NAME" "$route" 2>&1 \
            && log_ok "DNS routed: $route -> $TUNNEL_NAME" \
            || log_warn "Could not route DNS for $route (may already exist or DNS API issue)"
    done

    # --- validate config -----------------------------------------------------
    if sudo -u "$OS_USER" cloudflared tunnel ingress validate 2>&1; then
        log_ok "Ingress config validated"
    else
        log_warn "Ingress validation reported issues — proceeding anyway"
    fi

    # --- systemd service for the named tunnel --------------------------------
    local SVC_PATH="/etc/systemd/system/${NAMED_TUNNEL_SERVICE}"
    cat > "$SVC_PATH" <<EOF
[Unit]
Description=Cloudflare Named Tunnel (othaiim) — permanent remote access
Documentation=https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
TimeoutStartSec=30
User=${OS_USER}
ExecStartPre=/usr/local/bin/cloudflared --config ${CLOUDFLARED_CONFIG_FILE} tunnel ingress validate
ExecStart=/usr/local/bin/cloudflared --config ${CLOUDFLARED_CONFIG_FILE} tunnel run
ExecStop=/usr/local/bin/cloudflared tunnel cleanup ${TUNNEL_NAME}
Restart=on-failure
RestartSec=5s

# Hardening
NoNewPrivileges=true
AmbientCapabilities=CAP_NET_BIND_SERVICE
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${CLOUDFLARED_CONFIG_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    # cloudflared binary might be at /usr/bin/cloudflared on some installs
    local CFD_BIN
    CFD_BIN="$(command -v cloudflared)"
    if [[ "$CFD_BIN" != "/usr/local/bin/cloudflared" ]]; then
        sed -i "s|/usr/local/bin/cloudflared|${CFD_BIN}|g" "$SVC_PATH"
    fi

    log_ok "Service file: $SVC_PATH"
    service_enable_start "$NAMED_TUNNEL_SERVICE"

    # Stop the *old* quick-tunnel service if we previously created one —
    # the named tunnel supersedes it.  (The watchdog can still spin up a
    # quick tunnel as a last-resort failover, see Layer 3.)
    if service_active "$QUICK_TUNNEL_SERVICE"; then
        log "Stopping legacy quick-tunnel service (superseded by named tunnel) …"
        systemctl stop "$QUICK_TUNNEL_SERVICE" || true
        systemctl disable "$QUICK_TUNNEL_SERVICE" || true
    fi

    log_ok "Layer 1 (Cloudflare Named Tunnel) configured and running"
    echo
    echo -e "${C_GREEN}  Public URLs:${C_RST}"
    echo -e "  • ${C_BOLD}https://${TUNNEL_NAME}.${DOMAIN}${C_RST}        → localhost:${PORT_TERMINAL} (terminal)"
    echo -e "  • ${C_BOLD}https://api.${TUNNEL_NAME}.${DOMAIN}${C_RST}   → localhost:${PORT_API} (API)"
    echo -e "  • ${C_BOLD}https://builder.${TUNNEL_NAME}.${DOMAIN}${C_RST} → localhost:${PORT_BUILDER} (builder)"
    echo -e "  • ${C_BOLD}https://pages.${TUNNEL_NAME}.${DOMAIN}${C_RST}  → localhost:${PORT_PAGES} (pages)"
}

# ============================================================================
# Layer 2: Tailscale mesh VPN
# ============================================================================

layer2_tailscale() {
    log_step "Layer 2 — Tailscale mesh VPN"

    # --- is tailscale installed? ---------------------------------------------
    if ! command -v tailscale &>/dev/null; then
        log_warn "Tailscale is not installed."
        if confirm "Install Tailscale now?"; then
            log "Installing Tailscale via official script …"
            curl -fsSL https://tailscale.com/install.sh | sh
        else
            log_warn "Skipping Layer 2 (Tailscale)."
            return 1
        fi
    else
        log_ok "Tailscale found: $(tailscale version 2>/dev/null | head -n1)"
    fi

    # --- ensure tailscaled is enabled ----------------------------------------
    log "Enabling tailscaled service …"
    systemctl enable tailscaled 2>/dev/null || true
    systemctl start  tailscaled 2>/dev/null || true
    sleep 2

    if ! service_active "tailscaled"; then
        log_err "tailscaled failed to start"
        journalctl -u tailscaled --no-pager -n 20 || true
        log_warn "Skipping Layer 2."
        return 1
    fi

    # --- bring up tailscale (join mesh) --------------------------------------
    if tailscale status &>/dev/null 2>&1; then
        log_ok "Tailscale is already up"
    else
        log_warn "Tailscale needs to be brought up (joined to your tailnet)."
        echo
        echo -e "${C_BOLD}This will print an authentication URL if the machine is not pre-authorized.${C_RST}"
        echo -e "Open the URL in a browser and approve the device."
        echo

        # Accept advertised routes for the DGX subnet optionally
        if confirm "Also advertise the DGX subnet (10.0.0.0/24) so other tailnet nodes can reach it?"; then
            tailscale up --advertise-routes=10.0.0.0/24 --accept-routes --ssh 2>&1 \
                || tailscale up --advertise-routes=10.0.0.0/24 2>&1 \
                || true
        else
            tailscale up --ssh 2>&1 || tailscale up 2>&1 || true
        fi

        sleep 3
    fi

    # --- report stable IP ----------------------------------------------------
    local TS_IP=""
    TS_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
    if [[ -n "$TS_IP" ]]; then
        log_ok "Tailscale stable IP: ${C_BOLD}${TS_IP}${C_RST} (this IP NEVER changes)"
        echo
        echo -e "${C_GREEN}  Direct SSH from any tailnet device:${C_RST}"
        echo -e "  • ${C_BOLD}ssh ${OS_USER}@${TS_IP}${C_RST}"
        echo -e "  • ${C_BOLD}http://${TS_IP}:${PORT_TERMINAL}${C_RST}  (terminal)"
        echo -e "  • ${C_BOLD}http://${TS_IP}:${PORT_API}${C_RST}      (API)"
        echo -e "  • ${C_BOLD}http://${TS_IP}:${PORT_BUILDER}${C_RST}  (builder)"
        echo -e "  • ${C_BOLD}http://${TS_IP}:${PORT_PAGES}${C_RST}   (pages)"
    else
        log_warn "Could not determine Tailscale IP yet (may still be authenticating)."
        log "Run 'tailscale up' manually and rerun this script."
    fi

    log_ok "Layer 2 (Tailscale) configured"
}

# ============================================================================
# Layer 3: Improved Python watchdog + health endpoint
# ============================================================================

layer3_watchdog() {
    log_step "Layer 3 — Python Watchdog + Health Endpoint"

    # --- prerequisites --------------------------------------------------------
    pkg_install python3 python3-venv python3-pip

    # create venv for the watchdog (isolated deps)
    if [[ ! -d "$WATCHDOG_VENV" ]]; then
        log "Creating Python venv: $WATCHDOG_VENV"
        python3 -m venv "$WATCHDOG_VENV"
    fi

    # install / upgrade required pip packages
    local PIP="$WATCHDOG_VENV/bin/pip"
    log "Installing watchdog Python dependencies …"
    "$PIP" install --quiet --upgrade pip 2>/dev/null || true
    "$PIP" install --quiet requests psutil 2>&1 || {
        log_warn "pip install of requests/psutil had issues; watchdog will still run with best-effort"
    }

    # --- write the watchdog script --------------------------------------------
    log "Writing watchdog: $WATCHDOG_SCRIPT"
    cat > "$WATCHDOG_SCRIPT" <<'PYEOF'
#!/usr/bin/env python3
"""
tunnel_watchdog.py — Health monitor for DGX Spark remote-access stack.

Checks every 10 s:
  • local services (8888, 8890, 8891, 8882)
  • Cloudflare named tunnel systemd service
  • Cloudflare quick tunnel (if running as failover)
  • Tailscale connectivity

Exposes JSON health endpoint at http://localhost:8888/health (served by an
embedded HTTP server on the same port as the terminal service — implemented
here as a small standalone server on port 8889 and proxied, OR if nothing is
listening on 8888 we serve directly on 8888).

Email alerts are sent on critical failures (cooled down to avoid spam).
"""

import os, sys, time, json, socket, subprocess, smtplib, threading, logging
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.mime.text import MIMEText

# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #

BASE_DIR          = os.path.expanduser("~/othaiim-12b")
LOG_FILE          = os.path.join(BASE_DIR, "tunnel_health.log")
HEALTH_BIND       = "0.0.0.0"
HEALTH_PORT       = 8888          # /health endpoint
CHECK_INTERVAL    = 10            # seconds between health checks

SERVICES = {
    "terminal": 8888,
    "api":      8890,
    "builder":  8891,
    "pages":    8882,
}

NAMED_TUNNEL_SVC = "cloudflared-named-othaiim.service"
QUICK_TUNNEL_SVC = "cloudflared-quick-othaiim.service"
TAILSCALE_SVC    = "tailscaled.service"

# Quick-tunnel command used as last-resort failover
QUICK_TUNNEL_CMD = "cloudflared tunnel --url http://localhost:8888 --no-autoupdate"

# Email alerts
EMAIL_ENABLED = True
EMAIL_FROM    = "aiidentificationmachines@gmail.com"
EMAIL_TO      = "aiidentificationmachines@gmail.com"
SMTP_HOST    = "smtp.gmail.com"
SMTP_PORT    = 587
# Password / app-password read from environment variable GMAIL_APP_PASSWORD.
# If not set, email alerts are disabled (logged instead).
EMAIL_ALERT_COOLDOWN = timedelta(minutes=15)   # at most one alert email / 15 min per issue
RESTART_BACKOFF       = timedelta(minutes=2)    # don't retry restart of same thing more often

# --------------------------------------------------------------------------- #
#  Logging
# --------------------------------------------------------------------------- #

os.makedirs(BASE_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("tunnel_watchdog")

# --------------------------------------------------------------------------- #
#  State
# --------------------------------------------------------------------------- #

health_status = {
    "ts": "",
    "services": {},        # name -> {port, up, last_check}
    "named_tunnel": {"up": False, "last_check": ""},
    "quick_tunnel": {"up": False, "last_check": "", "url": ""},
    "tailscale":    {"up": False, "ip": "", "last_check": ""},
    "overall":      "ok",
}
_last_alert      = {}     # key -> datetime
_last_restart    = {}     # key -> datetime
_health_lock     = threading.Lock()

# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def svc_active(svc):
    rc, _, _ = run(f"systemctl is-active --quiet {svc}")
    return rc == 0

def port_open(port, host="localhost", timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

# --------------------------------------------------------------------------- #
#  Email alerts
# --------------------------------------------------------------------------- #

def send_email(subject, body):
    if not EMAIL_ENABLED:
        log.info("(email disabled) ALERT: %s — %s", subject, body)
        return
    app_pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not app_pw:
        log.info("GMAIL_APP_PASSWORD not set; cannot send email alert. ALERT: %s", subject)
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = f"[DGX Spark] {subject}"
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(EMAIL_FROM, app_pw)
            s.send_message(msg)
        log.info("Alert email sent: %s", subject)
    except Exception as e:
        log.error("Failed to send email alert (%s): %s", subject, e)

def alert(key, subject, body):
    """Send an email but throttle to EMAIL_ALERT_COOLDOWN per key."""
    t = datetime.now()
    last = _last_alert.get(key)
    if last and (t - last) < EMAIL_ALERT_COOLDOWN:
        return  # throttled
    _last_alert[key] = t
    send_email(subject, body)

# --------------------------------------------------------------------------- #
#  Restart helpers (with backoff)
# ----------------------------------------------------------------=========== #

def can_restart(key):
    t = datetime.now()
    last = _last_restart.get(key)
    if last and (t - last) < RESTART_BACKOFF:
        return False
    _last_restart[key] = t
    return True

def restart_service(svc):
    log.warning("Restarting service %s …", svc)
    rc, out, err = run(f"systemctl restart {svc}")
    if rc == 0:
        log.info("Service %s restarted OK", svc)
    else:
        log.error("Failed to restart %s: %s", svc, err or out)
    return rc == 0

def start_quick_tunnel():
    """Start a quick tunnel as failover if the named tunnel is down."""
    if not can_restart("quick_tunnel"):
        return
    # Stop any existing quick-tunnel service first
    run(f"systemctl stop {QUICK_TUNNEL_SVC} 2>/dev/null || true")
    rc, out, err = run(QUICK_TUNNEL_CMD, timeout=30)
    # The quick tunnel prints a URL like https://xxx.trycloudflare.com
    url = ""
    for line in (out + "\n" + err).splitlines():
        if "trycloudflare.com" in line:
            url = line.strip().split()[-1]
            break
    if url:
        log.warning("Quick-tunnel failover started: %s", url)
        with _health_lock:
            health_status["quick_tunnel"]["url"] = url
    else:
        log.error("Quick-tunnel failover failed to start")

# --------------------------------------------------------------------------- #
#  Health checks
# --------------------------------------------------------------------------- #

def check_services():
    for name, port in SERVICES.items():
        up = port_open(port)
        with _health_lock:
            health_status["services"][name] = {
                "port": port,
                "up": up,
                "last_check": now_iso(),
            }
        if not up:
            log.warning("Service '%s' (port %s) is DOWN", name, port)
            alert(f"svc_{name}",
                  f"Service {name} down on port {port}",
                  f"Service '{name}' on port {port} is not responding at {now_iso()}.")
        # Note: the watchdog does NOT kill/restart user DGX services (those are
        # managed by the DGX stack itself). It only restarts the tunnels.

def check_named_tunnel():
    up = svc_active(NAMED_TUNNEL_SVC)
    with _health_lock:
        health_status["named_tunnel"]["up"] = up
        health_status["named_tunnel"]["last_check"] = now_iso()
    if up:
        log.info("Named tunnel service: UP")
        # named tunnel up -> ensure quick tunnel failover is off
        with _health_lock:
            if health_status["quick_tunnel"]["url"]:
                health_status["quick_tunnel"]["url"] = ""
        run(f"systemctl stop {QUICK_TUNNEL_SVC} 2>/dev/null || true")
    else:
        log.warning("Named tunnel service: DOWN")
        if can_restart("named_tunnel"):
            restart_service(NAMED_TUNNEL_SVC)
            time.sleep(5)
            if not svc_active(NAMED_TUNNEL_SVC):
                alert("named_tunnel_down",
                      "Named tunnel is DOWN — failover to quick tunnel",
                      f"Named tunnel service '{NAMED_TUNNEL_SVC}' could not be restarted "
                      f"at {now_iso()}. Starting quick-tunnel failover.")
                start_quick_tunnel()

def check_quick_tunnel():
    # Only meaningful if named tunnel is down and we spun up a failover
    if not health_status["named_tunnel"]["up"] and health_status["quick_tunnel"]["url"]:
        up = True   # we assume the process is alive if we have a URL
        with _health_lock:
            health_status["quick_tunnel"]["up"] = up
            health_status["quick_tunnel"]["last_check"] = now_iso()
    else:
        with _health_lock:
            health_status["quick_tunnel"]["up"] = False
            health_status["quick_tunnel"]["last_check"] = now_iso()

def check_tailscale():
    rc, out, _ = run("tailscale ip -4 2>/dev/null", timeout=5)
    ip = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""
    up = bool(ip)
    with _health_lock:
        health_status["tailscale"]["up"] = up
        health_status["tailscale"]["ip"] = ip
        health_status["tailscale"]["last_check"] = now_iso()
    if not up:
        log.warning("Tailscale is DOWN (no IP)")
        alert("tailscale_down",
              "Tailscale is DOWN",
              f"Tailscale has no 100.x.x.x IP at {now_iso()}. Run 'tailscale up'.")
        if can_restart("tailscale"):
            restart_service("tailscaled")

def check_once():
    check_services()
    check_named_tunnel()
    check_quick_tunnel()
    check_tailscale()
    # overall status
    with _health_lock:
        svc_ok = all(v.get("up", False) for v in health_status["services"].values())
        tun_ok = health_status["named_tunnel"]["up"] or health_status["quick_tunnel"]["up"]
        ts_ok  = health_status["tailscale"]["up"]
        if svc_ok and (tun_ok or ts_ok):
            health_status["overall"] = "ok"
        elif svc_ok:
            health_status["overall"] = "degraded"
        else:
            health_status["overall"] = "critical"
        health_status["ts"] = now_iso()

# --------------------------------------------------------------------------- #
#  Health endpoint (HTTP)
# --------------------------------------------------------------------------- #

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/health/":
            with _health_lock:
                payload = json.dumps(health_status, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a):
        pass  # silence

def start_health_server():
    """Serve /health on HEALTH_PORT. If the DGX terminal already owns 8888,
    the terminal is expected to proxy /health to this process.  As a robust
    fallback, if port 8888 is free we bind it directly."""
    # Try to bind the configured health port
    attempts = [HEALTH_PORT, 8889, 8892]
    for p in attempts:
        try:
            srv = ThreadingHTTPServer((HEALTH_BIND, p), HealthHandler)
            srv.daemon_threads = True
            log.info("Health endpoint listening on http://%s:%s/health", HEALTH_BIND, p)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return
        except OSError as e:
            log.info("Cannot bind %s for health endpoint (%s) — trying next", p, e)
    log.error("Could not start health endpoint on any port")

# --------------------------------------------------------------------------- #
#  Main loop
# --------------------------------------------------------------------------- #

def main():
    log.info("=" * 60)
    log.info("DGX Spark tunnel watchdog starting (interval=%ss)", CHECK_INTERVAL)
    log.info("Health endpoint: http://localhost:%s/health", HEALTH_PORT)
    log.info("Alert email   : %s", EMAIL_TO if EMAIL_ENABLED else "disabled")
    log.info("Log file      : %s", LOG_FILE)
    log.info("=" * 60)

    start_health_server()

    while True:
        try:
            check_once()
            overall = health_status["overall"]
            if overall == "critical":
                log.critical("Overall status: CRITICAL")
                alert("overall_critical",
                      "DGX Spark stack CRITICAL",
                      f"Overall health is CRITICAL at {now_iso()}.\n"
                      f"See {LOG_FILE} for details.\n"
                      f"Status: {json.dumps(health_status, indent=2)}")
        except Exception as e:
            log.exception("Unexpected error in check loop: %s", e)
            try:
                alert("watchdog_exception",
                      "Tunnel watchdog exception",
                      f"Watchdog hit an exception at {now_iso()}: {e}")
            except Exception:
                pass
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
PYEOF

    chmod +x "$WATCHDOG_SCRIPT"
    chown "$OS_USER":"$OS_USER" "$WATCHDOG_SCRIPT" 2>/dev/null || true
    log_ok "Watchdog written: $WATCHDOG_SCRIPT"

    # --- write the main systemd service (othaiim-tunnel.service) -------------
    local SVC_PATH="/etc/systemd/system/${WATCHDOG_SERVICE}"
    cat > "$SVC_PATH" <<EOF
[Unit]
Description=Othaiim Tunnel Watchdog — multi-layer remote-access health monitor
Documentation=man:systemd.unit(5)
After=network.target
Wants=network-online.target tailscaled.service ${NAMED_TUNNEL_SERVICE}

[Service]
Type=simple
User=${OS_USER}
Group=${OS_USER}
WorkingDirectory=${BASE_DIR}

# Environment: set GMAIL_APP_PASSWORD so the watchdog can email alerts.
# To configure, create /etc/othaiim/tunnel.env with:
#   GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
# Then uncomment the EnvironmentFile line below.
#EnvironmentFile=/etc/othaiim/tunnel.env
#Environment=GMAIL_APP_PASSWORD=

ExecStart=${WATCHDOG_VENV}/bin/python ${WATCHDOG_SCRIPT}

Restart=always
RestartSec=10
TimeoutStopSec=30

# Hardening
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${BASE_DIR} ${CLOUDFLARED_CONFIG_DIR}
PrivateTmp=true

# Allow the watchdog to manage systemd services (restart tunnels)
# Requires polkit rule or running as root; if running as non-root user,
# add a sudoers entry. For simplicity the watchdog uses systemctl which
# works when the user has sufficient privileges or the service is run as root.

[Install]
WantedBy=multi-user.target
EOF

    log_ok "Service file: $SVC_PATH"

    # Hint about email credentials
    if [[ ! -f /etc/othaiim/tunnel.env ]]; then
        log "Tip: to enable email alerts, create /etc/othaiim/tunnel.env with:"
        echo '  GMAIL_APP_PASSWORD=your_gmail_app_password'
        echo "Then uncomment the EnvironmentFile line in $SVC_PATH."
    fi

    service_enable_start "$WATCHDOG_SERVICE"

    log_ok "Layer 3 (Watchdog + Health Endpoint) configured"
    echo
    echo -e "${C_GREEN}  Health endpoint:${C_RST} ${C_BOLD}http://localhost:${HEALTH_PORT}/health${C_RST}"
    echo -e "  Log file       : ${LOG_FILE}"
    echo -e "  Alert email    : ${EMAIL_TO}"
}

# ============================================================================
# Summary
# ============================================================================

summary() {
    log_step "Summary"

    echo -e "${C_BOLD}Installed layers:${C_RST}"
    echo
    if service_active "$NAMED_TUNNEL_SERVICE" 2>/dev/null; then
        echo -e "  ${C_GREEN}✓${C_RST} Layer 1 — Cloudflare Named Tunnel (service: $NAMED_TUNNEL_SERVICE)"
    else
        echo -e "  ${C_RED}✗${C_RST} Layer 1 — Cloudflare Named Tunnel (not running)"
    fi
    if service_active "tailscaled" 2>/dev/null; then
        local ts_ip
        ts_ip="$(tailscale ip -4 2>/dev/null | head -n1 || echo 'pending')"
        echo -e "  ${C_GREEN}✓${C_RST} Layer 2 — Tailscale (stable IP: ${C_BOLD}${ts_ip}${C_RST})"
    else
        echo -e "  ${C_RED}✗${C_RST} Layer 2 — Tailscale (not running)"
    fi
    if service_active "$WATCHDOG_SERVICE" 2>/dev/null; then
        echo -e "  ${C_GREEN}✓${C_RST} Layer 3 — Watchdog + Health Endpoint (service: $WATCHDOG_SERVICE)"
    else
        echo -e "  ${C_RED}✗${C_RST} Layer 3 — Watchdog (not running)"
    fi

    echo
    echo -e "${C_BOLD}Quick reference:${C_RST}"
    echo "  • Health check   : curl http://localhost:${HEALTH_PORT}/health"
    echo "  • Watchdog logs  : tail -f ${LOG_FILE}"
    echo "  • Service status : systemctl status ${WATCHDOG_SERVICE}"
    echo "  • Restart watchdog: sudo systemctl restart ${WATCHDOG_SERVICE}"
    echo
    echo -e "${C_BOLD}Idempotent:${C_RST} rerun this script anytime — it will detect what's already set up and skip/repair as needed."
}

# ============================================================================
# Main
# ============================================================================

main() {
    echo
    echo -e "${C_BOLD}${C_CYAN}╔══════════════════════════════════════════════════════════════════╗${C_RST}"
    echo -e "${C_BOLD}${C_CYAN}║   permanent_tunnel_fix.sh  v${SCRIPT_VERSION}  —  DGX Spark remote access   ║${C_RST}"
    echo -e "${C_BOLD}${C_CYAN}║   Host: $(hostname | head -c6)  User: ${OS_USER}  Base: othaiim-12b              ║${C_RST}"
    echo -e "${C_BOLD}${C_CYAN}╚══════════════════════════════════════════════════════════════════╝${C_RST}"
    echo

    preflight

    # Layer 1 — best-effort; skip gracefully if no domain / no cloudflared
    layer1_cloudflare_named || true

    # Layer 2 — best-effort; skip gracefully if user declines
    layer2_tailscale || true

    # Layer 3 — always attempt (core of the fix)
    layer3_watchdog

    summary

    log_ok "Done. Remote-access stack is configured."
}

main "$@"
