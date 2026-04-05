#!/usr/bin/env python3
"""
DOLI Epoch Simulation Engine — Balance-Based Projection

Projects bond timing by tracking spendable balances forward using
current share value and observed dilution rate.

Core formula: s = 360 / total_bonds
Reward per producer per epoch = producer_bonds * s
Bond when spendable >= 10.01
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


BLOCKS_PER_EPOCH = 360
BOND_COST = 10.0
BOND_THRESHOLD = 10.01


@dataclass
class ProducerState:
    name: str
    bonds: int
    spendable: float = 0.0
    bonded_this_epoch: bool = False

    def earn(self, s: float):
        reward = self.bonds * s
        self.spendable += reward
        return reward

    def try_bond(self) -> bool:
        """Check if this producer can bond using only its own spendable."""
        self.bonded_this_epoch = False
        if self.spendable >= BOND_THRESHOLD:
            self.spendable -= BOND_COST
            self.bonded_this_epoch = True
            return True
        return False


@dataclass
class SimConfig:
    anchor_epoch: int = 24
    target_epoch: int = 66
    anchor_total_bonds: int = 856
    anchor_s: float = 0.0  # computed from anchor_total_bonds if 0
    dilution_rate: float = 0.03  # s decreases by this fraction per epoch
    model: str = "dilution"

    vps1_bonds: int = 3
    vps1_spendable: float = 0.76
    vps2_bonds: int = 2
    vps2_spendable: float = 0.90

    # Bond priority: which VPS to bond first when both have equal bonds
    bond_priority: str = "vps1"

    accuracy_log: list = field(default_factory=list)


def compute_dilution_rate(accuracy_log: list) -> float:
    """Derive per-epoch dilution rate from real bond data.
    Uses geometric mean across the full span for stability.
    Returns fraction by which s decreases each epoch."""
    real_entries = [e for e in accuracy_log if "real_bonds" in e]
    if len(real_entries) < 2:
        return 0.03  # default

    points = sorted(real_entries, key=lambda e: e["epoch"])
    first = points[0]
    last = points[-1]

    epoch_span = last["epoch"] - first["epoch"]
    if epoch_span <= 0 or first["real_bonds"] <= 0 or last["real_bonds"] <= 0:
        return 0.03

    s_first = BLOCKS_PER_EPOCH / first["real_bonds"]
    s_last = BLOCKS_PER_EPOCH / last["real_bonds"]

    if s_last >= s_first:
        return 0.01  # no dilution observed, use minimal default

    # Geometric mean: (s_last/s_first)^(1/span) gives the per-epoch multiplier
    per_epoch_ratio = (s_last / s_first) ** (1 / epoch_span)
    dilution = 1 - per_epoch_ratio

    return max(0.005, min(dilution, 0.15))  # clamp to reasonable range


def simulate(config: Optional[SimConfig] = None) -> dict:
    if config is None:
        config = SimConfig()

    vps1 = ProducerState("VPS1", config.vps1_bonds, config.vps1_spendable)
    vps2 = ProducerState("VPS2", config.vps2_bonds, config.vps2_spendable)

    s = config.anchor_s if config.anchor_s > 0 else BLOCKS_PER_EPOCH / config.anchor_total_bonds
    total_bonds = config.anchor_total_bonds

    epochs = []
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

        # Apply dilution after anchor epoch
        if offset > 0:
            s *= (1 - config.dilution_rate)
            total_bonds = int(round(BLOCKS_PER_EPOCH / s))

        # Don't earn on anchor epoch — spendable already reflects current state
        if offset == 0:
            vps1_reward = 0.0
            vps2_reward = 0.0
        else:
            vps1_reward = vps1.earn(s)
            vps2_reward = vps2.earn(s)

        # Combined pool bonding: bond the VPS with fewer bonds first
        # (if equal, use priority setting). Transfer between wallets as needed.
        combined = vps1.spendable + vps2.spendable
        vps1.bonded_this_epoch = False
        vps2.bonded_this_epoch = False

        if combined >= BOND_THRESHOLD:
            # Decide who bonds: fewer bonds first, priority breaks ties
            if vps1.bonds < vps2.bonds:
                first, second = vps1, vps2
            elif vps2.bonds < vps1.bonds:
                first, second = vps2, vps1
            elif config.bond_priority == "vps1":
                first, second = vps1, vps2
            else:
                first, second = vps2, vps1

            # Bond first using combined pool
            deficit = BOND_COST - first.spendable
            if deficit > 0:
                transfer = min(deficit, second.spendable)
                second.spendable -= transfer
                first.spendable += transfer
            if first.spendable >= BOND_COST:
                first.spendable -= BOND_COST
                first.bonded_this_epoch = True

            # Check if second can also bond with remaining
            if first.spendable + second.spendable >= BOND_THRESHOLD:
                deficit2 = BOND_COST - second.spendable
                if deficit2 > 0:
                    transfer2 = min(deficit2, first.spendable)
                    first.spendable -= transfer2
                    second.spendable += transfer2
                if second.spendable >= BOND_COST:
                    second.spendable -= BOND_COST
                    second.bonded_this_epoch = True

        if vps1.bonded_this_epoch:
            vps1_pending_bond = True
        if vps2.bonded_this_epoch:
            vps2_pending_bond = True

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
            "combined_spendable": round(vps1.spendable + vps2.spendable, 8),
            "real": (offset == 0),
        }
        epochs.append(epoch_data)

    output = {
        "metadata": {
            "anchor_epoch": config.anchor_epoch,
            "anchor_total_bonds": config.anchor_total_bonds,
            "target_epoch": config.target_epoch,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": config.model,
            "dilution_rate": round(config.dilution_rate, 6),
        },
        "accuracy_log": config.accuracy_log,
        "epochs": epochs,
    }

    return output


def generate_markdown(data: dict) -> str:
    meta = data["metadata"]

    lines = [
        "# DOLI Epoch Projections — Dilution Model",
        "",
        f"**Anchor:** E{meta['anchor_epoch']} ({meta['anchor_total_bonds']} bonds)",
        f"**Generated:** {meta['generated_at']}",
        f"**Model:** {meta['model']}",
        f"**Dilution rate:** {meta.get('dilution_rate', '?')} per epoch",
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
