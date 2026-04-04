# Deep Space Network 🛰️

Real-time self-updating projection system for a DOLI blockchain node operation.
Tracks network dilution, predicts future rewards, and logs bond events automatically.

---

## What is this

Two independent DOLI producers (VPS1 and VPS2) are mining on the DOLI mainnet.
This repository is the live data feed of their operation — updated automatically
every epoch (1 hour) by a service running on VPS1.

Every commit = one epoch closed. The commit history is a complete log of the
network from our genesis forward.

---

## How it works

    VPS1 node (187.124.148.105)
      └── update.py runs as systemd service
            ├── detects epoch close via local RPC
            ├── fetches real bond data from VPS1 + VPS2
            ├── compares against projections → logs accuracy
            ├── recalibrates growth model from real data
            ├── regenerates projections.json + projections.md
            └── git commit + push → this repo

    GitHub (mapusimito/deep-space-network)
      └── webhook fires on every push
            └── Mac (MEDE) receives it instantly
                  └── git pull → projections always fresh locally

    Claude Code
      └── git pull → reads projections.json → answers queries

---

## Files

| File | Description |
|------|-------------|
| `projections.json` | Machine readable epoch projections + accuracy log |
| `projections.md` | Human readable projection table |
| `simulate.py` | Simulation engine — runs epoch by epoch model |
| `update.py` | Self-updating service — runs on VPS1 as systemd |
| `query.py` | CLI query interface |
| `update.log` | Service log — every epoch event recorded |

---

## The math

DOLI uses a Proof of Time consensus. Rewards are distributed by bond weight:
s = 360 / total_bonds        # share per bond per epoch
reward = your_bonds × s      # your epoch reward

As `total_bonds` grows, `s` shrinks — this is dilution.
The reward curve `r(x) = b(x) × (360/x)` is an asymmetric bell curve.
As `x → ∞`, `s → 0` asymptotically. Rewards compress but never reach zero.

The vertex condition (peak reward point):
b'(x) = b(x) / x
Past this point every new bond returns diminishing value relative to the previous.

---

## Our producers

| Node | Name | Address | Bonds |
|------|------|---------|-------|
| VPS1 | mapusisimito | `doli1alzfhp6jxe6lzxs55l9yajfcf64una5s8dsfnhh2xzt9lnadv9as7pjl62` | 2+ |
| VPS2 | df80f5d70af4 | `doli17r677gnaj7cyhqlyxyfvkrfz63hggkryu9cr8fr7hl35etramxkshz2e49` | 2+ |

Both nodes run an autobond script that automatically stakes new bonds
whenever spendable balance reaches 10.01 DOLI.

---

## The model

**Type:** Self-calibrating time series forecasting

**Anchor:** Real epoch data (E16 onward — all validated against RPC)

**Weights:**
- Structural growth accumulate epoch: 35 bonds (6 nodes)
- Structural growth burst epoch: 70 bonds (6 nodes)

**Recalibration:** Every epoch, real bond data is compared against projection.
Accuracy is logged. Growth weights are recalibrated from last 3 real epochs.
The model self-corrects — it gets more accurate as more data comes in.

**Validated accuracy so far:**

| Epoch | Projected | Real | Accuracy |
|-------|-----------|------|----------|
| E16 | 528 | 528 | 100% |
| E17 | 564 | 563 | 99.8% |
| E18 | 635 | 635 | 100% |
| E19 | 670 | 668 | 99.7% |

---

## Querying
```bash
python3 query.py "when does vps1 next bond"
python3 query.py "what is s at epoch 25"
python3 query.py "combined reward at epoch 30"
python3 query.py "when do we reach 5 bonds each"
python3 query.py "recalibrate e19 total_bonds=668"
```

---

## Commit format

Every epoch produces one commit:
E{epoch} | bonds={total} | s={value} | acc={accuracy}% | vps1={bonds}b vps2={bonds}b

Example:
E19 | bonds=668 | s=0.5389 | acc=99.7% | vps1=2b vps2=2b

---

## Network context

19 active producers on DOLI mainnet. Two categories:

**Structural nodes (DOLI team)** — 6 nodes, ~91 bonds each, registered at genesis.
Compound aggressively in alternating burst pattern. Control ~91% of network bonds.

**Independent miners** — 13 producers including us. Combined ~53 bonds.
We run the most sophisticated independent operation on the network:
combined reward strategy, autobond, self-calibrating projections.

---

## DOLI resources

- Repository: https://github.com/doli-network/doli
- Whitepaper: https://github.com/doli-network/doli/blob/main/WHITEPAPER.md
- CLI reference: https://github.com/doli-network/doli/blob/main/docs/cli.md
- RPC reference: https://github.com/doli-network/doli/blob/main/docs/rpc_reference.md
- Explorer: https://explorer.doli.network
- Network status: https://explorer.doli.network/network.html

---

*"Time is the only fair currency."*
