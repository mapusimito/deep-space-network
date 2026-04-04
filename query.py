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
