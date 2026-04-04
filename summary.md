# DOLI Projections System — Code Summary
Generated: Sat Apr  4 17:34:42 UTC 2026

## simulate.py
```
#!/usr/bin/env python3
"""
DOLI Epoch Simulation Engine — Pessimistic Projection Model

Simulates epoch-by-epoch network growth and reward distribution
from an anchor epoch to a target epoch.

Core formula: s = 360 / total_bonds (share per bond per epoch)
Reward per producer = producer_bonds * s

NOTE: Projections should be regenerated every time real epoch data
comes in via the recalibrate command. The model is only as good as
its last real data point.
"""

import json
import math
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional


# --- Constants ---
BLOCKS_PER_EPOCH = 360
BOND_COST = 10.0
BOND_THRESHOLD = 10.01  # autobond triggers at this spendable balance
REWARD_PER_BLOCK = 1.0  # 1 DOLI per block into reward pool


@dataclass
class ProducerState:
    """Tracks a single producer's bonds and spendable balance."""
    name: str
    bonds: int
    spendable: float = 0.0
    bonded_this_epoch: bool = False

    def earn(self, s: float):
        """Add epoch reward based on current bonds and share value."""
        reward = self.bonds * s
        self.spendable += reward
        return reward

    def try_bond(self) -> bool:
        """Attempt to bond if spendable >= threshold. Returns True if bonded."""
        self.bonded_this_epoch = False
        if self.spendable >= BOND_THRESHOLD:
            self.spendable -= BOND_COST
            # Bond takes effect NEXT epoch (epoch-deferred)
            # We mark it, caller increments bonds next epoch
            self.bonded_this_epoch = True
            return True
        return False


@dataclass
class SimConfig:
    """Configuration for the simulation."""
    anchor_epoch: int = 18
    target_epoch: int = 60
    anchor_total_bonds: int = 635
    model: str = "pessimistic"

    # VPS initial states
    vps1_bonds: int = 2
    vps1_spendable: float = 7.54
    vps2_bonds: int = 2
    vps2_spendable: float = 0.31

    # Structural nodes: alternating pattern from anchor
    # Odd offset epochs: +35 (accumulate), Even offset epochs: +70 (burst)
    structural_accumulate: int = 35
    structural_burst: int = 70

    # Mid miners (N7-N13): 7 producers, +1 bond each per 2 epochs
    mid_miner_count: int = 7
    mid_miner_bonds_per_2_epochs: int = 1  # per producer

    # Accuracy log from previous calibrations
    accuracy_log: list = field(default_factory=list)


@dataclass
class EpochResult:
    """Result for a single epoch."""
    epoch: int
    total_bonds: int
    s: float
    vps1_bonds: int
    vps1_spendable: float
    vps1_reward: float
    vps1_bonded: bool
    vps2_bonds: int
    vps2_spendable: float
    vps2_reward: float
    vps2_bonded: bool
    combined_reward: float
    network_growth: int


def compute_network_growth(epoch_offset: int, config: SimConfig) -> int:
    """
    Compute bonds added by non-VPS producers this epoch.

    Structural nodes: alternating pattern
      - Odd offset: +accumulate (35)
      - Even offset: +burst (70)

    Mid miners (N7-N13): +1 bond per producer every 2 epochs
      = +7 bonds every 2 epochs = +3.5 avg/epoch
      We add mid_miner_count bonds on even offsets, 0 on odd.
    """
    # Structural growth
    if epoch_offset % 2 == 1:
        structural = config.structural_accumulate
    else:
        structural = config.structural_burst

    # Mid miner growth: +1 per producer every 2 epochs
    if epoch_offset % 2 == 0 and epoch_offset > 0:
        mid_miners = config.mid_miner_count * config.mid_miner_bonds_per_2_epochs
    else:
        mid_miners = 0

    return structural + mid_miners


def simulate(config: Optional[SimConfig] = None) -> dict:
    """
    Run epoch-by-epoch simulation from anchor to target.

    Returns dict with metadata, epochs array, and accuracy_log.
    """
    if config is None:
        config = SimConfig()

    vps1 = ProducerState("VPS1 (mapusisimito)", config.vps1_bonds, config.vps1_spendable)
    vps2 = ProducerState("VPS2 (df80f5d70af4)", config.vps2_bonds, config.vps2_spendable)

    epochs = []
    total_bonds = config.anchor_total_bonds

    # Track deferred bonds (bonds purchased this epoch take effect next epoch)
    vps1_pending_bond = False
    vps2_pending_bond = False

    for epoch in range(config.anchor_epoch, config.target_epoch + 1):
        offset = epoch - config.anchor_epoch

        # Apply deferred bonds from previous epoch
        if vps1_pending_bond:
            vps1.bonds += 1
            vps1_pending_bond = False
        if vps2_pending_bond:
            vps2.bonds += 1
            vps2_pending_bond = False

        # Calculate share value
        s = BLOCKS_PER_EPOCH / total_bonds

        # Earn rewards
        vps1_reward = vps1.earn(s)
        vps2_reward = vps2.earn(s)

        # Try to bond (after earning)
        if vps1.try_bond():
            vps1_pending_bond = True
        if vps2.try_bond():
            vps2_pending_bond = True

        # Calculate network growth for NEXT epoch
        # (current epoch's bonds are already set)
        if offset >= 0:
            next_offset = offset + 1
            growth = compute_network_growth(next_offset, config)
        else:
            growth = 0

        # Add VPS bonds to next epoch's growth count
        vps_growth = (1 if vps1.bonded_this_epoch else 0) + (1 if vps2.bonded_this_epoch else 0)

        result = EpochResult(
            epoch=epoch,
            total_bonds=total_bonds,
            s=round(s, 4),
            vps1_bonds=vps1.bonds,
            vps1_spendable=round(vps1.spendable, 8),
            vps1_reward=round(vps1_reward, 8),
            vps1_bonded=vps1.bonded_this_epoch,
            vps2_bonds=vps2.bonds,
            vps2_spendable=round(vps2.spendable, 8),
            vps2_reward=round(vps2_reward, 8),
            vps2_bonded=vps2.bonded_this_epoch,
            combined_reward=round(vps1_reward + vps2_reward, 8),
            network_growth=growth + vps_growth,
        )
        epochs.append(result)

        # Advance total_bonds for next epoch
        total_bonds += growth + vps_growth

    # Build output
    output = {
        "metadata": {
            "anchor_epoch": config.anchor_epoch,
            "anchor_total_bonds": config.anchor_total_bonds,
            "target_epoch": config.target_epoch,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": config.model,
        },
        "epochs": [asdict(e) for e in epochs],
        "accuracy_log": config.accuracy_log,
    }

    return output


def generate_markdown(data: dict) -> str:
    """Generate human-readable markdown table from simulation data."""
    lines = [
        "# DOLI Epoch Projections — Pessimistic Model",
        "",
        f"**Anchor:** E{data['metadata']['anchor_epoch']} "
        f"({data['metadata']['anchor_total_bonds']} bonds)",
        f"**Generated:** {data['metadata']['generated_at']}",
        f"**Model:** {data['metadata']['model']}",
        "",
        "| Epoch | Total bonds | s | VPS1 bonds | VPS1 spendable | VPS2 bonds | VPS2 spendable | Combined reward | Bond events |",
        "|------:|------------:|------:|-----------:|---------------:|-----------:|---------------:|----------------:|:------------|",
    ]

    for e in data["epochs"]:
        events = []
        if e["vps1_bonded"]:
            events.append("VPS1 bonds")
        if e["vps2_bonded"]:
            events.append("VPS2 bonds")
        event_str = ", ".join(events) if events else "-"

        lines.append(
            f"| {e['epoch']:>5} "
            f"| {e['total_bonds']:>11} "
            f"| {e['s']:>5.4f} "
            f"| {e['vps1_bonds']:>10} "
            f"| {e['vps1_spendable']:>14.4f} "
            f"| {e['vps2_bonds']:>10} "
            f"| {e['vps2_spendable']:>14.4f} "
            f"| {e['combined_reward']:>15.4f} "
            f"| {event_str} |"
        )

    # Accuracy log
    if data.get("accuracy_log"):
        lines.extend([
            "",
            "## Accuracy Log",
            "",
            "| Epoch | Projected bonds | Real bonds | Accuracy % |",
            "|------:|----------------:|-----------:|-----------:|",
        ])
        for entry in data["accuracy_log"]:
            lines.append(
                f"| {entry['epoch']:>5} "
                f"| {entry['projected_bonds']:>15} "
                f"| {entry['real_bonds']:>10} "
                f"| {entry['accuracy_pct']:>10.1f} |"
            )

    lines.append("")
    return "\n".join(lines)


def save_projections(output_dir: str = "."):
    """Run simulation and save projections.json and projections.md."""
    import os

    data = simulate()

    json_path = os.path.join(output_dir, "projections.json")
    md_path = os.path.join(output_dir, "projections.md")

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    with open(md_path, "w") as f:
        f.write(generate_markdown(data))

    return data


def load_config_from_json(json_path: str) -> SimConfig:
    """Load a SimConfig from an existing projections.json (for recalibration)."""
    with open(json_path) as f:
        data = json.load(f)

    meta = data["metadata"]
    # Find the anchor epoch data
    anchor_epoch_data = None
    for e in data["epochs"]:
        if e["epoch"] == meta["anchor_epoch"]:
            anchor_epoch_data = e
            break

    config = SimConfig(
        anchor_epoch=meta["anchor_epoch"],
        anchor_total_bonds=meta["anchor_total_bonds"],
        target_epoch=meta.get("target_epoch", 60),
        model=meta.get("model", "pessimistic"),
        accuracy_log=data.get("accuracy_log", []),
    )

    if anchor_epoch_data:
        config.vps1_bonds = anchor_epoch_data["vps1_bonds"]
        config.vps1_spendable = anchor_epoch_data["vps1_spendable"]
        config.vps2_bonds = anchor_epoch_data["vps2_bonds"]
        config.vps2_spendable = anchor_epoch_data["vps2_spendable"]

    return config


if __name__ == "__main__":
    data = save_projections()
    print(f"Generated projections for E{data['metadata']['anchor_epoch']} "
          f"to E{data['metadata']['target_epoch']}")
    print(f"Saved to projections.json and projections.md")
```

## update.py
```
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
```

## query.py
```
#!/usr/bin/env python3
"""
DOLI Projection Query Interface

Natural language CLI for querying epoch projections and recalibrating
the simulation model with real data.

Usage:
    python query.py "when does vps1 next bond"
    python query.py "what is s at epoch 25"
    python query.py "combined reward at epoch 30"
    python query.py "how many bonds do we have at epoch 40"
    python query.py "when do we reach 5 bonds each"
    python query.py "accuracy check e19 actual_bonds=670"
    python query.py "recalibrate e19 total_bonds=670"
"""

import json
import os
import re
import sys
from simulate import simulate, generate_markdown, SimConfig, load_config_from_json

PROJECTIONS_FILE = os.path.join(os.path.dirname(__file__), "projections.json")


def load_projections() -> dict:
    """Load projections from JSON file."""
    with open(PROJECTIONS_FILE) as f:
        return json.load(f)


def save_projections(data: dict):
    """Save projections to JSON and markdown."""
    json_path = PROJECTIONS_FILE
    md_path = json_path.replace(".json", ".md")

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    with open(md_path, "w") as f:
        f.write(generate_markdown(data))


def get_epoch(data: dict, epoch_num: int) -> dict | None:
    """Get epoch data by number."""
    for e in data["epochs"]:
        if e["epoch"] == epoch_num:
            return e
    return None


def parse_epoch_num(text: str) -> int | None:
    """Extract epoch number from text like 'e19', 'epoch 25', 'E30'."""
    m = re.search(r'e(?:poch)?\s*(\d+)', text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def handle_when_bond(query: str, data: dict) -> str:
    """Handle 'when does vpsX next bond' queries."""
    current_epoch = data["metadata"]["anchor_epoch"]

    if "vps1" in query.lower() or "mapusisimito" in query.lower():
        key = "vps1_bonded"
        name = "VPS1"
    elif "vps2" in query.lower() or "df80f5d70af4" in query.lower():
        key = "vps2_bonded"
        name = "VPS2"
    else:
        # Either VPS
        results = []
        for e in data["epochs"]:
            if e["epoch"] <= current_epoch:
                continue
            if e["vps1_bonded"]:
                results.append(f"VPS1 bonds at E{e['epoch']} (bonds -> {e['vps1_bonds']+1})")
                break
        for e in data["epochs"]:
            if e["epoch"] <= current_epoch:
                continue
            if e["vps2_bonded"]:
                results.append(f"VPS2 bonds at E{e['epoch']} (bonds -> {e['vps2_bonds']+1})")
                break
        return "\n".join(results) if results else "No bonding events projected."

    for e in data["epochs"]:
        if e["epoch"] <= current_epoch:
            continue
        if e[key]:
            bonds_after = e["vps1_bonds"] + 1 if "vps1" in key else e["vps2_bonds"] + 1
            return f"{name} next bonds at E{e['epoch']} (will have {bonds_after} bonds effective E{e['epoch']+1})"

    return f"No bonding event projected for {name} in range."


def handle_s_at_epoch(query: str, data: dict) -> str:
    """Handle 'what is s at epoch X' queries."""
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."
    return f"E{epoch_num}: s = {e['s']:.4f} (total_bonds = {e['total_bonds']})"


def handle_reward_at_epoch(query: str, data: dict) -> str:
    """Handle reward queries at specific epochs."""
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."

    lines = [
        f"E{epoch_num} rewards (s = {e['s']:.4f}, total_bonds = {e['total_bonds']}):",
        f"  VPS1: {e['vps1_reward']:.8f} DOLI ({e['vps1_bonds']} bonds)",
        f"  VPS2: {e['vps2_reward']:.8f} DOLI ({e['vps2_bonds']} bonds)",
        f"  Combined: {e['combined_reward']:.8f} DOLI",
    ]
    return "\n".join(lines)


def handle_bonds_at_epoch(query: str, data: dict) -> str:
    """Handle 'how many bonds at epoch X' queries."""
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."

    total_ours = e["vps1_bonds"] + e["vps2_bonds"]
    return (f"E{epoch_num}: VPS1 = {e['vps1_bonds']} bonds, VPS2 = {e['vps2_bonds']} bonds, "
            f"combined = {total_ours} bonds (network = {e['total_bonds']})")


def handle_when_reach(query: str, data: dict) -> str:
    """Handle 'when do we reach X bonds each' queries."""
    m = re.search(r'(\d+)\s*bonds?\s*(each|total|combined)?', query, re.IGNORECASE)
    if not m:
        return "Could not parse target bond count."

    target = int(m.group(1))
    mode = (m.group(2) or "each").lower()

    for e in data["epochs"]:
        if mode == "each":
            if e["vps1_bonds"] >= target and e["vps2_bonds"] >= target:
                return (f"Both VPS reach {target} bonds each at E{e['epoch']} "
                        f"(VPS1={e['vps1_bonds']}, VPS2={e['vps2_bonds']})")
        elif mode in ("total", "combined"):
            if e["vps1_bonds"] + e["vps2_bonds"] >= target:
                return (f"Combined {target} bonds reached at E{e['epoch']} "
                        f"(VPS1={e['vps1_bonds']}, VPS2={e['vps2_bonds']})")

    return f"Target of {target} bonds ({mode}) not reached in projection range."


def handle_accuracy_check(query: str, data: dict) -> str:
    """Handle 'accuracy check eX actual_bonds=Y' queries."""
    epoch_num = parse_epoch_num(query)
    m = re.search(r'actual_bonds\s*=\s*(\d+)', query, re.IGNORECASE)
    if epoch_num is None or m is None:
        return "Usage: accuracy check eX actual_bonds=Y"

    actual = int(m.group(1))
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."

    projected = e["total_bonds"]
    accuracy = (1 - abs(projected - actual) / actual) * 100
    diff = projected - actual
    direction = "over" if diff > 0 else "under"

    lines = [
        f"E{epoch_num} accuracy check:",
        f"  Projected: {projected} bonds",
        f"  Actual:    {actual} bonds",
        f"  Diff:      {abs(diff)} bonds ({direction}-estimated)",
        f"  Accuracy:  {accuracy:.1f}%",
    ]

    if accuracy < 95:
        lines.append(f"\n  WARNING: Accuracy below 95%. Consider recalibrating:")
        lines.append(f'  python query.py "recalibrate e{epoch_num} total_bonds={actual}"')

    return "\n".join(lines)


def handle_recalibrate(query: str, data: dict) -> str:
    """
    Recalibrate the model with real epoch data.

    Usage: recalibrate eX total_bonds=Y [vps1_bonds=A] [vps1_spendable=B]
           [vps2_bonds=C] [vps2_spendable=D]
    """
    epoch_num = parse_epoch_num(query)
    m_bonds = re.search(r'total_bonds\s*=\s*(\d+)', query, re.IGNORECASE)

    if epoch_num is None or m_bonds is None:
        return "Usage: recalibrate eX total_bonds=Y [vps1_bonds=A] [vps1_spendable=B] [vps2_bonds=C] [vps2_spendable=D]"

    real_total_bonds = int(m_bonds.group(1))

    # Check accuracy of previous projection
    old_epoch = get_epoch(data, epoch_num)
    accuracy_entry = None
    if old_epoch:
        projected = old_epoch["total_bonds"]
        accuracy = (1 - abs(projected - real_total_bonds) / real_total_bonds) * 100
        accuracy_entry = {
            "epoch": epoch_num,
            "projected_bonds": projected,
            "real_bonds": real_total_bonds,
            "accuracy_pct": round(accuracy, 1),
        }

    # Parse optional VPS overrides
    vps1_bonds = _parse_kv(query, "vps1_bonds", int)
    vps1_spendable = _parse_kv(query, "vps1_spendable", float)
    vps2_bonds = _parse_kv(query, "vps2_bonds", int)
    vps2_spendable = _parse_kv(query, "vps2_spendable", float)

    # Get VPS state from old projection if not overridden
    if old_epoch:
        if vps1_bonds is None:
            vps1_bonds = old_epoch["vps1_bonds"]
        if vps1_spendable is None:
            vps1_spendable = old_epoch["vps1_spendable"]
        if vps2_bonds is None:
            vps2_bonds = old_epoch["vps2_bonds"]
        if vps2_spendable is None:
            vps2_spendable = old_epoch["vps2_spendable"]

    # Recalculate structural growth rate based on actual vs projected
    old_meta = data["metadata"]
    epochs_elapsed = epoch_num - old_meta["anchor_epoch"]
    if epochs_elapsed > 0:
        actual_growth = real_total_bonds - old_meta["anchor_total_bonds"]
        # Remove VPS bond contributions from growth estimate
        vps_bonds_added = ((vps1_bonds or 2) - 2) + ((vps2_bonds or 2) - 2)
        network_growth = actual_growth - vps_bonds_added

        # Estimate structural growth rate (adjust accumulate/burst)
        # Count how many accumulate vs burst epochs occurred
        accumulate_epochs = sum(1 for i in range(1, epochs_elapsed + 1) if i % 2 == 1)
        burst_epochs = sum(1 for i in range(1, epochs_elapsed + 1) if i % 2 == 0)
        mid_miner_epochs = sum(1 for i in range(1, epochs_elapsed + 1) if i % 2 == 0 and i > 0)
        mid_miner_growth = mid_miner_epochs * 7  # 7 mid miners

        structural_growth = network_growth - mid_miner_growth
        if accumulate_epochs + burst_epochs > 0:
            # Maintain 2:1 burst-to-accumulate ratio, scale both
            total_structural_epochs = accumulate_epochs + burst_epochs
            avg_structural = structural_growth / total_structural_epochs if total_structural_epochs > 0 else 35
            # burst is ~2x accumulate
            new_accumulate = int(round(avg_structural * 2 / 3))
            new_burst = int(round(avg_structural * 4 / 3))
        else:
            new_accumulate = 35
            new_burst = 70
    else:
        new_accumulate = 35
        new_burst = 70

    # Build new config
    accuracy_log = data.get("accuracy_log", [])
    if accuracy_entry:
        accuracy_log.append(accuracy_entry)

    config = SimConfig(
        anchor_epoch=epoch_num,
        target_epoch=max(60, epoch_num + 42),
        anchor_total_bonds=real_total_bonds,
        vps1_bonds=vps1_bonds or 2,
        vps1_spendable=vps1_spendable or 0.0,
        vps2_bonds=vps2_bonds or 2,
        vps2_spendable=vps2_spendable or 0.0,
        structural_accumulate=new_accumulate,
        structural_burst=new_burst,
        accuracy_log=accuracy_log,
    )

    # Regenerate
    new_data = simulate(config)
    new_data["accuracy_log"] = accuracy_log
    save_projections(new_data)

    lines = [
        f"Recalibrated from E{epoch_num} (total_bonds={real_total_bonds})",
        f"  Structural growth adjusted: accumulate={new_accumulate}, burst={new_burst}",
        f"  VPS1: {vps1_bonds} bonds, {vps1_spendable:.4f} spendable",
        f"  VPS2: {vps2_bonds} bonds, {vps2_spendable:.4f} spendable",
    ]

    if accuracy_entry:
        lines.append(f"  Previous model accuracy: {accuracy_entry['accuracy_pct']:.1f}%")

    lines.append(f"\nRegenerated projections E{epoch_num} to E{config.target_epoch}")
    return "\n".join(lines)


def handle_summary(data: dict) -> str:
    """Print a summary of current projections."""
    meta = data["metadata"]
    epochs = data["epochs"]
    first = epochs[0]
    last = epochs[-1]

    # Find all bond events
    vps1_events = [e["epoch"] for e in epochs if e["vps1_bonded"]]
    vps2_events = [e["epoch"] for e in epochs if e["vps2_bonded"]]

    # Total rewards
    total_combined = sum(e["combined_reward"] for e in epochs)

    lines = [
        f"Projection: E{meta['anchor_epoch']} → E{meta['target_epoch']} ({meta['model']} model)",
        f"Network: {first['total_bonds']} → {last['total_bonds']} bonds",
        f"Share value: {first['s']:.4f} → {last['s']:.4f}",
        f"",
        f"VPS1: {first['vps1_bonds']} → {last['vps1_bonds']} bonds | bond epochs: {vps1_events}",
        f"VPS2: {first['vps2_bonds']} → {last['vps2_bonds']} bonds | bond epochs: {vps2_events}",
        f"",
        f"Total combined reward over range: {total_combined:.4f} DOLI",
    ]
    return "\n".join(lines)


def _parse_kv(text: str, key: str, cast=str):
    """Parse key=value from text."""
    m = re.search(rf'{key}\s*=\s*([\d.]+)', text, re.IGNORECASE)
    return cast(m.group(1)) if m else None


def route_query(query: str) -> str:
    """Route a natural language query to the appropriate handler."""
    data = load_projections()
    q = query.lower().strip()

    if "recalibrate" in q or "recalib" in q:
        return handle_recalibrate(query, data)

    if "accuracy" in q and ("check" in q or "actual" in q):
        return handle_accuracy_check(query, data)

    if "when" in q and "reach" in q:
        return handle_when_reach(q, data)

    if "when" in q and "bond" in q:
        return handle_when_bond(q, data)

    if ("what is s" in q or "share" in q) and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_s_at_epoch(q, data)

    if "reward" in q and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_reward_at_epoch(q, data)

    if ("how many bonds" in q or "bond count" in q) and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_bonds_at_epoch(q, data)

    if "summary" in q or "overview" in q:
        return handle_summary(data)

    # Fallback: try to detect epoch number and show full epoch data
    epoch_num = parse_epoch_num(q)
    if epoch_num is not None:
        e = get_epoch(data, epoch_num)
        if e:
            return json.dumps(e, indent=2)
        return f"Epoch {epoch_num} not in projection range."

    return (
        "Could not understand query. Try:\n"
        '  "when does vps1 next bond"\n'
        '  "what is s at epoch 25"\n'
        '  "combined reward at epoch 30"\n'
        '  "how many bonds do we have at epoch 40"\n'
        '  "when do we reach 5 bonds each"\n'
        '  "accuracy check e19 actual_bonds=670"\n'
        '  "recalibrate e19 total_bonds=670"\n'
        '  "summary"'
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py \"<query>\"")
        print("\nExamples:")
        print('  python query.py "when does vps1 next bond"')
        print('  python query.py "what is s at epoch 25"')
        print('  python query.py "combined reward at epoch 30"')
        print('  python query.py "how many bonds do we have at epoch 40"')
        print('  python query.py "when do we reach 5 bonds each"')
        print('  python query.py "accuracy check e19 actual_bonds=670"')
        print('  python query.py "recalibrate e19 total_bonds=670"')
        print('  python query.py "summary"')
        sys.exit(1)

    result = route_query(" ".join(sys.argv[1:]))
    print(result)
```

## update.log
```
[2026-04-04 16:53:17] DOLI projection updater starting
[2026-04-04 16:53:17] Loaded existing projections anchored at E19
[2026-04-04 16:53:17] New epoch boundary: E20 (height=7260)
[2026-04-04 16:53:17] Epoch 20 detected — fetching real data
[2026-04-04 16:53:17] Real bonds: 671 — s = 0.5365 — producers: 20
[2026-04-04 16:53:27] Failed to reach VPS2 RPC: <urlopen error timed out>
[2026-04-04 16:53:27] VPS1: 2 bonds, 2.21567566 spendable
[2026-04-04 16:53:27] VPS2: 2 bonds, 2.43070901 spendable
[2026-04-04 16:53:27] Projected: 690 — accuracy: 97.2%
[2026-04-04 16:53:27] Recalibrated: accumulate=2 burst=4
[2026-04-04 16:53:27] Regenerated projections E20→E62
[2026-04-04 16:55:03] DOLI projection updater starting
[2026-04-04 16:55:03] Loaded existing projections anchored at E20
```

## projections.json
```
{
  "metadata": {
    "anchor_epoch": 20,
    "anchor_total_bonds": 671,
    "target_epoch": 62,
    "generated_at": "2026-04-04T16:56:51.749029+00:00",
    "model": "pessimistic"
  },
  "epochs": [
    {
      "epoch": 20,
      "total_bonds": 671,
      "s": 0.5365,
      "vps1_bonds": 2,
      "vps1_spendable": 3.288701,
      "vps1_reward": 1.07302534,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 2.46349286,
      "vps2_reward": 1.07302534,
      "vps2_bonded": false,
      "combined_reward": 2.14605067,
      "network_growth": 22
    },
    {
      "epoch": 21,
      "total_bonds": 693,
      "s": 0.5195,
      "vps1_bonds": 2,
      "vps1_spendable": 4.32766203,
      "vps1_reward": 1.03896104,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 3.50245389,
      "vps2_reward": 1.03896104,
      "vps2_bonded": false,
      "combined_reward": 2.07792208,
      "network_growth": 51
    },
    {
      "epoch": 22,
      "total_bonds": 744,
      "s": 0.4839,
      "vps1_bonds": 2,
      "vps1_spendable": 5.29540397,
      "vps1_reward": 0.96774194,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 4.47019583,
      "vps2_reward": 0.96774194,
      "vps2_bonded": false,
      "combined_reward": 1.93548387,
      "network_growth": 22
    },
    {
      "epoch": 23,
      "total_bonds": 766,
      "s": 0.47,
      "vps1_bonds": 2,
      "vps1_spendable": 6.23535175,
      "vps1_reward": 0.93994778,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 5.41014361,
      "vps2_reward": 0.93994778,
      "vps2_bonded": false,
      "combined_reward": 1.87989556,
      "network_growth": 51
    },
    {
      "epoch": 24,
      "total_bonds": 817,
      "s": 0.4406,
      "vps1_bonds": 2,
      "vps1_spendable": 7.1166247,
      "vps1_reward": 0.88127295,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 6.29141656,
      "vps2_reward": 0.88127295,
      "vps2_bonded": false,
      "combined_reward": 1.7625459,
      "network_growth": 22
    },
    {
      "epoch": 25,
      "total_bonds": 839,
      "s": 0.4291,
      "vps1_bonds": 2,
      "vps1_spendable": 7.97478918,
      "vps1_reward": 0.85816448,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 7.14958104,
      "vps2_reward": 0.85816448,
      "vps2_bonded": false,
      "combined_reward": 1.71632896,
      "network_growth": 51
    },
    {
      "epoch": 26,
      "total_bonds": 890,
      "s": 0.4045,
      "vps1_bonds": 2,
      "vps1_spendable": 8.78377795,
      "vps1_reward": 0.80898876,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 7.95856981,
      "vps2_reward": 0.80898876,
      "vps2_bonded": false,
      "combined_reward": 1.61797753,
      "network_growth": 22
    },
    {
      "epoch": 27,
      "total_bonds": 912,
      "s": 0.3947,
      "vps1_bonds": 2,
      "vps1_spendable": 9.57325163,
      "vps1_reward": 0.78947368,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 8.74804349,
      "vps2_reward": 0.78947368,
      "vps2_bonded": false,
      "combined_reward": 1.57894737,
      "network_growth": 51
    },
    {
      "epoch": 28,
      "total_bonds": 963,
      "s": 0.3738,
      "vps1_bonds": 2,
      "vps1_spendable": 0.32091518,
      "vps1_reward": 0.74766355,
      "vps1_bonded": true,
      "vps2_bonds": 2,
      "vps2_spendable": 9.49570704,
      "vps2_reward": 0.74766355,
      "vps2_bonded": false,
      "combined_reward": 1.4953271,
      "network_growth": 23
    },
    {
      "epoch": 29,
      "total_bonds": 986,
      "s": 0.3651,
      "vps1_bonds": 3,
      "vps1_spendable": 1.41624987,
      "vps1_reward": 1.09533469,
      "vps1_bonded": false,
      "vps2_bonds": 2,
      "vps2_spendable": 0.22593017,
      "vps2_reward": 0.73022312,
      "vps2_bonded": true,
      "combined_reward": 1.82555781,
      "network_growth": 52
    },
    {
      "epoch": 30,
      "total_bonds": 1038,
      "s": 0.3468,
      "vps1_bonds": 3,
      "vps1_spendable": 2.45671229,
      "vps1_reward": 1.04046243,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 1.26639259,
      "vps2_reward": 1.04046243,
      "vps2_bonded": false,
      "combined_reward": 2.08092486,
      "network_growth": 22
    },
    {
      "epoch": 31,
      "total_bonds": 1060,
      "s": 0.3396,
      "vps1_bonds": 3,
      "vps1_spendable": 3.47558022,
      "vps1_reward": 1.01886792,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 2.28526052,
      "vps2_reward": 1.01886792,
      "vps2_bonded": false,
      "combined_reward": 2.03773585,
      "network_growth": 51
    },
    {
      "epoch": 32,
      "total_bonds": 1111,
      "s": 0.324,
      "vps1_bonds": 3,
      "vps1_spendable": 4.44767743,
      "vps1_reward": 0.97209721,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 3.25735773,
      "vps2_reward": 0.97209721,
      "vps2_bonded": false,
      "combined_reward": 1.94419442,
      "network_growth": 22
    },
    {
      "epoch": 33,
      "total_bonds": 1133,
      "s": 0.3177,
      "vps1_bonds": 3,
      "vps1_spendable": 5.40089896,
      "vps1_reward": 0.95322154,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 4.21057926,
      "vps2_reward": 0.95322154,
      "vps2_bonded": false,
      "combined_reward": 1.90644307,
      "network_growth": 51
    },
    {
      "epoch": 34,
      "total_bonds": 1184,
      "s": 0.3041,
      "vps1_bonds": 3,
      "vps1_spendable": 6.31306113,
      "vps1_reward": 0.91216216,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 5.12274143,
      "vps2_reward": 0.91216216,
      "vps2_bonded": false,
      "combined_reward": 1.82432432,
      "network_growth": 22
    },
    {
      "epoch": 35,
      "total_bonds": 1206,
      "s": 0.2985,
      "vps1_bonds": 3,
      "vps1_spendable": 7.20858352,
      "vps1_reward": 0.89552239,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 6.01826381,
      "vps2_reward": 0.89552239,
      "vps2_bonded": false,
      "combined_reward": 1.79104478,
      "network_growth": 51
    },
    {
      "epoch": 36,
      "total_bonds": 1257,
      "s": 0.2864,
      "vps1_bonds": 3,
      "vps1_spendable": 8.06777206,
      "vps1_reward": 0.85918854,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 6.87745236,
      "vps2_reward": 0.85918854,
      "vps2_bonded": false,
      "combined_reward": 1.71837709,
      "network_growth": 22
    },
    {
      "epoch": 37,
      "total_bonds": 1279,
      "s": 0.2815,
      "vps1_bonds": 3,
      "vps1_spendable": 8.91218175,
      "vps1_reward": 0.8444097,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 7.72186205,
      "vps2_reward": 0.8444097,
      "vps2_bonded": false,
      "combined_reward": 1.68881939,
      "network_growth": 51
    },
    {
      "epoch": 38,
      "total_bonds": 1330,
      "s": 0.2707,
      "vps1_bonds": 3,
      "vps1_spendable": 9.72421183,
      "vps1_reward": 0.81203008,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 8.53389213,
      "vps2_reward": 0.81203008,
      "vps2_bonded": false,
      "combined_reward": 1.62406015,
      "network_growth": 22
    },
    {
      "epoch": 39,
      "total_bonds": 1352,
      "s": 0.2663,
      "vps1_bonds": 3,
      "vps1_spendable": 0.5230284,
      "vps1_reward": 0.79881657,
      "vps1_bonded": true,
      "vps2_bonds": 3,
      "vps2_spendable": 9.3327087,
      "vps2_reward": 0.79881657,
      "vps2_bonded": false,
      "combined_reward": 1.59763314,
      "network_growth": 52
    },
    {
      "epoch": 40,
      "total_bonds": 1404,
      "s": 0.2564,
      "vps1_bonds": 4,
      "vps1_spendable": 1.54866942,
      "vps1_reward": 1.02564103,
      "vps1_bonded": false,
      "vps2_bonds": 3,
      "vps2_spendable": 0.10193946,
      "vps2_reward": 0.76923077,
      "vps2_bonded": true,
      "combined_reward": 1.79487179,
      "network_growth": 23
    },
    {
      "epoch": 41,
      "total_bonds": 1427,
      "s": 0.2523,
      "vps1_bonds": 4,
      "vps1_spendable": 2.55777944,
      "vps1_reward": 1.00911002,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 1.11104949,
      "vps2_reward": 1.00911002,
      "vps2_bonded": false,
      "combined_reward": 2.01822004,
      "network_growth": 51
    },
    {
      "epoch": 42,
      "total_bonds": 1478,
      "s": 0.2436,
      "vps1_bonds": 4,
      "vps1_spendable": 3.53206902,
      "vps1_reward": 0.97428958,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 2.08533907,
      "vps2_reward": 0.97428958,
      "vps2_bonded": false,
      "combined_reward": 1.94857916,
      "network_growth": 22
    },
    {
      "epoch": 43,
      "total_bonds": 1500,
      "s": 0.24,
      "vps1_bonds": 4,
      "vps1_spendable": 4.49206902,
      "vps1_reward": 0.96,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 3.04533907,
      "vps2_reward": 0.96,
      "vps2_bonded": false,
      "combined_reward": 1.92,
      "network_growth": 51
    },
    {
      "epoch": 44,
      "total_bonds": 1551,
      "s": 0.2321,
      "vps1_bonds": 4,
      "vps1_spendable": 5.42050229,
      "vps1_reward": 0.92843327,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 3.97377234,
      "vps2_reward": 0.92843327,
      "vps2_bonded": false,
      "combined_reward": 1.85686654,
      "network_growth": 22
    },
    {
      "epoch": 45,
      "total_bonds": 1573,
      "s": 0.2289,
      "vps1_bonds": 4,
      "vps1_spendable": 6.33595048,
      "vps1_reward": 0.91544819,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 4.88922052,
      "vps2_reward": 0.91544819,
      "vps2_bonded": false,
      "combined_reward": 1.83089638,
      "network_growth": 51
    },
    {
      "epoch": 46,
      "total_bonds": 1624,
      "s": 0.2217,
      "vps1_bonds": 4,
      "vps1_spendable": 7.22264999,
      "vps1_reward": 0.88669951,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 5.77592003,
      "vps2_reward": 0.88669951,
      "vps2_bonded": false,
      "combined_reward": 1.77339901,
      "network_growth": 22
    },
    {
      "epoch": 47,
      "total_bonds": 1646,
      "s": 0.2187,
      "vps1_bonds": 4,
      "vps1_spendable": 8.09749811,
      "vps1_reward": 0.87484812,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 6.65076815,
      "vps2_reward": 0.87484812,
      "vps2_bonded": false,
      "combined_reward": 1.74969623,
      "network_growth": 51
    },
    {
      "epoch": 48,
      "total_bonds": 1697,
      "s": 0.2121,
      "vps1_bonds": 4,
      "vps1_spendable": 8.94605438,
      "vps1_reward": 0.84855628,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 7.49932442,
      "vps2_reward": 0.84855628,
      "vps2_bonded": false,
      "combined_reward": 1.69711255,
      "network_growth": 22
    },
    {
      "epoch": 49,
      "total_bonds": 1719,
      "s": 0.2094,
      "vps1_bonds": 4,
      "vps1_spendable": 9.78375072,
      "vps1_reward": 0.83769634,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 8.33702076,
      "vps2_reward": 0.83769634,
      "vps2_bonded": false,
      "combined_reward": 1.67539267,
      "network_growth": 51
    },
    {
      "epoch": 50,
      "total_bonds": 1770,
      "s": 0.2034,
      "vps1_bonds": 4,
      "vps1_spendable": 0.59731004,
      "vps1_reward": 0.81355932,
      "vps1_bonded": true,
      "vps2_bonds": 4,
      "vps2_spendable": 9.15058008,
      "vps2_reward": 0.81355932,
      "vps2_bonded": false,
      "combined_reward": 1.62711864,
      "network_growth": 23
    },
    {
      "epoch": 51,
      "total_bonds": 1793,
      "s": 0.2008,
      "vps1_bonds": 5,
      "vps1_spendable": 1.60121411,
      "vps1_reward": 1.00390407,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 9.95370334,
      "vps2_reward": 0.80312326,
      "vps2_bonded": false,
      "combined_reward": 1.80702733,
      "network_growth": 51
    },
    {
      "epoch": 52,
      "total_bonds": 1844,
      "s": 0.1952,
      "vps1_bonds": 5,
      "vps1_spendable": 2.57735294,
      "vps1_reward": 0.97613883,
      "vps1_bonded": false,
      "vps2_bonds": 4,
      "vps2_spendable": 0.7346144,
      "vps2_reward": 0.78091106,
      "vps2_bonded": true,
      "combined_reward": 1.75704989,
      "network_growth": 23
    },
    {
      "epoch": 53,
      "total_bonds": 1867,
      "s": 0.1928,
      "vps1_bonds": 5,
      "vps1_spendable": 3.54146649,
      "vps1_reward": 0.96411355,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 1.69872795,
      "vps2_reward": 0.96411355,
      "vps2_bonded": false,
      "combined_reward": 1.9282271,
      "network_growth": 51
    },
    {
      "epoch": 54,
      "total_bonds": 1918,
      "s": 0.1877,
      "vps1_bonds": 5,
      "vps1_spendable": 4.47994407,
      "vps1_reward": 0.93847758,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 2.63720553,
      "vps2_reward": 0.93847758,
      "vps2_bonded": false,
      "combined_reward": 1.87695516,
      "network_growth": 22
    },
    {
      "epoch": 55,
      "total_bonds": 1940,
      "s": 0.1856,
      "vps1_bonds": 5,
      "vps1_spendable": 5.40777912,
      "vps1_reward": 0.92783505,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 3.56504058,
      "vps2_reward": 0.92783505,
      "vps2_bonded": false,
      "combined_reward": 1.8556701,
      "network_growth": 51
    },
    {
      "epoch": 56,
      "total_bonds": 1991,
      "s": 0.1808,
      "vps1_bonds": 5,
      "vps1_spendable": 6.31184743,
      "vps1_reward": 0.90406831,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 4.46910889,
      "vps2_reward": 0.90406831,
      "vps2_bonded": false,
      "combined_reward": 1.80813661,
      "network_growth": 22
    },
    {
      "epoch": 57,
      "total_bonds": 2013,
      "s": 0.1788,
      "vps1_bonds": 5,
      "vps1_spendable": 7.20603521,
      "vps1_reward": 0.89418778,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 5.36329667,
      "vps2_reward": 0.89418778,
      "vps2_bonded": false,
      "combined_reward": 1.78837556,
      "network_growth": 51
    },
    {
      "epoch": 58,
      "total_bonds": 2064,
      "s": 0.1744,
      "vps1_bonds": 5,
      "vps1_spendable": 8.07812823,
      "vps1_reward": 0.87209302,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 6.23538969,
      "vps2_reward": 0.87209302,
      "vps2_bonded": false,
      "combined_reward": 1.74418605,
      "network_growth": 22
    },
    {
      "epoch": 59,
      "total_bonds": 2086,
      "s": 0.1726,
      "vps1_bonds": 5,
      "vps1_spendable": 8.94102373,
      "vps1_reward": 0.86289549,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 7.09828519,
      "vps2_reward": 0.86289549,
      "vps2_bonded": false,
      "combined_reward": 1.72579099,
      "network_growth": 51
    },
    {
      "epoch": 60,
      "total_bonds": 2137,
      "s": 0.1685,
      "vps1_bonds": 5,
      "vps1_spendable": 9.78332602,
      "vps1_reward": 0.84230229,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 7.94058748,
      "vps2_reward": 0.84230229,
      "vps2_bonded": false,
      "combined_reward": 1.68460459,
      "network_growth": 22
    },
    {
      "epoch": 61,
      "total_bonds": 2159,
      "s": 0.1667,
      "vps1_bonds": 5,
      "vps1_spendable": 0.61704533,
      "vps1_reward": 0.83371931,
      "vps1_bonded": true,
      "vps2_bonds": 5,
      "vps2_spendable": 8.7743068,
      "vps2_reward": 0.83371931,
      "vps2_bonded": false,
      "combined_reward": 1.66743863,
      "network_growth": 52
    },
    {
      "epoch": 62,
      "total_bonds": 2211,
      "s": 0.1628,
      "vps1_bonds": 6,
      "vps1_spendable": 1.59397885,
      "vps1_reward": 0.97693351,
      "vps1_bonded": false,
      "vps2_bonds": 5,
      "vps2_spendable": 9.58841806,
      "vps2_reward": 0.81411126,
      "vps2_bonded": false,
      "combined_reward": 1.79104478,
      "network_growth": 22
    }
  ],
  "accuracy_log": [
    {
      "epoch": 19,
      "projected_bonds": 670,
      "real_bonds": 668,
      "accuracy_pct": 99.7
    },
    {
      "epoch": 20,
      "projected_bonds": 690,
      "real_bonds": 671,
      "accuracy_pct": 97.2
    }
  ]
}```
