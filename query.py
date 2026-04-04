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
    python query.py "summary"
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


def handle_when_bond(query: str, data: dict) -> str:
    current_epoch = data["metadata"]["anchor_epoch"]

    if "vps1" in query or "mapusisimito" in query:
        key, name = "vps1", "VPS1"
    elif "vps2" in query or "df80f5d70af4" in query:
        key, name = "vps2", "VPS2"
    else:
        results = []
        for e in data["epochs"]:
            if e["epoch"] <= current_epoch:
                continue
            if e["vps1"]["bonded_this_epoch"]:
                results.append(f"VPS1 bonds at E{e['epoch']} (bonds -> {e['vps1']['bonds']+1})")
                break
        for e in data["epochs"]:
            if e["epoch"] <= current_epoch:
                continue
            if e["vps2"]["bonded_this_epoch"]:
                results.append(f"VPS2 bonds at E{e['epoch']} (bonds -> {e['vps2']['bonds']+1})")
                break
        return "\n".join(results) if results else "No bonding events projected."

    for e in data["epochs"]:
        if e["epoch"] <= current_epoch:
            continue
        if e[key]["bonded_this_epoch"]:
            bonds_after = e[key]["bonds"] + 1
            return f"{name} next bonds at E{e['epoch']} (will have {bonds_after} bonds effective E{e['epoch']+1})"

    return f"No bonding event projected for {name} in range."


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
    v1, v2 = e["vps1"], e["vps2"]
    real_tag = " [REAL]" if e.get("real") else ""
    return (
        f"E{epoch_num} rewards (s = {e['s']:.4f}, total_bonds = {e['total_bonds']}){real_tag}:\n"
        f"  VPS1: {v1['reward']:.8f} DOLI ({v1['bonds']} bonds)\n"
        f"  VPS2: {v2['reward']:.8f} DOLI ({v2['bonds']} bonds)\n"
        f"  Combined: {e['combined_reward']:.8f} DOLI"
    )


def handle_bonds_at_epoch(query: str, data: dict) -> str:
    epoch_num = parse_epoch_num(query)
    if epoch_num is None:
        return "Could not parse epoch number."
    e = get_epoch(data, epoch_num)
    if e is None:
        return f"Epoch {epoch_num} not in projection range."
    v1, v2 = e["vps1"], e["vps2"]
    total_ours = v1["bonds"] + v2["bonds"]
    return (f"E{epoch_num}: VPS1 = {v1['bonds']} bonds, VPS2 = {v2['bonds']} bonds, "
            f"combined = {total_ours} bonds (network = {e['total_bonds']})")


def handle_when_reach(query: str, data: dict) -> str:
    m = re.search(r'(\d+)\s*bonds?\s*(each|total|combined)?', query, re.IGNORECASE)
    if not m:
        return "Could not parse target bond count."
    target = int(m.group(1))
    mode = (m.group(2) or "each").lower()

    for e in data["epochs"]:
        v1, v2 = e["vps1"], e["vps2"]
        if mode == "each":
            if v1["bonds"] >= target and v2["bonds"] >= target:
                return (f"Both VPS reach {target} bonds each at E{e['epoch']} "
                        f"(VPS1={v1['bonds']}, VPS2={v2['bonds']})")
        elif mode in ("total", "combined"):
            if v1["bonds"] + v2["bonds"] >= target:
                return (f"Combined {target} bonds reached at E{e['epoch']} "
                        f"(VPS1={v1['bonds']}, VPS2={v2['bonds']})")

    return f"Target of {target} bonds ({mode}) not reached in projection range."


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
        return "Usage: recalibrate eX total_bonds=Y [vps1_bonds=A] [vps1_spendable=B] [vps2_bonds=C] [vps2_spendable=D]"

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
    vps2_bonds = _parse_kv(query, "vps2_bonds", int)
    vps2_spendable = _parse_kv(query, "vps2_spendable", float)

    if old_epoch:
        v1, v2 = old_epoch["vps1"], old_epoch["vps2"]
        if vps1_bonds is None: vps1_bonds = v1["bonds"]
        if vps1_spendable is None: vps1_spendable = v1["spendable"]
        if vps2_bonds is None: vps2_bonds = v2["bonds"]
        if vps2_spendable is None: vps2_spendable = v2["spendable"]

    # Recalculate structural growth if enough data
    old_meta = data["metadata"]
    sg = old_meta.get("structural_growth", {})
    new_accumulate = sg.get("accumulate_epoch", 22)
    new_burst = sg.get("burst_epoch", 44)

    if len(accuracy_log) >= 3:
        recent = accuracy_log[-4:]
        growths = []
        for i in range(1, len(recent)):
            ed = recent[i]["epoch"] - recent[i-1]["epoch"]
            bd = recent[i]["real_bonds"] - recent[i-1]["real_bonds"]
            if ed > 0:
                growths.append(bd / ed)
        if len(growths) >= 2:
            avg = sum(growths) / len(growths)
            base = avg / 1.5
            new_accumulate = max(1, int(round(base)))
            new_burst = max(1, int(round(base * 2)))

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

    new_data = simulate(config)
    new_data["accuracy_log"] = accuracy_log
    save_projections(new_data)

    lines = [
        f"Recalibrated from E{epoch_num} (total_bonds={real_total_bonds})",
        f"  Structural growth: accumulate={new_accumulate}, burst={new_burst}",
        f"  VPS1: {vps1_bonds} bonds, {vps1_spendable:.4f} spendable",
        f"  VPS2: {vps2_bonds} bonds, {vps2_spendable:.4f} spendable",
    ]
    if len(accuracy_log) > 0:
        lines.append(f"  Latest accuracy: {accuracy_log[-1]['accuracy_pct']:.1f}%")
    lines.append(f"\nRegenerated projections E{epoch_num} to E{config.target_epoch}")
    return "\n".join(lines)


def handle_summary(data: dict) -> str:
    meta = data["metadata"]
    sg = meta.get("structural_growth", {})
    epochs = data["epochs"]
    first, last = epochs[0], epochs[-1]

    vps1_events = [e["epoch"] for e in epochs if e["vps1"]["bonded_this_epoch"]]
    vps2_events = [e["epoch"] for e in epochs if e["vps2"]["bonded_this_epoch"]]
    real_count = sum(1 for e in epochs if e.get("real"))
    total_combined = sum(e["combined_reward"] for e in epochs)

    lines = [
        f"Projection: E{meta['anchor_epoch']} -> E{meta['target_epoch']} ({meta['model']} model)",
        f"Structural growth: accumulate={sg.get('accumulate_epoch', '?')}, burst={sg.get('burst_epoch', '?')}",
        f"Network: {first['total_bonds']} -> {last['total_bonds']} bonds",
        f"Share value: {first['s']:.4f} -> {last['s']:.4f}",
        f"Real data points: {real_count}",
        f"",
        f"VPS1: {first['vps1']['bonds']} -> {last['vps1']['bonds']} bonds | bond epochs: {vps1_events}",
        f"VPS2: {first['vps2']['bonds']} -> {last['vps2']['bonds']} bonds | bond epochs: {vps2_events}",
        f"",
        f"Total combined reward over range: {total_combined:.4f} DOLI",
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
        print('  python query.py "summary"')
        sys.exit(1)
    print(route_query(" ".join(sys.argv[1:])))
