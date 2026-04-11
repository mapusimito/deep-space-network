#!/bin/bash
# DOLI Node Doctor, Watchdog, Autoupgrader & Autobonder v4
# Modeled after VPS2's proven architecture.
#
# Handles: permission fixes, lock cleanup, version upgrades (via doli snap),
#          RPC health checks, sync monitoring, auto-recovery, auto-upgrade,
#          auto-bonding when spendable >= BOND_THRESHOLD.
#
# Usage:
#   doli-doctor doctor     — diagnose and fix common problems
#   doli-doctor watchdog   — check health + auto-recover if needed
#   doli-doctor upgrade    — check for updates and apply if available
#   doli-doctor autobond   — check balance and bond if possible
#   doli-doctor status     — quick health report
#   doli-doctor cycle      — full cycle: upgrade + watchdog + autobond (default)
#
# Runs every 3 minutes via systemd timer.

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
BOND_THRESHOLD="10.01"
VPS1_ADDRESS="doli1alzfhp6jxe6lzxs55l9yajfcf64una5s8dsfnhh2xzt9lnadv9as7pjl62"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [doli-doctor] $1"
    echo "$msg"
    echo "$msg" >> "$DOCTOR_LOG" 2>/dev/null || true
}

# --- Health checks ---

fix_permissions() {
    local bad_count
    bad_count=$(find "$DATA_DIR" -not -user "$NODE_USER" 2>/dev/null | wc -l)
    if [ "$bad_count" -gt 0 ]; then
        log "FIX: $bad_count files with wrong ownership — fixing"
    fi
    # Always enforce VPS2 permission pattern: doli:doli, group write, setgid on dirs
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"
    chmod -R g+w "$DATA_DIR"
    find "$DATA_DIR" -type d -exec chmod g+ws {} \; 2>/dev/null
    if [ "$bad_count" -gt 0 ]; then
        return 1
    fi
    return 0
}

fix_lock_file() {
    if [ -f "$LOCK_FILE" ]; then
        if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
            log "FIX: Stale lock file (service not running) — removing"
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
        log "WARN: Disk at ${usage}%"
        return 1
    fi
    return 0
}

check_memory() {
    local available
    available=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null)
    if [ -n "$available" ] && [ "$available" -lt 200 ]; then
        log "WARN: Only ${available}MB RAM"
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
        return 1
    fi
    return 0
}

# Check the registry for a newer release and upgrade if available.
# Uses `doli upgrade --yes --service doli-mainnet` (VPS2's proven command).
# The doli CLI handles: stop service -> replace binary -> restart service.
# After upgrade, doctor's version change detection will trigger snap recovery.
check_upgrade() {
    log "Checking for upgrades via doli upgrade"

    local before after upgrade_output rc
    before=$(/usr/bin/doli-node --version 2>/dev/null || echo "unknown")

    # Run upgrade command non-interactively, targeting the specific service.
    # Capture output so we can report on it.
    upgrade_output=$(/usr/bin/doli upgrade --yes --service "$SERVICE" 2>&1)
    rc=$?

    if [ "$rc" -ne 0 ]; then
        log "UPGRADE: command failed (rc=$rc): $(echo "$upgrade_output" | tail -3 | tr '\n' ' | ')"
        return 1
    fi

    after=$(/usr/bin/doli-node --version 2>/dev/null || echo "unknown")

    if [ "$before" = "$after" ]; then
        log "UPGRADE: Already up to date ($before)"
        return 0
    fi

    log "UPGRADE: Applied '$before' -> '$after'"
    log "Upgrade output: $(echo "$upgrade_output" | tail -3 | tr '\n' ' | ')"

    # The CLI should have restarted the service. Give it time to come up.
    sleep 10

    # Write new version so detect_version_change is consistent
    echo "$after" > "$VERSION_FILE"

    # After upgrade: snap recovery to handle any state format incompatibility.
    # This is the VPS1 lesson — the CLI does its best but state_db may still
    # have permission issues or format mismatches that only snap can fix.
    log "UPGRADE: Running snap recovery after binary upgrade"
    run_snap_recovery || log "UPGRADE: snap recovery had issues — check status"

    return 0
}

# Use `doli snap` for recovery — the VPS2 pattern.
# This downloads a verified state snapshot from peers, much cleaner
# than manual wipe. Preserves wallet index and transaction history.
run_snap_recovery() {
    log "Running snap recovery (doli snap)"
    systemctl stop "$SERVICE" 2>/dev/null || true
    sleep 3
    rm -f "$LOCK_FILE"
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"
    find "$DATA_DIR" -type d -exec chmod g+s {} \; 2>/dev/null

    # Run doli snap as doli user — it wipes and re-syncs cleanly
    local snap_output
    snap_output=$(sudo -u "$NODE_USER" /usr/bin/doli snap --no-restart 2>&1) || true
    log "Snap output: $(echo "$snap_output" | tail -3)"

    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR"
    systemctl reset-failed "$SERVICE" 2>/dev/null || true
    systemctl start "$SERVICE"
    sleep 15

    if systemctl is-active --quiet "$SERVICE"; then
        log "Snap recovery successful — service running"
        return 0
    else
        log "Snap recovery failed — service still down"
        return 1
    fi
}

check_rpc() {
    local response height
    response=$(curl -sf -m 5 -X POST "$RPC_URL" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"getChainInfo","params":{},"id":1}' 2>/dev/null) || return 1

    height=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['bestHeight'])" 2>/dev/null) || return 1

    if [ -z "$height" ] || [ "$height" = "0" ]; then
        return 1
    fi
    echo "$height"
    return 0
}

check_sync() {
    local height
    height=$(check_rpc 2>/dev/null) || return 1
    if [ "$height" = "0" ] || [ "$height" -lt 2 ]; then
        log "SYNC: height is $height — needs snap recovery"
        return 1
    fi
    return 0
}

# --- Composite commands ---

doctor() {
    log "=== DOCTOR ==="
    local issues=0

    fix_permissions || issues=$((issues + 1))
    fix_lock_file || issues=$((issues + 1))
    check_disk || issues=$((issues + 1))
    check_memory || issues=$((issues + 1))

    if ! detect_version_change; then
        log "Version changed — running snap recovery for clean state"
        run_snap_recovery || log "WARN: Snap recovery had issues"
        issues=$((issues + 1))
    fi

    # Final permission pass
    chown -R "$NODE_USER:$NODE_GROUP" "$DATA_DIR" 2>/dev/null || true

    if [ "$issues" -eq 0 ]; then
        log "DOCTOR: All clear"
    else
        log "DOCTOR: Fixed $issues issue(s)"
    fi
}

watchdog() {
    log "=== WATCHDOG ==="

    # Is service running?
    if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
        log "Service not active — running doctor"
        doctor
        # If doctor didn't start it, try explicitly
        if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
            systemctl reset-failed "$SERVICE" 2>/dev/null || true
            systemctl start "$SERVICE" 2>/dev/null || true
            sleep 10
        fi
        # Still down? Snap recovery
        if ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
            log "Still down after doctor — escalating to snap recovery"
            run_snap_recovery || log "CRITICAL: Cannot recover"
        fi
        return
    fi

    # Service running — check RPC
    local height
    height=$(check_rpc 2>/dev/null)
    if [ $? -ne 0 ]; then
        log "RPC unresponsive — 30s grace"
        sleep 30
        height=$(check_rpc 2>/dev/null)
        if [ $? -ne 0 ]; then
            log "RPC still down — restarting"
            systemctl restart "$SERVICE"
            sleep 15
            height=$(check_rpc 2>/dev/null)
            if [ $? -ne 0 ]; then
                log "Restart didn't fix RPC — snap recovery"
                run_snap_recovery || true
            fi
        fi
        return
    fi

    # Check sync health (height > 0)
    if [ "$height" -lt 2 ]; then
        log "Height stuck at $height — snap recovery"
        run_snap_recovery || true
        return
    fi

    log "WATCHDOG: Healthy (h=$height)"
}

status() {
    echo "=== DOLI Node Status ==="
    echo "Service:  $(systemctl is-active $SERVICE 2>/dev/null || echo 'unknown')"
    echo "Version:  $(/usr/bin/doli-node --version 2>/dev/null || echo 'unknown')"
    echo "Stored:   $(cat $VERSION_FILE 2>/dev/null || echo 'none')"

    local height
    height=$(check_rpc 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "RPC:      responding (h=$height)"
    else
        echo "RPC:      not responding"
    fi

    echo "Disk:     $(df -h $DATA_DIR --output=avail 2>/dev/null | tail -1 | xargs) free"
    echo "Memory:   $(awk '/MemAvailable/ {printf "%.0f MB", $2/1024}' /proc/meminfo 2>/dev/null)"

    local bad
    bad=$(find "$DATA_DIR" -not -user "$NODE_USER" 2>/dev/null | wc -l)
    echo "Perms:    $bad files with wrong ownership"

    if [ -f "$LOCK_FILE" ]; then
        echo "Lock:     present"
    else
        echo "Lock:     none"
    fi

    # Balance check via RPC (always works, even if wallet index is stale)
    local bal
    bal=$(curl -sf -m 5 -X POST "$RPC_URL" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"getBalance","params":{"address":"doli1alzfhp6jxe6lzxs55l9yajfcf64una5s8dsfnhh2xzt9lnadv9as7pjl62"},"id":1}' 2>/dev/null)
    if [ -n "$bal" ]; then
        local bonded spendable
        bonded=$(echo "$bal" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['bonded']/100000000)" 2>/dev/null || echo "?")
        spendable=$(echo "$bal" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['confirmed']/100000000)" 2>/dev/null || echo "?")
        echo "Bonded:   $bonded DOLI"
        echo "Spend:    $spendable DOLI"
    fi
}

# Autobond — matches VPS2's check_and_bond logic exactly, but stateless.
# Runs on every cycle (every 3 min). The bond threshold and formula are
# identical to VPS2: bonds_to_add = floor(spendable / 10.01).
#
# Unlike VPS2's sleep-based daemon, this runs as a one-shot each cycle:
# - Cannot silently die (no long-running process to crash)
# - Auto-recovers if doctor restarts the node
# - Idempotent: reads current balance every time, bonds what's bondable
autobond() {
    log "=== AUTOBOND ==="

    # 1. Wait for node RPC (equivalent to VPS2's wait_for_node but bounded)
    local height
    height=$(check_rpc 2>/dev/null)
    if [ $? -ne 0 ]; then
        log "AUTOBOND: RPC not responding — skipping (doctor will handle recovery)"
        return 0
    fi

    # 2. Check sync (equivalent to VPS2's check_sync — height must be > 0)
    if [ "$height" -lt 2 ]; then
        log "AUTOBOND: node not synced (h=$height) — skipping"
        return 0
    fi

    # 3. Log epoch info (equivalent to VPS2's get_epoch_info)
    local current_epoch blocks_into_epoch blocks_remaining
    current_epoch=$(( height / 360 ))
    blocks_into_epoch=$(( height % 360 ))
    blocks_remaining=$(( 360 - blocks_into_epoch ))
    log "AUTOBOND: epoch=$current_epoch height=$height blocks_into_epoch=$blocks_into_epoch blocks_remaining=$blocks_remaining"

    # 4. Maturation window check — VPS2 waits 60 blocks (600s) after the epoch
    # boundary for reward maturation. We do the same: skip the first 60 blocks.
    # This ensures epoch rewards are mature (whitepaper 10.7: 6 confirmations).
    if [ "$blocks_into_epoch" -lt 60 ]; then
        log "AUTOBOND: in maturation window ($blocks_into_epoch/60 blocks) — rewards not mature yet, skipping"
        return 0
    fi

    # 5. Check and bond (equivalent to VPS2's check_and_bond)
    # Read spendable via RPC — more reliable than CLI (wallet index can lag).
    local bal_json spendable_base spendable_doli
    bal_json=$(curl -sf -m 5 -X POST "$RPC_URL" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"getBalance\",\"params\":{\"address\":\"$VPS1_ADDRESS\"},\"id\":1}" 2>/dev/null)

    if [ -z "$bal_json" ]; then
        log "AUTOBOND: WARNING — could not read balance — skipping"
        return 0
    fi

    spendable_base=$(echo "$bal_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['confirmed'])" 2>/dev/null)
    if [ -z "$spendable_base" ]; then
        log "AUTOBOND: WARNING — could not parse balance — skipping"
        return 0
    fi

    spendable_doli=$(python3 -c "print(f'{$spendable_base / 100000000:.8f}')" 2>/dev/null || echo "0")

    # Compute bonds_to_add = floor(spendable / 10.01) — matches VPS2 exactly
    local bonds_to_add
    bonds_to_add=$(python3 -c "print(int($spendable_doli / $BOND_THRESHOLD))" 2>/dev/null || echo "0")

    log "AUTOBOND: Spendable: $spendable_doli DOLI — bonds to add: $bonds_to_add"

    if [ "$bonds_to_add" -lt 1 ]; then
        log "AUTOBOND: Balance insufficient — skipping"
        return 0
    fi

    # 6. Execute bond command (equivalent to VPS2's add-bond call)
    log "AUTOBOND: Adding $bonds_to_add bond(s)"
    local bond_output bond_rc
    bond_output=$(/usr/bin/doli producer add-bond --count "$bonds_to_add" --yes 2>&1)
    bond_rc=$?

    if [ "$bond_rc" -eq 0 ]; then
        log "AUTOBOND: Result: $(echo "$bond_output" | tail -3 | tr '\n' ' | ')"
    else
        log "AUTOBOND: FAILED (rc=$bond_rc): $(echo "$bond_output" | tail -3 | tr '\n' ' | ')"
    fi
}

cycle() {
    log "=== CYCLE (upgrade + watchdog + autobond) ==="
    # Step 1: check for upgrades (and apply if any)
    check_upgrade || log "CYCLE: upgrade check failed, continuing"
    # Step 2: health watchdog (may trigger snap recovery if needed)
    watchdog
    # Step 3: autobond — only runs if watchdog found node healthy
    if systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
        autobond || log "CYCLE: autobond had issues, continuing"
    else
        log "CYCLE: service not active, skipping autobond"
    fi
}

# --- Main ---
mkdir -p "$LOG_DIR"

case "${1:-cycle}" in
    doctor)   doctor ;;
    watchdog) watchdog ;;
    upgrade)  check_upgrade ;;
    autobond) autobond ;;
    status)   status ;;
    cycle)    cycle ;;
    *)        echo "Usage: $0 {doctor|watchdog|upgrade|autobond|status|cycle}"; exit 1 ;;
esac
