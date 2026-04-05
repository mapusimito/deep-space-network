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

from simulate import simulate, generate_markdown, SimConfig, compute_dilution_rate

# --- Configuration ---
BLOCKS_PER_EPOCH = 360
BASE_UNITS = 100_000_000
MATURATION_BUFFER = 60  # extra seconds after epoch boundary for reward maturation
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
    """Returns (spendable_doli, bond_count).
    Assumes bonded field is in base units (same as confirmed).
    """
    bal = rpc_call("getBalance", {"address": address})
    spendable = bal["confirmed"] / BASE_UNITS
    bonded_raw = bal["bonded"]
    bond_count = int(bonded_raw // (10 * BASE_UNITS))
    # Sanity check: if bonded > 0 but bond_count is 0 or unreasonably high,
    # the RPC format assumption may be wrong
    if bonded_raw > 0 and (bond_count == 0 or bond_count > 500):
        log.error(f"Suspect bond_count={bond_count} from bonded={bonded_raw} — "
                  f"verify RPC 'bonded' field format (base units vs DOLI float)")
        raise RuntimeError(f"Bond count sanity check failed: bonded={bonded_raw}, derived count={bond_count}")
    return spendable, bond_count


def get_epoch_reward_from_history(address: str, producer_bonds_prev_epoch: int) -> tuple[float | None, int | None]:
    """Fetch latest epoch reward from doli history, derive total bonds.
    Uses the bond count from the PREVIOUS epoch (when the reward was earned).
    Returns (reward_amount, derived_total_bonds) or (None, None) on failure."""
    try:
        result = subprocess.run(
            ["doli", "history"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            log.warning(f"doli history failed: {result.stderr.strip()}")
            return None, None

        # Parse first Epoch_reward entry
        lines = result.stdout.splitlines()
        in_epoch_reward = False
        for line in lines:
            if "Type:     Epoch_reward" in line:
                in_epoch_reward = True
            elif in_epoch_reward and "Received:" in line:
                # Extract amount: "+0.96385542 DOLI"
                amount_str = line.split("+")[1].split(" ")[0]
                reward = float(amount_str)
                s_derived = reward / producer_bonds_prev_epoch
                derived_bonds = int(round(BLOCKS_PER_EPOCH / s_derived))
                return reward, derived_bonds
        log.warning("No Epoch_reward found in doli history")
        return None, None
    except Exception as e:
        log.warning(f"Failed to parse doli history: {e}")
        return None, None


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
    """Commit projections and push to GitHub. Pulls first to avoid rejection."""
    msg = (f"E{epoch} | bonds={total_bonds} | s={s:.4f} "
           f"| acc={accuracy:.1f}% | vps1={vps1_bonds}b vps2={vps2_bonds}b")

    # Sync with remote before committing our changes
    # Stash our generated files, pull, then pop and commit
    git_cmd("stash", "--include-untracked")
    git_cmd("pull", "--ff-only", "origin", "main")
    git_cmd("stash", "pop")

    git_cmd("add", "projections.json", "projections.md")
    git_cmd("commit", "-m", msg)

    result = subprocess.run(
        ["git", "-C", str(PROJECTIONS_DIR), "push", "origin", "main"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        log.error(f"Push failed: {result.stderr.strip()}")
        raise RuntimeError(f"git push failed: {result.stderr.strip()}")

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





def process_new_epoch(epoch: int, prev_data: dict | None):
    """Fetch real data, recalibrate, regenerate, commit, push."""
    log.info(f"Epoch {epoch} closed — waiting {MATURATION_BUFFER}s for reward maturation")
    time.sleep(MATURATION_BUFFER)

    log.info(f"Fetching real data for E{epoch}")

    # --- Measurement 1: getProducers snapshot ---
    try:
        snapshot_bonds, producer_count = get_total_bonds()
        log.info(f"Snapshot bonds: {snapshot_bonds} — producers: {producer_count}")
    except Exception as e:
        log.error(f"Failed to fetch total bonds: {e}")
        return

    # Fetch VPS balances (both from local RPC — chain knows all)
    try:
        vps1_spendable, vps1_bonds = get_balance(VPS1_ADDRESS)
        log.info(f"VPS1: {vps1_bonds} bonds, {vps1_spendable:.8f} spendable")
    except Exception as e:
        log.error(f"Failed to fetch VPS1 balance: {e}")
        return

    # --- Measurement 2: reward-derived bond count ---
    # Reward was earned during the PREVIOUS epoch, so we need the bond count
    # from that epoch. Check if the producer bonded this epoch (spendable < 1
    # and previous projection had more spendable) as a heuristic.
    prev_epoch_bonds = vps1_bonds
    if prev_data:
        for e in prev_data["epochs"]:
            if e["epoch"] == epoch - 1:
                prev_epoch_bonds = e["vps1"]["bonds"]
                break
            elif e["epoch"] == epoch:
                # If current epoch entry exists, check previous
                prev_epoch_bonds = e["vps1"]["bonds"]
                break
    # If VPS1 bonded this epoch, previous epoch had one fewer bond
    if vps1_bonds > prev_epoch_bonds:
        prev_epoch_bonds_for_reward = prev_epoch_bonds
    else:
        prev_epoch_bonds_for_reward = vps1_bonds

    reward_amount, reward_derived_bonds = get_epoch_reward_from_history(
        VPS1_ADDRESS, prev_epoch_bonds_for_reward,
    )
    if reward_derived_bonds is not None:
        log.info(f"Reward-derived bonds: {reward_derived_bonds} "
                 f"(reward={reward_amount:.8f}, "
                 f"using {prev_epoch_bonds_for_reward} bonds from prev epoch, "
                 f"s={reward_amount/prev_epoch_bonds_for_reward:.8f})")
    else:
        log.warning("Could not derive bonds from reward — using snapshot only")

    # --- Reconcile: reward-derived is mathematically exact, prefer it ---
    if reward_derived_bonds is not None:
        if reward_derived_bonds != snapshot_bonds:
            diff_pct = abs(snapshot_bonds - reward_derived_bonds) / max(snapshot_bonds, reward_derived_bonds) * 100
            log.info(f"Bond count: snapshot={snapshot_bonds} vs reward-derived={reward_derived_bonds} "
                     f"(diff={diff_pct:.1f}%) — using reward-derived")
        total_bonds = reward_derived_bonds
    else:
        total_bonds = snapshot_bonds  # fallback to snapshot

    real_s = BLOCKS_PER_EPOCH / total_bonds
    log.info(f"Final bonds: {total_bonds} — s = {real_s:.4f}")

    try:
        vps2_spendable, vps2_bonds = get_balance(VPS2_ADDRESS)
        log.info(f"VPS2: {vps2_bonds} bonds, {vps2_spendable:.8f} spendable")
    except Exception as e:
        log.error(f"Failed to fetch VPS2 balance: {e} — skipping regeneration to avoid corrupting model")
        return

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

    # Compute dilution rate from real data
    dilution_rate = compute_dilution_rate(accuracy_log)
    real_s = BLOCKS_PER_EPOCH / total_bonds
    log.info(f"Dilution rate: {dilution_rate:.4f} per epoch")

    # Simulate
    config = SimConfig(
        anchor_epoch=epoch,
        target_epoch=epoch + TARGET_EPOCH_AHEAD,
        anchor_total_bonds=total_bonds,
        anchor_s=real_s,
        dilution_rate=dilution_rate,
        vps1_bonds=vps1_bonds,
        vps1_spendable=vps1_spendable,
        vps2_bonds=vps2_bonds,
        vps2_spendable=vps2_spendable,
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

        # Sleep until next epoch boundary instead of fixed polling
        try:
            height = get_current_height()
            blocks_remaining = BLOCKS_PER_EPOCH - (height % BLOCKS_PER_EPOCH)
            seconds_remaining = blocks_remaining * 10
            sleep_time = seconds_remaining + MATURATION_BUFFER
            log.info(f"Sleeping {sleep_time}s until next epoch boundary "
                     f"({blocks_remaining} blocks remaining)")
            time.sleep(sleep_time)
        except Exception as e:
            log.error(f"Failed to calculate sleep time: {e} — sleeping 300s")
            time.sleep(300)


if __name__ == "__main__":
    main()
