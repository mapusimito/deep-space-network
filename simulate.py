#!/usr/bin/env python3
"""
DOLI Epoch Simulation Engine — VPS1-only, Balance-Based Projection

Projects bond timing by tracking VPS1 spendable balance forward using
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
    dilution_rate: float = 0.03  # flat fallback if accumulate/burst not available
    model: str = "dilution"

    # Accumulate/burst dilution — derived from classify_epoch_growth()
    accumulate_dilution: float = 0.0
    burst_dilution: float = 0.0
    anchor_phase: str = ""  # "accumulate" or "burst"

    vps1_bonds: int = 3
    vps1_spendable: float = 0.76

    genesis: int = 1

    accuracy_log: list = field(default_factory=list)

    @property
    def has_dual_dilution(self) -> bool:
        return self.accumulate_dilution > 0 and self.burst_dilution > 0 and self.anchor_phase != ""


def classify_epoch_growth(accuracy_log: list, min_accuracy: float = 90.0) -> dict:
    """Analyze real bond deltas to classify epochs as accumulate or burst."""
    real_entries = [
        e for e in accuracy_log
        if "real_bonds" in e and e.get("accuracy_pct", 0) >= min_accuracy
    ]
    real_entries.sort(key=lambda e: e["epoch"])

    if len(real_entries) < 3:
        return {"epochs": [], "accumulate_weight": 35, "burst_weight": 70, "pattern": ""}

    deltas = []
    for i in range(1, len(real_entries)):
        prev, curr = real_entries[i - 1], real_entries[i]
        gap = curr["epoch"] - prev["epoch"]
        if gap != 1:
            continue
        delta = curr["real_bonds"] - prev["real_bonds"]
        if delta <= 0:
            continue
        s_prev = BLOCKS_PER_EPOCH / prev["real_bonds"]
        s_curr = BLOCKS_PER_EPOCH / curr["real_bonds"]
        dilution = 1 - (s_curr / s_prev)
        deltas.append({
            "epoch": curr["epoch"],
            "delta": delta,
            "bonds": curr["real_bonds"],
            "s": round(s_curr, 8),
            "dilution": round(dilution, 6),
        })

    if len(deltas) < 3:
        return {"epochs": deltas, "accumulate_weight": 35, "burst_weight": 70, "pattern": ""}

    vals = sorted(d["delta"] for d in deltas)
    q1 = vals[len(vals) // 4]
    q3 = vals[3 * len(vals) // 4]
    iqr = q3 - q1
    fence_lo = q1 - 1.5 * iqr
    fence_hi = q3 + 1.5 * iqr
    clean_vals = [v for v in vals if fence_lo <= v <= fence_hi]

    if len(clean_vals) < 3:
        clean_vals = vals

    c_lo = clean_vals[len(clean_vals) // 3]
    c_hi = clean_vals[2 * len(clean_vals) // 3]

    for _ in range(20):
        lo_group = [v for v in clean_vals if abs(v - c_lo) <= abs(v - c_hi)]
        hi_group = [v for v in clean_vals if abs(v - c_hi) < abs(v - c_lo)]
        if not lo_group or not hi_group:
            break
        new_lo = sum(lo_group) / len(lo_group)
        new_hi = sum(hi_group) / len(hi_group)
        if abs(new_lo - c_lo) < 0.1 and abs(new_hi - c_hi) < 0.1:
            c_lo, c_hi = new_lo, new_hi
            break
        c_lo, c_hi = new_lo, new_hi

    threshold = (c_lo + c_hi) / 2

    accum_vals, burst_vals = [], []
    for d in deltas:
        if d["delta"] <= threshold:
            d["type"] = "accumulate"
            accum_vals.append(d["delta"])
        else:
            d["type"] = "burst"
            burst_vals.append(d["delta"])

    accum_weight = sum(accum_vals) / len(accum_vals) if accum_vals else 35
    burst_weight = sum(burst_vals) / len(burst_vals) if burst_vals else 70
    pattern = "".join("A" if d["type"] == "accumulate" else "B" for d in deltas)

    return {
        "epochs": deltas,
        "accumulate_weight": round(accum_weight, 1),
        "burst_weight": round(burst_weight, 1),
        "threshold": round(threshold, 1),
        "pattern": pattern,
    }


def compute_dilution_rate(accuracy_log: list) -> float:
    """Derive per-epoch dilution rate from real bond data (geometric mean)."""
    real_entries = [e for e in accuracy_log if "real_bonds" in e]
    if len(real_entries) < 2:
        return 0.03

    points = sorted(real_entries, key=lambda e: e["epoch"])
    first = points[0]
    last = points[-1]

    epoch_span = last["epoch"] - first["epoch"]
    if epoch_span <= 0 or first["real_bonds"] <= 0 or last["real_bonds"] <= 0:
        return 0.03

    s_first = BLOCKS_PER_EPOCH / first["real_bonds"]
    s_last = BLOCKS_PER_EPOCH / last["real_bonds"]

    if s_last >= s_first:
        return 0.01

    per_epoch_ratio = (s_last / s_first) ** (1 / epoch_span)
    dilution = 1 - per_epoch_ratio

    return max(0.005, min(dilution, 0.15))


def simulate(config: Optional[SimConfig] = None) -> dict:
    if config is None:
        config = SimConfig()

    vps1 = ProducerState("VPS1", config.vps1_bonds, config.vps1_spendable)

    s = config.anchor_s if config.anchor_s > 0 else BLOCKS_PER_EPOCH / config.anchor_total_bonds
    total_bonds = config.anchor_total_bonds

    epochs = []
    vps1_pending_bond = False

    for epoch in range(config.anchor_epoch, config.target_epoch + 1):
        offset = epoch - config.anchor_epoch

        if vps1_pending_bond:
            vps1.bonds += 1
            vps1_pending_bond = False

        if offset > 0:
            if config.has_dual_dilution:
                if config.anchor_phase == "accumulate":
                    rate = config.burst_dilution if offset % 2 == 1 else config.accumulate_dilution
                else:
                    rate = config.accumulate_dilution if offset % 2 == 1 else config.burst_dilution
            else:
                rate = config.dilution_rate
            s *= (1 - rate)
            total_bonds = int(round(BLOCKS_PER_EPOCH / s))

        # Don't earn on anchor epoch — spendable already reflects current state
        if offset == 0:
            vps1_reward = 0.0
        else:
            vps1_reward = vps1.earn(s)

        vps1.bonded_this_epoch = False
        if vps1.spendable >= BOND_THRESHOLD:
            vps1.spendable -= BOND_COST
            vps1.bonded_this_epoch = True

        if vps1.bonded_this_epoch:
            vps1_pending_bond = True

        need_to_bond = max(0.0, BOND_THRESHOLD - vps1.spendable)

        epoch_data = {
            "epoch": epoch,
            "total_bonds": total_bonds,
            "s": round(s, 8),
            "vps1": {
                "bonds": vps1.bonds,
                "spendable": round(vps1.spendable, 8),
                "reward": round(vps1_reward, 8),
                "bonded_this_epoch": vps1.bonded_this_epoch,
                "need_to_bond": round(need_to_bond, 8),
            },
            "real": (offset == 0),
        }
        epochs.append(epoch_data)

    metadata = {
        "genesis": config.genesis,
        "anchor_epoch": config.anchor_epoch,
        "anchor_total_bonds": config.anchor_total_bonds,
        "target_epoch": config.target_epoch,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "dilution_rate": round(config.dilution_rate, 6),
    }
    if config.has_dual_dilution:
        metadata["accumulate_dilution"] = round(config.accumulate_dilution, 6)
        metadata["burst_dilution"] = round(config.burst_dilution, 6)
        metadata["anchor_phase"] = config.anchor_phase

    return {
        "metadata": metadata,
        "accuracy_log": config.accuracy_log,
        "epochs": epochs,
    }


def generate_markdown(data: dict) -> str:
    meta = data["metadata"]

    lines = [
        "# DOLI Epoch Projections — VPS1",
        "",
        f"**Anchor:** E{meta['anchor_epoch']} ({meta['anchor_total_bonds']} bonds)",
        f"**Generated:** {meta['generated_at']}",
        f"**Model:** {meta['model']}",
        f"**Dilution rate:** {meta.get('dilution_rate', '?')} per epoch",
        "",
        "| Epoch | Net bonds | s | VPS1 bonds | Spendable | Reward | Need to bond | Event | Real |",
        "|------:|----------:|------:|-----------:|----------:|-------:|-------------:|:------|:----:|",
    ]

    for e in data["epochs"]:
        v1 = e["vps1"]
        event_str = "BOND" if v1["bonded_this_epoch"] else "-"
        real_str = "Y" if e.get("real") else "-"
        need = v1.get("need_to_bond", max(0.0, BOND_THRESHOLD - v1["spendable"]))

        lines.append(
            f"| {e['epoch']:>5} "
            f"| {e['total_bonds']:>9} "
            f"| {e['s']:>5.4f} "
            f"| {v1['bonds']:>10} "
            f"| {v1['spendable']:>9.4f} "
            f"| {v1['reward']:>6.4f} "
            f"| {need:>12.4f} "
            f"| {event_str} "
            f"| {real_str} |"
        )

    if data.get("accuracy_log"):
        lines.extend([
            "",
            "## Accuracy Log",
            "",
            "| Epoch | Projected bonds | Real bonds | Accuracy % | VPS1 bonds |",
            "|------:|----------------:|-----------:|-----------:|-----------:|",
        ])
        for entry in data["accuracy_log"]:
            v1b = entry.get("vps1_bonds", "-")
            lines.append(
                f"| {entry['epoch']:>5} "
                f"| {entry['projected_bonds']:>15} "
                f"| {entry['real_bonds']:>10} "
                f"| {entry['accuracy_pct']:>10.1f} "
                f"| {str(v1b):>10} |"
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
