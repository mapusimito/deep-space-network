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
