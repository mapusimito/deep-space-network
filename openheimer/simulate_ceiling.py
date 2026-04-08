#!/usr/bin/env python3
"""
Simulación del modelo ACTUAL (BOND_UNIT fijo en 10 DOLI).

Detecta exactamente en qué epoch el bondeo se vuelve mathematically
imposible bajo el modelo del whitepaper.

Calcula el techo analítico:    lifetime = b · s / d
Y lo verifica con simulación discreta.

Usa projections.json del proyecto principal como estado inicial.
"""

import json
from pathlib import Path

BLOCKS_PER_EPOCH = 360
BOND_UNIT = 10.0
BOND_THRESHOLD = 10.01
MAX_EPOCHS = 100_000


def load_anchor():
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


def analytical_ceiling(b: int, s: float, d: float) -> dict:
    """Compute the lifetime cumulative reward and how many bonds it allows."""
    lifetime = b * s / d
    bonds_possible = int(lifetime / BOND_UNIT)
    return {
        "lifetime_reward": lifetime,
        "bonds_possible": bonds_possible,
        "ceiling_reached": lifetime < BOND_UNIT,
    }


def simulate():
    a = load_anchor()
    s = BLOCKS_PER_EPOCH / a["B0"]
    d = a["d"]

    v1_b = a["vps1_b"]
    v2_b = a["vps2_b"]
    v1_s = a["vps1_s"]
    v2_s = a["vps2_s"]

    bond_events = []
    last_event = a["anchor_epoch"]
    epochs_since_last = 0

    for offset in range(1, MAX_EPOCHS + 1):
        epoch = a["anchor_epoch"] + offset
        s *= (1 - d)
        if s <= 0:
            break

        v1_s += v1_b * s
        v2_s += v2_b * s
        epochs_since_last += 1

        # Combined pool bonding
        for _ in range(2):
            combined = v1_s + v2_s
            if combined < BOND_THRESHOLD:
                break

            if v1_b <= v2_b:
                deficit = BOND_UNIT - v1_s
                if deficit > 0:
                    transfer = min(deficit, v2_s)
                    v2_s -= transfer
                    v1_s += transfer
                if v1_s >= BOND_UNIT:
                    v1_s -= BOND_UNIT
                    v1_b += 1
                    bond_events.append((epoch, "v1", v1_b, epochs_since_last, s))
                    last_event = epoch
                    epochs_since_last = 0
            else:
                deficit = BOND_UNIT - v2_s
                if deficit > 0:
                    transfer = min(deficit, v1_s)
                    v1_s -= transfer
                    v2_s += transfer
                if v2_s >= BOND_UNIT:
                    v2_s -= BOND_UNIT
                    v2_b += 1
                    bond_events.append((epoch, "v2", v2_b, epochs_since_last, s))
                    last_event = epoch
                    epochs_since_last = 0

        # Stop early if no bond in 5000 epochs (definitely walled)
        if epochs_since_last > 5000:
            break

    return {
        "anchor": a,
        "events": bond_events,
        "final": (v1_b, v2_b, v1_s, v2_s, s, last_event),
    }


def report(result):
    a = result["anchor"]
    print("=" * 72)
    print("CURRENT MODEL (FIXED BOND_UNIT) — CEILING DETECTION")
    print("=" * 72)
    print(f"\nAnchor:    E{a['anchor_epoch']}")
    print(f"B0:        {a['B0']}")
    print(f"d:         {a['d']:.4f} per epoch")
    print(f"BOND_UNIT: {BOND_UNIT} DOLI (fixed)")
    print(f"VPS1:      {a['vps1_b']} bonds")
    print(f"VPS2:      {a['vps2_b']} bonds")

    # Analytical ceiling at anchor
    s0 = BLOCKS_PER_EPOCH / a["B0"]
    print(f"\n--- Analytical lifetime ceiling at anchor ---")
    for label, b in [("VPS1", a["vps1_b"]), ("VPS2", a["vps2_b"]),
                      ("combined", a["vps1_b"] + a["vps2_b"])]:
        c = analytical_ceiling(b, s0, a["d"])
        print(f"  {label:>10}: b={b}, lifetime={c['lifetime_reward']:.2f} DOLI, "
              f"bonds_possible={c['bonds_possible']}")

    events = result["events"]
    print(f"\nTotal bond events before wall: {len(events)}")

    if events:
        print(f"\nAll events (showing growing gaps):")
        for ep, who, nb, gap, s in events:
            print(f"  E{ep:>5}  gap=+{gap:>4}  {who}->{nb}b  s={s:.6f}")

    v1, v2, v1s, v2s, s, last = result["final"]
    print(f"\nFinal state at last bond E{last}:")
    print(f"  VPS1: {v1} bonds, {v1s:.4f} spendable")
    print(f"  VPS2: {v2} bonds, {v2s:.4f} spendable")
    print(f"  Combined spendable: {v1s + v2s:.4f}")
    print(f"  s = {s:.6f}")

    final_ceiling = analytical_ceiling(v1 + v2, s, a["d"])
    print(f"\nLifetime cumulative from this point forward:")
    print(f"  = {v1 + v2} · {s:.6f} / {a['d']:.4f} = {final_ceiling['lifetime_reward']:.4f} DOLI")
    print(f"  → enough for {final_ceiling['bonds_possible']} more bonds")
    if final_ceiling["ceiling_reached"]:
        print(f"  → MURO ABSOLUTO. Bondear nunca más será posible.")
    else:
        print(f"  → Aún hay margen.")


if __name__ == "__main__":
    result = simulate()
    report(result)
