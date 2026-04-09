#!/bin/bash
# DOLI Node Doctor & Watchdog — unified health management
# Handles: permission fixes, lock cleanup, version upgrades,
#          RPC health checks, sync monitoring, auto-recovery.
#
# Usage:
#   doli-doctor doctor     — diagnose and fix common problems
#   doli-doctor watchdog   — check health + auto-recover if needed
#   doli-doctor status     — quick health report
#
# Install as systemd timer for continuous monitoring.

set -euo pipefail

SERVICE="doli-mainnet"
DATA_DIR="/var/lib/doli/mainnet"
LOG_DIR="/var/log/doli"
RPC_URL="http://127.0.0.1:8500"
LOCK_FILE="$DATA_DIR/producer.lock"
VERSION_FILE="/tmp/doli-version"
DOCTOR_LOG="$LOG_DIR/doctor.log"
NODE_USER="doli"
NODE_GROUP="doli"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [doli-doctor] $1"
    echo "$msg"
    echo "$msg" >> "$DOCTOR_LOG" 2>/dev/null || true
}

# --- Individual checks ---

fix_permissions() {
    local bad_files
    bad_files=$(find "$DATA_DIR" -not -user "$NODE_USER" 2>/dev/null | head -20)
    if [ -n "$bad_files" ]; then
        log "FIX: Found files not owned by $NODE_USER — fixing permissions"
        chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"
        return 1  # was broken
    fi
    return 0
}

fix_lock_file() {
    if [ -f "$LOCK_FILE" ]; then
        # Check if the service is actually running
        if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
            log "FIX: Stale lock file found (service not running) — removing"
            rm -f "$LOCK_FILE"
            return 1
        fi
    fi
    return 0
}

check_disk() {
    local usage
    usage=$(df "$DATA_DIR" --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
    if [ -n "$usage" ] && [ "$usage" -gt 90 ]; then
        log "WARN: Disk usage at ${usage}% — dangerously high"
        return 1
    fi
    return 0
}

check_memory() {
    local available
    available=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null)
    if [ -n "$available" ] && [ "$available" -lt 200 ]; then
        log "WARN: Only ${available}MB RAM available — may OOM"
        return 1
    fi
    return 0
}

detect_version_change() {
    local current stored
    current=$(/usr/bin/doli-node --version 2>/dev/null || echo "unknown")
    stored=$(cat "$VERSION_FILE" 2>/dev/null || echo "")

    if [ "$current" != "$stored" ]; then
        log "VERSION CHANGE: '$stored' -> '$current'"
        echo "$current" > "$VERSION_FILE"
        return 1  # version changed
    fi
    return 0
}

handle_version_upgrade() {
    log "Handling version upgrade — stopping service, cleaning state, restarting"

    # Stop service
    systemctl stop "$SERVICE" 2>/dev/null || true
    sleep 2

    # Fix permissions (new binary may have created files as root during update)
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"

    # Remove lock file
    rm -f "$LOCK_FILE"

    # Wipe state_db and utxo_store — node will re-sync via snap sync
    # These are rebuilt from the network, wallet.json and signed_slots.db are preserved
    if [ -d "$DATA_DIR/state_db" ]; then
        log "Wiping state_db for clean re-sync"
        rm -rf "$DATA_DIR/state_db"
    fi
    if [ -d "$DATA_DIR/utxo_store" ]; then
        log "Wiping utxo_store for clean re-sync"
        rm -rf "$DATA_DIR/utxo_store"
    fi
    if [ -d "$DATA_DIR/blocks" ]; then
        log "Wiping blocks for clean re-sync"
        rm -rf "$DATA_DIR/blocks"
    fi

    # Re-create dirs with correct ownership
    mkdir -p "$DATA_DIR/state_db" "$DATA_DIR/utxo_store" "$DATA_DIR/blocks"
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"

    log "State wiped — node will snap-sync from peers on next start"
}

check_rpc() {
    local response
    response=$(curl -sf -m 5 -X POST "$RPC_URL" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"getChainInfo","params":{},"id":1}' 2>/dev/null)

    if [ -z "$response" ]; then
        log "RPC: not responding"
        return 1
    fi

    local height
    height=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['bestHeight'])" 2>/dev/null || echo "0")

    if [ "$height" = "0" ]; then
        log "RPC: responding but height=0"
        return 1
    fi

    echo "$height"
    return 0
}

check_sync_progress() {
    local h1 h2
    h1=$(check_rpc 2>/dev/null) || return 1
    sleep 15
    h2=$(check_rpc 2>/dev/null) || return 1

    if [ "$h1" = "$h2" ]; then
        log "SYNC: height stuck at $h1 for 15 seconds"
        return 1
    fi
    return 0
}

# --- Composite commands ---

doctor() {
    log "=== DOCTOR: Running diagnostics ==="
    local issues=0

    # 1. Permissions
    fix_permissions || issues=$((issues + 1))

    # 2. Lock file
    fix_lock_file || issues=$((issues + 1))

    # 3. Disk
    check_disk || issues=$((issues + 1))

    # 4. Memory
    check_memory || issues=$((issues + 1))

    # 5. Version change
    if ! detect_version_change; then
        handle_version_upgrade
        issues=$((issues + 1))
    fi

    # 6. Final permission pass (in case upgrade created new files)
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR" 2>/dev/null || true

    if [ "$issues" -eq 0 ]; then
        log "DOCTOR: All checks passed — no issues found"
    else
        log "DOCTOR: Fixed $issues issue(s)"
    fi

    return 0
}

watchdog() {
    log "=== WATCHDOG: Health check ==="

    # Is the service running?
    if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
        log "WATCHDOG: Service not active — running doctor and restarting"
        doctor
        systemctl reset-failed "$SERVICE" 2>/dev/null || true
        systemctl start "$SERVICE"
        sleep 10

        if systemctl is-active --quiet "$SERVICE"; then
            log "WATCHDOG: Service restarted successfully"
        else
            log "WATCHDOG: Service failed to start after doctor — check manually"
            # One more try: full state wipe
            log "WATCHDOG: Attempting full state wipe + restart"
            handle_version_upgrade
            systemctl reset-failed "$SERVICE" 2>/dev/null || true
            systemctl start "$SERVICE"
            sleep 10
            if systemctl is-active --quiet "$SERVICE"; then
                log "WATCHDOG: Recovery successful after state wipe"
            else
                log "WATCHDOG: CRITICAL — cannot recover node. Manual intervention needed."
            fi
        fi
        return
    fi

    # Service is running — check RPC
    local height
    height=$(check_rpc 2>/dev/null)
    if [ $? -ne 0 ]; then
        log "WATCHDOG: Service active but RPC unresponsive — giving 30s grace"
        sleep 30
        height=$(check_rpc 2>/dev/null)
        if [ $? -ne 0 ]; then
            log "WATCHDOG: RPC still down — restarting service"
            systemctl restart "$SERVICE"
        else
            log "WATCHDOG: RPC recovered (height=$height)"
        fi
        return
    fi

    log "WATCHDOG: Healthy (height=$height)"
}

status() {
    echo "=== DOLI Node Status ==="
    echo "Service:  $(systemctl is-active $SERVICE 2>/dev/null || echo 'unknown')"
    echo "Version:  $(/usr/bin/doli-node --version 2>/dev/null || echo 'unknown')"
    echo "Stored:   $(cat $VERSION_FILE 2>/dev/null || echo 'none')"

    local height
    height=$(check_rpc 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "RPC:      responding (height=$height)"
    else
        echo "RPC:      not responding"
    fi

    echo "Disk:     $(df -h $DATA_DIR --output=avail 2>/dev/null | tail -1 | xargs) available"
    echo "Memory:   $(awk '/MemAvailable/ {printf "%.0f MB", $2/1024}' /proc/meminfo 2>/dev/null)"

    local bad
    bad=$(find "$DATA_DIR" -not -user "$NODE_USER" 2>/dev/null | wc -l)
    echo "Perms:    $bad files with wrong ownership"

    if [ -f "$LOCK_FILE" ]; then
        echo "Lock:     present (PID=$(cat $LOCK_FILE 2>/dev/null || echo '?'))"
    else
        echo "Lock:     none"
    fi
}

# --- Main ---

mkdir -p "$LOG_DIR"

case "${1:-watchdog}" in
    doctor)   doctor ;;
    watchdog) watchdog ;;
    status)   status ;;
    *)
        echo "Usage: $0 {doctor|watchdog|status}"
        exit 1
        ;;
esac
