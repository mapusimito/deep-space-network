#!/usr/bin/env python3
"""
DOLI Self-Updating Projection Service

Runs as a systemd service on VPS1. Detects epoch boundaries, fetches
real data via RPC, recalibrates the model, regenerates projections,
and commits/pushes to GitHub.

Every epoch close = one commit to mapusimito/deep-space-network.
Commit format: "E{epoch} | bonds={total} | s={value} | acc={accuracy}% | vps1={bonds}b vps2={bonds}b"
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from simulate import simulate, generate_markdown, SimConfig

# --- Configuration ---
BLOCKS_PER_EPOCH = 360
BASE_UNITS = 100_000_000
CHECK_INTERVAL = 300  # 5 minutes
MATURATION_WAIT = 60  # wait 60s after epoch boundary for reward maturation
TARGET_EPOCH_AHEAD = 42

VPS1_RPC = "http://127.0.0.1:8500"
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
def rpc_call(method: str, params: dict | None = None, timeout: int = 10) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        VPS1_RPC,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data["result"]


def get_current_height() -> int:
    return rpc_call("getChainInfo")["bestHeight"]


def get_total_bonds() -> tuple[int, int]:
    producers = rpc_call("getProducers", {"active_only": True})
    total_bonds = sum(p["bondCount"] for p in producers)
    return total_bonds, len(producers)


def get_balance(address: str) -> tuple[float, int]:
    """Returns (spendable_doli, bond_count)."""
    bal = rpc_call("getBalance", {"address": address})
    spendable = bal["confirmed"] / BASE_UNITS
    bond_count = int(bal["bonded"] // (10 * BASE_UNITS))
    return spendable, bond_count


# --- Git helpers ---
def git_cmd(*args) -> str:
    result = subprocess.run(
        ["git", "-C", str(PROJECTIONS_DIR)] + list(args),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        log.error(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_commit_and_push(epoch: int, total_bonds: int, s: float,
                         accuracy: float, vps1_bonds: int, vps2_bonds: int):
    """Commit projections and push to GitHub."""
    msg = (f"E{epoch} | bonds={total_bonds} | s={s:.4f} "
           f"| acc={accuracy:.1f}% | vps1={vps1_bonds}b vps2={vps2_bonds}b")

    git_cmd("add", "projections.json", "projections.md")
    git_cmd("commit", "-m", msg)
    push_result = git_cmd("push", "origin", "main")
    log.info(f"Committed and pushed: {msg}")
    return msg


# --- Projection management ---
def load_projections() -> dict | None:
    if PROJECTIONS_JSON.exists():
        with open(PROJECTIONS_JSON) as f:
            return json.load(f)
    return None


def save_projections(data: dict):
    with open(PROJECTIONS_JSON, "w") as f:
        json.dump(data, f, indent=2)
    with open(PROJECTIONS_MD, "w") as f:
        f.write(generate_markdown(data))


def recalibrate_growth(accuracy_log: list, default_accumulate: int = 22,
                        default_burst: int = 44) -> tuple[int, int]:
    """Recalibrate from last 3+ real data points. Returns defaults if insufficient data."""
    if len(accuracy_log) < 3:
        return default_accumulate, default_burst

    recent = accuracy_log[-min(4, len(accuracy_log)):]
    growths = []
    for i in range(1, len(recent)):
        ed = recent[i]["epoch"] - recent[i-1]["epoch"]
        bd = recent[i]["real_bonds"] - recent[i-1]["real_bonds"]
        if ed > 0:
            growths.append(bd / ed)

    if len(growths) < 2:
        return default_accumulate, default_burst

    avg = sum(growths) / len(growths)
    base = avg / 1.5
    return max(1, int(round(base))), max(1, int(round(base * 2)))


def process_new_epoch(epoch: int, prev_data: dict | None):
    """Fetch real data, recalibrate, regenerate, commit, push."""
    log.info(f"Epoch {epoch} closed — waiting {MATURATION_WAIT}s for reward maturation")
    time.sleep(MATURATION_WAIT)

    log.info(f"Fetching real data for E{epoch}")

    try:
        total_bonds, producer_count = get_total_bonds()
    except Exception as e:
        log.error(f"Failed to fetch total bonds: {e}")
        return

    real_s = BLOCKS_PER_EPOCH / total_bonds
    log.info(f"Real bonds: {total_bonds} — s = {real_s:.4f} — producers: {producer_count}")

    # Fetch VPS balances (both from local RPC — chain knows all)
    try:
        vps1_spendable, vps1_bonds = get_balance(VPS1_ADDRESS)
        log.info(f"VPS1: {vps1_bonds} bonds, {vps1_spendable:.8f} spendable")
    except Exception as e:
        log.error(f"Failed to fetch VPS1 balance: {e}")
        return

    try:
        vps2_spendable, vps2_bonds = get_balance(VPS2_ADDRESS)
        log.info(f"VPS2: {vps2_bonds} bonds, {vps2_spendable:.8f} spendable")
    except Exception as e:
        log.warning(f"Failed to fetch VPS2 balance: {e}")
        vps2_spendable, vps2_bonds = 0.0, 2

    # Build accuracy log
    accuracy_log = prev_data.get("accuracy_log", []) if prev_data else []
    accuracy_pct = 100.0

    if prev_data:
        projected_bonds = None
        for e in prev_data["epochs"]:
            if e["epoch"] == epoch:
                projected_bonds = e["total_bonds"]
                break

        if projected_bonds is not None:
            accuracy_pct = (1 - abs(projected_bonds - total_bonds) / total_bonds) * 100
            accuracy_log.append({
                "epoch": epoch,
                "projected_bonds": projected_bonds,
                "real_bonds": total_bonds,
                "accuracy_pct": round(accuracy_pct, 1),
            })
            log.info(f"Projected: {projected_bonds} — accuracy: {accuracy_pct:.1f}%")
            if accuracy_pct < 95:
                log.warning(f"Accuracy below 95%!")
        else:
            accuracy_log.append({
                "epoch": epoch,
                "projected_bonds": total_bonds,
                "real_bonds": total_bonds,
                "accuracy_pct": 100.0,
            })
    else:
        accuracy_log.append({
            "epoch": epoch,
            "projected_bonds": total_bonds,
            "real_bonds": total_bonds,
            "accuracy_pct": 100.0,
        })

    # Get current growth rates from previous metadata
    prev_acc = 22
    prev_burst = 44
    if prev_data:
        sg = prev_data.get("metadata", {}).get("structural_growth", {})
        prev_acc = sg.get("accumulate_epoch", 22)
        prev_burst = sg.get("burst_epoch", 44)

    new_accumulate, new_burst = recalibrate_growth(accuracy_log, prev_acc, prev_burst)
    log.info(f"Recalibrated: accumulate={new_accumulate} burst={new_burst}")

    # Simulate
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
    log.info(f"Regenerated projections E{epoch} -> E{config.target_epoch}")

    # Commit and push to GitHub
    try:
        git_commit_and_push(
            epoch, total_bonds, real_s, accuracy_pct,
            vps1_bonds, vps2_bonds,
        )
    except Exception as e:
        log.error(f"Git commit/push failed: {e}")


def main():
    log.info("DOLI projection updater starting")

    last_epoch = None
    prev_data = load_projections()
    if prev_data:
        last_epoch = prev_data["metadata"]["anchor_epoch"]
        log.info(f"Loaded existing projections anchored at E{last_epoch}")

    while True:
        try:
            height = get_current_height()
            current_epoch = height // BLOCKS_PER_EPOCH

            if last_epoch is None:
                log.info(f"First run: height={height}, epoch={current_epoch}")
                process_new_epoch(current_epoch, load_projections())
                last_epoch = current_epoch

            elif current_epoch > last_epoch:
                for ep in range(last_epoch + 1, current_epoch + 1):
                    log.info(f"New epoch boundary: E{ep} (height={height})")
                    process_new_epoch(ep, load_projections())
                last_epoch = current_epoch

        except Exception as e:
            log.error(f"Error in main loop: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
