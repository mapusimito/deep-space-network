#!/usr/bin/env python3
"""
DOLI Self-Updating Projection Service

Runs as a systemd service on VPS1. Checks every 5 minutes for new epoch
boundaries, fetches real data via RPC, recalibrates the model, and
regenerates projections.

NOTE: Projections are only as good as the last real data point.
This service keeps them fresh automatically.
"""

import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from simulate import simulate, generate_markdown, SimConfig

# --- Configuration ---
BLOCKS_PER_EPOCH = 360
BASE_UNITS = 100_000_000  # 1 DOLI = 100,000,000 base units
CHECK_INTERVAL = 300  # 5 minutes
TARGET_EPOCH_AHEAD = 42  # project 42 epochs ahead

VPS1_RPC = "http://127.0.0.1:8500"
VPS2_RPC = "http://157.90.151.47:8500"

VPS1_ADDRESS = "doli1alzfhp6jxe6lzxs55l9yajfcf64una5s8dsfnhh2xzt9lnadv9as7pjl62"
VPS2_ADDRESS = "doli17r677gnaj7cyhqlyxyfvkrfz63hggkryu9cr8fr7hl35etramxkshz2e49"

PROJECTIONS_DIR = SCRIPT_DIR
PROJECTIONS_JSON = PROJECTIONS_DIR / "projections.json"
PROJECTIONS_MD = PROJECTIONS_DIR / "projections.md"
LOG_FILE = PROJECTIONS_DIR / "update.log"

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("doli-projections")


# --- RPC helpers ---
def rpc_call(url: str, method: str, params: dict | None = None, timeout: int = 10) -> dict:
    """Make a JSON-RPC call and return the result."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data["result"]


def get_current_height() -> int:
    """Get current block height from local node."""
    info = rpc_call(VPS1_RPC, "getChainInfo")
    return info["bestHeight"]


def get_total_bonds() -> tuple[int, int]:
    """Get total bonds and producer count from network."""
    producers = rpc_call(VPS1_RPC, "getProducers", {"active_only": True})
    total_bonds = sum(p["bondCount"] for p in producers)
    return total_bonds, len(producers)


def get_balance(rpc_url: str, address: str) -> tuple[float, int]:
    """Get spendable balance and bond count for an address.
    Returns (spendable_doli, bond_count).
    """
    bal = rpc_call(rpc_url, "getBalance", {"address": address})
    spendable = bal["confirmed"] / BASE_UNITS
    bond_count = bal["bonded"] // (10 * BASE_UNITS)  # 10 DOLI per bond
    return spendable, int(bond_count)


def get_vps1_state() -> tuple[float, int]:
    """Get VPS1 spendable and bonds via local RPC."""
    return get_balance(VPS1_RPC, VPS1_ADDRESS)


def get_vps2_state() -> tuple[float, int]:
    """Get VPS2 spendable and bonds via local RPC (chain knows all balances)."""
    try:
        return get_balance(VPS1_RPC, VPS2_ADDRESS)
    except Exception as e:
        log.warning(f"Failed to fetch VPS2 balance: {e}")
        return None, None


# --- Projection management ---
def load_projections() -> dict | None:
    """Load existing projections.json if it exists."""
    if PROJECTIONS_JSON.exists():
        with open(PROJECTIONS_JSON) as f:
            return json.load(f)
    return None


def save_projections(data: dict):
    """Save projections to JSON and markdown."""
    with open(PROJECTIONS_JSON, "w") as f:
        json.dump(data, f, indent=2)
    with open(PROJECTIONS_MD, "w") as f:
        f.write(generate_markdown(data))


def recalibrate_growth(accuracy_log: list, default_accumulate: int = 22, default_burst: int = 44) -> tuple[int, int]:
    """
    Recalibrate structural growth rates from real epoch data.

    Requires at least 3 consecutive real epoch data points to adjust.
    With fewer points, returns defaults to avoid over-fitting on noise.

    Analyzes real bond growth between consecutive logged epochs,
    detects alternating pattern, and returns adjusted accumulate/burst values.
    """
    # Need at least 3 data points (2 growth intervals) to detect patterns
    if len(accuracy_log) < 3:
        return default_accumulate, default_burst

    # Use last 4 entries (or all if fewer) — want 3+ intervals
    recent = accuracy_log[-min(4, len(accuracy_log)):]

    # Calculate growth between consecutive entries
    growths = []
    for i in range(1, len(recent)):
        epoch_diff = recent[i]["epoch"] - recent[i - 1]["epoch"]
        bond_diff = recent[i]["real_bonds"] - recent[i - 1]["real_bonds"]
        if epoch_diff > 0:
            growths.append(bond_diff / epoch_diff)  # per-epoch growth rate

    if len(growths) < 2:
        return default_accumulate, default_burst

    avg_growth = sum(growths) / len(growths)

    # Maintain ~2:1 burst-to-accumulate ratio
    # avg_growth ≈ (accumulate + burst) / 2 = (x + 2x) / 2 = 1.5x
    # so x = avg_growth / 1.5
    base = avg_growth / 1.5
    new_accumulate = max(1, int(round(base)))
    new_burst = max(1, int(round(base * 2)))

    return new_accumulate, new_burst


def process_new_epoch(epoch: int, prev_data: dict | None):
    """
    Called when a new epoch boundary is detected.
    Fetches real data, logs accuracy, recalibrates, and regenerates.
    """
    log.info(f"Epoch {epoch} detected — fetching real data")

    # Fetch real network state
    try:
        total_bonds, producer_count = get_total_bonds()
    except Exception as e:
        log.error(f"Failed to fetch total bonds: {e}")
        return

    real_s = BLOCKS_PER_EPOCH / total_bonds
    log.info(f"Real bonds: {total_bonds} — s = {real_s:.4f} — producers: {producer_count}")

    # Fetch VPS states
    vps1_spendable, vps1_bonds = get_vps1_state()
    vps2_spendable, vps2_bonds = get_vps2_state()

    if vps2_spendable is None:
        # Fallback: use projected values for VPS2
        if prev_data:
            for e in prev_data["epochs"]:
                if e["epoch"] == epoch:
                    vps2_spendable = e["vps2_spendable"]
                    vps2_bonds = e["vps2_bonds"]
                    break
        if vps2_spendable is None:
            vps2_spendable = 0.0
            vps2_bonds = 2

    log.info(f"VPS1: {vps1_bonds} bonds, {vps1_spendable:.8f} spendable")
    log.info(f"VPS2: {vps2_bonds} bonds, {vps2_spendable:.8f} spendable")

    # Build accuracy log
    accuracy_log = []
    if prev_data:
        accuracy_log = prev_data.get("accuracy_log", [])

        # Check accuracy of previous projection for this epoch
        projected_bonds = None
        for e in prev_data["epochs"]:
            if e["epoch"] == epoch:
                projected_bonds = e["total_bonds"]
                break

        if projected_bonds is not None:
            accuracy = (1 - abs(projected_bonds - total_bonds) / total_bonds) * 100
            accuracy_entry = {
                "epoch": epoch,
                "projected_bonds": projected_bonds,
                "real_bonds": total_bonds,
                "accuracy_pct": round(accuracy, 1),
            }
            accuracy_log.append(accuracy_entry)
            log.info(f"Projected: {projected_bonds} — accuracy: {accuracy:.1f}%")

            if accuracy < 95:
                log.warning(f"Accuracy below 95% — model may need attention")
        else:
            log.info(f"No prior projection for E{epoch} — first data point")
            accuracy_log.append({
                "epoch": epoch,
                "projected_bonds": total_bonds,
                "real_bonds": total_bonds,
                "accuracy_pct": 100.0,
            })

    else:
        # First run, no prior data
        accuracy_log.append({
            "epoch": epoch,
            "projected_bonds": total_bonds,
            "real_bonds": total_bonds,
            "accuracy_pct": 100.0,
        })

    # Recalibrate growth rates
    new_accumulate, new_burst = recalibrate_growth(accuracy_log)
    log.info(f"Recalibrated: accumulate={new_accumulate} burst={new_burst}")

    # Build config and simulate
    config = SimConfig(
        anchor_epoch=epoch,
        target_epoch=epoch + TARGET_EPOCH_AHEAD,
        anchor_total_bonds=total_bonds,
        vps1_bonds=vps1_bonds,
        vps1_spendable=vps1_spendable,
        vps2_bonds=vps2_bonds,
        vps2_spendable=vps2_spendable,
        structural_accumulate=new_accumulate,
        structural_burst=new_burst,
        accuracy_log=accuracy_log,
    )

    new_data = simulate(config)
    new_data["accuracy_log"] = accuracy_log
    save_projections(new_data)

    log.info(f"Regenerated projections E{epoch}→E{config.target_epoch}")


def main():
    """Main loop: check for new epochs every 5 minutes."""
    log.info("DOLI projection updater starting")

    last_epoch = None

    # Load existing projections to get last known epoch
    prev_data = load_projections()
    if prev_data:
        last_epoch = prev_data["metadata"]["anchor_epoch"]
        log.info(f"Loaded existing projections anchored at E{last_epoch}")

    while True:
        try:
            height = get_current_height()
            current_epoch = height // BLOCKS_PER_EPOCH

            if last_epoch is None:
                # First run — process current epoch
                log.info(f"First run: height={height}, epoch={current_epoch}")
                prev_data = load_projections()
                process_new_epoch(current_epoch, prev_data)
                last_epoch = current_epoch

            elif current_epoch > last_epoch:
                # New epoch(s) detected
                # Process each missed epoch (in case we missed some)
                for epoch in range(last_epoch + 1, current_epoch + 1):
                    log.info(f"New epoch boundary: E{epoch} (height={height})")
                    prev_data = load_projections()
                    process_new_epoch(epoch, prev_data)

                last_epoch = current_epoch

        except Exception as e:
            log.error(f"Error in main loop: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
