#!/usr/bin/env python3
"""
Simulación del modelo BOND_UNIT elástico.

Bajo este modelo, el costo de un bono se ajusta proporcionalmente al
crecimiento de la red:

    BOND_UNIT(t) = max(FLOOR, 10 * B0 / B(t))

Esto elimina el techo de bondeo sin tocar el supply total ni la
programación de halvings.

Usa projections.json del proyecto principal como estado inicial.
"""

import json
import math
import sys
from pathlib import Path

# Constants
BLOCKS_PER_EPOCH = 360
EPOCHS_PER_YEAR = 8760
EPOCHS_PER_ERA = 4 * EPOCHS_PER_YEAR  # 35,040
MAX_STAKE = 3000
BOND_UNIT_INITIAL = 10.0
BOND_UNIT_FLOOR = 0.01  # never below 1 cent (anti-spam)


def block_reward(epoch_offset: int) -> float:
    """Halving schedule. R = 1 in Era 1, halves each era."""
    era = epoch_offset // EPOCHS_PER_ERA
    return BOND_UNIT_INITIAL * (0.5 ** era) / 10.0  # R = 1, 0.5, 0.25, ...


def bond_unit(B_current: float, B0: int) -> float:
    """Elastic BOND_UNIT — cost of bonding decreases as network grows."""
    return max(BOND_UNIT_FLOOR, BOND_UNIT_INITIAL * B0 / B_current)


def load_anchor():
    """Load current network state from ../projections.json."""
    path = Path(__file__).parent.parent / "projections.json"
    with open(path) as f:
        data = json.load(f)
    m = data["metadata"]
    e0 = data["epochs"][0]
    return {
        "anchor_epoch": m["anchor_epoch"],
        "B0": m["anchor_total_bonds"],
        "d": m["dilution_rate"],
        "vps1_b": e0["vps1"]["bonds"],
        "vps2_b": e0["vps2"]["bonds"],
        "vps1_s": e0["vps1"]["spendable"],
        "vps2_s": e0["vps2"]["spendable"],
    }


def simulate(max_epochs: int = 200_000):
    anchor = load_anchor()
    B0 = anchor["B0"]
    d = anchor["d"]
    s = BLOCKS_PER_EPOCH / B0
    B = float(B0)

    v1_b = anchor["vps1_b"]
    v2_b = anchor["vps2_b"]
    v1_s = anchor["vps1_s"]
    v2_s = anchor["vps2_s"]

    bond_events = []
    bu_log = []
    capped_warning = False

    for offset in range(1, max_epochs + 1):
        epoch = anchor["anchor_epoch"] + offset

        # Apply dilution
        s *= (1 - d)
        if s <= 0:
            break
        B = BLOCKS_PER_EPOCH / s
        if B > 1e18:  # numerical guardrail
            if not capped_warning:
                print(f"  [warn] B exceeded 1e18 at E{epoch}, halting")
                capped_warning = True
            break

        # Era reward
        R = block_reward(offset)
        s_eff = R * BLOCKS_PER_EPOCH / B

        # Earn
        v1_s += v1_b * s_eff
        v2_s += v2_b * s_eff

        # Current bond cost
        BU = bond_unit(B, B0)
        threshold = BU + 0.001
        bu_log.append((epoch, BU, B))

        # Combined pool bonding (bond fewer-bonds VPS first)
        for _ in range(2):
            if v1_b >= MAX_STAKE and v2_b >= MAX_STAKE:
                break
            combined = v1_s + v2_s
            if combined < threshold:
                break

            if v1_b <= v2_b and v1_b < MAX_STAKE:
                deficit = BU - v1_s
                if deficit > 0:
                    transfer = min(deficit, v2_s)
                    v2_s -= transfer
                    v1_s += transfer
                if v1_s >= BU:
                    v1_s -= BU
                    v1_b += 1
                    bond_events.append((epoch, "v1", v1_b, BU, B, R))
            elif v2_b < MAX_STAKE:
                deficit = BU - v2_s
                if deficit > 0:
                    transfer = min(deficit, v1_s)
                    v1_s -= transfer
                    v2_s += transfer
                if v2_s >= BU:
                    v2_s -= BU
                    v2_b += 1
                    bond_events.append((epoch, "v2", v2_b, BU, B, R))
            else:
                break

    return {
        "anchor": anchor,
        "events": bond_events,
        "bu_log": bu_log,
        "final": (v1_b, v2_b, v1_s, v2_s, B, s),
    }


def report(result):
    a = result["anchor"]
    print("=" * 72)
    print("ELASTIC BOND_UNIT MODEL — SIMULATION REPORT")
    print("=" * 72)
    print(f"\nAnchor:    E{a['anchor_epoch']}")
    print(f"B0:        {a['B0']}")
    print(f"VPS1:      {a['vps1_b']} bonds, {a['vps1_s']:.4f} spendable")
    print(f"VPS2:      {a['vps2_b']} bonds, {a['vps2_s']:.4f} spendable")
    print(f"Dilution:  {a['d']:.4f} per epoch")
    print(f"BOND_UNIT formula: max({BOND_UNIT_FLOOR}, 10 * {a['B0']} / B)")

    events = result["events"]
    print(f"\nTotal bond events: {len(events)}")

    if events:
        print(f"\nFirst 15 events:")
        last = a["anchor_epoch"]
        for ep, who, nb, bu, B, R in events[:15]:
            gap = ep - last
            era = (ep - a["anchor_epoch"]) // EPOCHS_PER_ERA + 1
            print(f"  E{ep:>7} (Era {era}, gap +{gap:>3})  "
                  f"{who}->{nb}b  cost={bu:.6f} DOLI  B={int(B):>12,}")
            last = ep

        if len(events) > 15:
            print(f"  ... ({len(events) - 15} more)")
            print(f"\nLast 3 events:")
            for ep, who, nb, bu, B, R in events[-3:]:
                era = (ep - a["anchor_epoch"]) // EPOCHS_PER_ERA + 1
                print(f"  E{ep:>7} (Era {era})  "
                      f"{who}->{nb}b  cost={bu:.8f} DOLI  B={int(B):>15,}")

    v1, v2, v1s, v2s, B, s = result["final"]
    print(f"\nFinal state:")
    print(f"  VPS1: {v1} bonds, {v1s:.6f} spendable")
    print(f"  VPS2: {v2} bonds, {v2s:.6f} spendable")
    print(f"  B = {int(B):,}, s = {s:.4e}")

    # Milestones
    print(f"\nWhen does BOND_UNIT cross each threshold?")
    milestones = [5, 1, 0.1, 0.01]
    hit = {m: None for m in milestones}
    for ep, bu, B in result["bu_log"]:
        for m in milestones:
            if hit[m] is None and bu <= m:
                hit[m] = (ep, B)
    for m in milestones:
        v = hit[m]
        if v:
            ep, B = v
            print(f"  BU ≤ {m:>5}: E{ep} (B={int(B):,})")
        else:
            print(f"  BU ≤ {m}: not reached in horizon")


if __name__ == "__main__":
    result = simulate(max_epochs=200_000)
    report(result)
