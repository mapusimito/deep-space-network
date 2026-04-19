#!/usr/bin/env python3
"""
DOLI Projection Query Interface — VPS1

Natural language CLI for querying epoch projections and recalibrating
the simulation model with real data.

Usage:
    python query.py "when does vps1 next bond"
    python query.py "what is s at epoch 25"
    python query.py "reward at epoch 30"
    python query.py "how many bonds at epoch 40"
    python query.py "summary"
    python query.py "recalibrate e80 total_bonds=2757 vps1_bonds=12 vps1_spendable=6.48"
"""

import json
import os
import re
import sys
from simulate import simulate, generate_markdown, SimConfig

PROJECTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projections.json")


def load_projections() -> dict:
    with open(PROJECTIONS_FILE) as f:
        return json.load(f)


def save_projections(data: dict):
    json_path = PROJECTIONS_FILE
    md_path = json_path.replace(".json", ".md")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    with open(md_path, "w") as f:
        f.write(generate_markdown(data))


def get_epoch(data: dict, epoch_num: int) -> dict | None:
    for e in data["epochs"]:
        if e["epoch"] == epoch_num:
            return e
    return None


def parse_epoch_num(text: str) -> int | None:
    m = re.search(r'e(?:poch)?\s*(\d+)', text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def handle_when_bond(data: dict) -> str:
    current_epoch = data["metadata"]["anchor_epoch"]
    for e in data["epochs"]:
        if e["epoch"] <= current_epoch:
            continue
        if e["vps1"]["bonded_this_epoch"]:
            bonds_after = e["vps1"]["bonds"] + 1
            spendable_now = e["vps1"]["spendable"]
            return (f"VPS1 next bonds at E{e['epoch']} "
                    f"(will have {bonds_after} bonds effective E{e['epoch']+1}; "
                    f"spendable after bond: {spendable_now:.8f})")
    return "No bonding event projected in range."


def handle_s_at_epoch(query: str, data: dict) -> str:
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."
    real_tag = " [REAL]" if e.get("real") else ""
    return f"E{epoch_num}: s = {e['s']:.4f} (total_bonds = {e['total_bonds']}){real_tag}"


def handle_reward_at_epoch(query: str, data: dict) -> str:
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."
    v1 = e["vps1"]
    real_tag = " [REAL]" if e.get("real") else ""
    return (
        f"E{epoch_num} (s = {e['s']:.4f}, net_bonds = {e['total_bonds']}){real_tag}:\n"
        f"  VPS1: {v1['reward']:.8f} DOLI ({v1['bonds']} bonds)\n"
        f"  Spendable after: {v1['spendable']:.8f} DOLI\n"
        f"  Still needs to bond: {v1.get('need_to_bond', 0):.8f} DOLI"
    )


def handle_bonds_at_epoch(query: str, data: dict) -> str:
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."
    v1 = e["vps1"]
    return (f"E{epoch_num}: VPS1 = {v1['bonds']} bonds, "
            f"spendable = {v1['spendable']:.8f}, "
            f"network = {e['total_bonds']} bonds")


def handle_accuracy_check(query: str, data: dict) -> str:
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
    epoch_num = parse_epoch_num(query)
    m_bonds = re.search(r'total_bonds\s*=\s*(\d+)', query, re.IGNORECASE)
    if epoch_num is None or m_bonds is None:
        return "Usage: recalibrate eX total_bonds=Y [vps1_bonds=A] [vps1_spendable=B]"

    real_total_bonds = int(m_bonds.group(1))
    old_epoch = get_epoch(data, epoch_num)

    accuracy_log = data.get("accuracy_log", [])
    if old_epoch:
        projected = old_epoch["total_bonds"]
        accuracy = (1 - abs(projected - real_total_bonds) / real_total_bonds) * 100
        accuracy_log.append({
            "epoch": epoch_num,
            "projected_bonds": projected,
            "real_bonds": real_total_bonds,
            "accuracy_pct": round(accuracy, 1),
        })

    vps1_bonds = _parse_kv(query, "vps1_bonds", int)
    vps1_spendable = _parse_kv(query, "vps1_spendable", float)

    if old_epoch:
        v1 = old_epoch["vps1"]
        if vps1_bonds is None: vps1_bonds = v1["bonds"]
        if vps1_spendable is None: vps1_spendable = v1["spendable"]

    from simulate import compute_dilution_rate, classify_epoch_growth, BLOCKS_PER_EPOCH
    dilution_rate = compute_dilution_rate(accuracy_log)
    growth = classify_epoch_growth(accuracy_log)
    accum_dilution = 0.0
    burst_dilution = 0.0
    anchor_phase = ""
    if len(growth["epochs"]) >= 4:
        accum_epochs = [e for e in growth["epochs"] if e["type"] == "accumulate"]
        burst_epochs = [e for e in growth["epochs"] if e["type"] == "burst"]
        if accum_epochs and burst_epochs:
            accum_dilution = sum(e["dilution"] for e in accum_epochs) / len(accum_epochs)
            burst_dilution = sum(e["dilution"] for e in burst_epochs) / len(burst_epochs)
            anchor_phase = growth["epochs"][-1]["type"]

    real_s = BLOCKS_PER_EPOCH / real_total_bonds

    config = SimConfig(
        anchor_epoch=epoch_num,
        target_epoch=max(60, epoch_num + 42),
        anchor_total_bonds=real_total_bonds,
        anchor_s=real_s,
        dilution_rate=dilution_rate,
        accumulate_dilution=accum_dilution,
        burst_dilution=burst_dilution,
        anchor_phase=anchor_phase,
        vps1_bonds=vps1_bonds or 2,
        vps1_spendable=vps1_spendable or 0.0,
        accuracy_log=accuracy_log,
    )

    new_data = simulate(config)
    new_data["accuracy_log"] = accuracy_log
    save_projections(new_data)

    lines = [
        f"Recalibrated from E{epoch_num} (total_bonds={real_total_bonds})",
        f"  VPS1: {vps1_bonds} bonds, {(vps1_spendable or 0):.4f} spendable",
        f"  Dilution rate: {dilution_rate:.4f}/epoch",
    ]
    if len(accuracy_log) > 0:
        lines.append(f"  Latest accuracy: {accuracy_log[-1]['accuracy_pct']:.1f}%")
    lines.append(f"\nRegenerated projections E{epoch_num} to E{config.target_epoch}")
    return "\n".join(lines)


def handle_summary(data: dict) -> str:
    meta = data["metadata"]
    epochs = data["epochs"]
    first, last = epochs[0], epochs[-1]

    bond_epochs = [e["epoch"] for e in epochs if e["vps1"]["bonded_this_epoch"]]
    real_count = sum(1 for e in epochs if e.get("real"))
    total_reward = sum(e["vps1"]["reward"] for e in epochs)

    # Find next bond epoch
    anchor = meta["anchor_epoch"]
    next_bond = next((e for e in epochs if e["epoch"] > anchor and e["vps1"]["bonded_this_epoch"]), None)
    next_bond_str = f"E{next_bond['epoch']}" if next_bond else "not in range"

    # Current spendable (anchor epoch)
    anchor_e = epochs[0]
    spendable_now = anchor_e["vps1"]["spendable"]
    need_now = anchor_e["vps1"].get("need_to_bond", max(0.0, 10.01 - spendable_now))

    lines = [
        f"Projection: E{meta['anchor_epoch']} -> E{meta['target_epoch']} ({meta['model']} model)",
        f"Network: {first['total_bonds']} -> {last['total_bonds']} bonds",
        f"Share value: {first['s']:.4f} -> {last['s']:.4f}",
        f"Real data points: {real_count}",
        f"",
        f"VPS1: {first['vps1']['bonds']} bonds now -> {last['vps1']['bonds']} bonds at E{meta['target_epoch']}",
        f"VPS1 spendable now: {spendable_now:.8f} DOLI (need {need_now:.8f} more to bond)",
        f"Next bond: {next_bond_str}",
        f"All bond epochs: {bond_epochs}",
        f"",
        f"Total VPS1 reward over range: {total_reward:.4f} DOLI",
    ]

    if data.get("accuracy_log"):
        lines.append(f"\nAccuracy log ({len(data['accuracy_log'])} entries):")
        for a in data["accuracy_log"][-5:]:
            lines.append(f"  E{a['epoch']}: projected={a['projected_bonds']} real={a['real_bonds']} acc={a['accuracy_pct']}%")

    return "\n".join(lines)


def _parse_kv(text: str, key: str, cast=str):
    m = re.search(rf'{key}\s*=\s*([\d.]+)', text, re.IGNORECASE)
    return cast(m.group(1)) if m else None


def route_query(query: str) -> str:
    data = load_projections()
    q = query.lower().strip()

    if "recalibrate" in q or "recalib" in q:
        return handle_recalibrate(query, data)
    if "accuracy" in q and ("check" in q or "actual" in q):
        return handle_accuracy_check(query, data)
    if "when" in q and "bond" in q:
        return handle_when_bond(data)
    if ("what is s" in q or "share" in q) and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_s_at_epoch(q, data)
    if "reward" in q and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_reward_at_epoch(q, data)
    if ("how many bonds" in q or "bond count" in q or "bonds at" in q) and ("epoch" in q or re.search(r'e\d+', q)):
        return handle_bonds_at_epoch(q, data)
    if "summary" in q or "overview" in q:
        return handle_summary(data)

    epoch_num = parse_epoch_num(q)
    if epoch_num is not None:
        e = get_epoch(data, epoch_num)
        if e:
            return json.dumps(e, indent=2)
        return f"Epoch {epoch_num} not in projection range."

    return (
        "Could not understand query. Try:\n"
        '  "when does vps1 next bond"\n'
        '  "what is s at epoch 85"\n'
        '  "reward at epoch 85"\n'
        '  "how many bonds at epoch 90"\n'
        '  "accuracy check e80 actual_bonds=2757"\n'
        '  "recalibrate e80 total_bonds=2757 vps1_bonds=12 vps1_spendable=6.48"\n'
        '  "summary"'
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py \"<query>\"")
        sys.exit(1)
    print(route_query(" ".join(sys.argv[1:])))
