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
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


# --- Constants ---
BLOCKS_PER_EPOCH = 360
BOND_COST = 10.0
BOND_THRESHOLD = 10.01  # autobond triggers at this spendable balance


@dataclass
class ProducerState:
    """Tracks a single producer's bonds and spendable balance."""
    name: str
    bonds: int
    spendable: float = 0.0
    bonded_this_epoch: bool = False

    def earn(self, s: float):
        reward = self.bonds * s
        self.spendable += reward
        return reward

    def try_bond(self) -> bool:
        self.bonded_this_epoch = False
        if self.spendable >= BOND_THRESHOLD:
            self.spendable -= BOND_COST
            self.bonded_this_epoch = True
            return True
        return False


@dataclass
class SimConfig:
    """Configuration for the simulation."""
    anchor_epoch: int = 19
    target_epoch: int = 61
    anchor_total_bonds: int = 668
    model: str = "pessimistic"

    vps1_bonds: int = 2
    vps1_spendable: float = 1.13
    vps2_bonds: int = 2
    vps2_spendable: float = 0.31

    structural_accumulate: int = 35
    structural_burst: int = 70

    mid_miner_count: int = 7
    mid_miner_bonds_per_2_epochs: int = 1

    accuracy_log: list = field(default_factory=list)


def compute_network_growth(epoch_offset: int, config: SimConfig) -> int:
    """Compute bonds added by non-VPS producers this epoch."""
    if epoch_offset % 2 == 1:
        structural = config.structural_accumulate
    else:
        structural = config.structural_burst

    # Mid miners bond independently, distributed evenly across epochs
    if epoch_offset > 0:
        total_mid = config.mid_miner_count * config.mid_miner_bonds_per_2_epochs
        if epoch_offset % 2 == 1:
            mid_miners = (total_mid + 1) // 2  # ceil
        else:
            mid_miners = total_mid // 2
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

    vps1 = ProducerState("VPS1", config.vps1_bonds, config.vps1_spendable)
    vps2 = ProducerState("VPS2", config.vps2_bonds, config.vps2_spendable)

    epochs = []
    total_bonds = config.anchor_total_bonds

    vps1_pending_bond = False
    vps2_pending_bond = False

    for epoch in range(config.anchor_epoch, config.target_epoch + 1):
        offset = epoch - config.anchor_epoch

        if vps1_pending_bond:
            vps1.bonds += 1
            vps1_pending_bond = False
        if vps2_pending_bond:
            vps2.bonds += 1
            vps2_pending_bond = False

        s = BLOCKS_PER_EPOCH / total_bonds

        vps1_reward = vps1.earn(s)
        vps2_reward = vps2.earn(s)

        if vps1.try_bond():
            vps1_pending_bond = True
        if vps2.try_bond():
            vps2_pending_bond = True

        if offset >= 0:
            growth = compute_network_growth(offset + 1, config)
        else:
            growth = 0

        vps_growth = (1 if vps1.bonded_this_epoch else 0) + (1 if vps2.bonded_this_epoch else 0)

        epoch_data = {
            "epoch": epoch,
            "total_bonds": total_bonds,
            "s": round(s, 8),
            "vps1": {
                "bonds": vps1.bonds,
                "spendable": round(vps1.spendable, 8),
                "reward": round(vps1_reward, 8),
                "bonded_this_epoch": vps1.bonded_this_epoch,
            },
            "vps2": {
                "bonds": vps2.bonds,
                "spendable": round(vps2.spendable, 8),
                "reward": round(vps2_reward, 8),
                "bonded_this_epoch": vps2.bonded_this_epoch,
            },
            "combined_reward": round(vps1_reward + vps2_reward, 8),
            "network_growth": growth + vps_growth,
            "real": (offset == 0),  # only anchor epoch is real data
        }
        epochs.append(epoch_data)

        total_bonds += growth + vps_growth

    output = {
        "metadata": {
            "anchor_epoch": config.anchor_epoch,
            "anchor_total_bonds": config.anchor_total_bonds,
            "target_epoch": config.target_epoch,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": config.model,
            "structural_growth": {
                "accumulate_epoch": config.structural_accumulate,
                "burst_epoch": config.structural_burst,
                "last_calibrated": datetime.now(timezone.utc).isoformat(),
            },
        },
        "accuracy_log": config.accuracy_log,
        "epochs": epochs,
    }

    return output


def generate_markdown(data: dict) -> str:
    """Generate human-readable markdown table from simulation data."""
    meta = data["metadata"]
    sg = meta.get("structural_growth", {})

    lines = [
        "# DOLI Epoch Projections — Pessimistic Model",
        "",
        f"**Anchor:** E{meta['anchor_epoch']} ({meta['anchor_total_bonds']} bonds)",
        f"**Generated:** {meta['generated_at']}",
        f"**Model:** {meta['model']}",
        f"**Structural growth:** accumulate={sg.get('accumulate_epoch', '?')}, burst={sg.get('burst_epoch', '?')}",
        "",
        "| Epoch | Total bonds | s | VPS1 bonds | VPS1 spendable | VPS2 bonds | VPS2 spendable | Combined reward | Bond events | Real |",
        "|------:|------------:|------:|-----------:|---------------:|-----------:|---------------:|----------------:|:------------|:----:|",
    ]

    for e in data["epochs"]:
        v1 = e["vps1"]
        v2 = e["vps2"]
        events = []
        if v1["bonded_this_epoch"]:
            events.append("VPS1 bonds")
        if v2["bonded_this_epoch"]:
            events.append("VPS2 bonds")
        event_str = ", ".join(events) if events else "-"
        real_str = "Y" if e.get("real") else "-"

        lines.append(
            f"| {e['epoch']:>5} "
            f"| {e['total_bonds']:>11} "
            f"| {e['s']:>5.4f} "
            f"| {v1['bonds']:>10} "
            f"| {v1['spendable']:>14.4f} "
            f"| {v2['bonds']:>10} "
            f"| {v2['spendable']:>14.4f} "
            f"| {e['combined_reward']:>15.4f} "
            f"| {event_str} "
            f"| {real_str} |"
        )

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
    with open(os.path.join(output_dir, "projections.json"), "w") as f:
        json.dump(data, f, indent=2)
    with open(os.path.join(output_dir, "projections.md"), "w") as f:
        f.write(generate_markdown(data))
    return data


if __name__ == "__main__":
    data = save_projections()
    print(f"Generated projections for E{data['metadata']['anchor_epoch']} "
          f"to E{data['metadata']['target_epoch']}")
