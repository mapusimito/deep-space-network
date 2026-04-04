# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

DOLI epoch projection system. Simulates network bond growth and reward distribution for two VPS nodes (VPS1/mapusisimito, VPS2/df80f5d70af4) on the DOLI Proof-of-Time blockchain.

## Commands

```bash
# Generate/regenerate projections from default config
python3 doli/simulate.py

# Query projections (natural language)
python3 doli/query.py "when does vps1 next bond"
python3 doli/query.py "what is s at epoch 25"
python3 doli/query.py "combined reward at epoch 30"
python3 doli/query.py "summary"

# Recalibrate with real epoch data (regenerates all projections)
python3 doli/query.py "recalibrate e19 total_bonds=668 vps1_spendable=1.13 vps2_spendable=0.31"
```

## Architecture

- `doli/simulate.py` — Simulation engine. `SimConfig` holds all model parameters. `simulate()` runs epoch-by-epoch, returns dict with metadata + epochs array. `save_projections()` writes both JSON and markdown.
- `doli/query.py` — CLI query router. Parses natural language, dispatches to handler functions. Also handles recalibration (updates anchor, adjusts growth rates, regenerates).
- `doli/projections.json` — Generated output. Machine-readable. Contains metadata, epochs array, and accuracy_log.
- `doli/projections.md` — Generated output. Human-readable table.

## Core Formula

```
s = 360 / total_bonds          # share per bond per epoch
reward = producer_bonds * s     # epoch reward for a producer
```

Bond cost: 10 DOLI. Autobond threshold: 10.01 DOLI spendable. Bonds are epoch-deferred (take effect next epoch).

## Pessimistic Model Assumptions

- Structural nodes (6): alternating growth pattern (accumulate/burst epochs)
- Mid miners (N7-N13): +1 bond per producer every 2 epochs
- Other miners: stable
- Growth rates are recalibrated when real data comes in

## Live Data Pipeline

Projections are auto-updated by VPS1 and synced to Mac via GitHub.

**Data flow:** VPS1 detects epoch -> fetches real RPC data -> recalibrates -> regenerates -> commits to GitHub -> Mac pulls every 2min

**To query projections (no SSH needed):**
```bash
# Pull latest (also happens automatically every 2 min)
git -C ~/.doli/deep-space-network pull

# Query locally
python3 ~/.doli/deep-space-network/query.py "summary"
python3 ~/.doli/deep-space-network/query.py "when does vps1 next bond"
```

**GitHub repo:** mapusimito/deep-space-network
- Every epoch = one commit
- Commit format: `E{epoch} | bonds={total} | s={value} | acc={accuracy}% | vps1={bonds}b vps2={bonds}b`

**VPS1 services (187.124.148.105):**
- `doli-projections.service` — epoch detection + auto-recalibrate + git push
- `doli-projections-http.service` — serves on port 8888

**Mac service:**
- `com.doli.sync` (launchd) — git pull every 2 min to `~/.doli/deep-space-network/`

## JSON Structure

Epochs use nested objects: `e["vps1"]["bonds"]`, `e["vps1"]["spendable"]`, `e["vps2"]["reward"]`.
Each epoch has a `"real"` boolean field — true means confirmed from RPC, false means projected.

## Key Constraint

Always read `~/.doli/deep-space-network/projections.json` before answering numerical questions. Never guess rewards — calculate from `s = 360 / total_bonds`. Precision: 4 decimal places on `s`, 8 on DOLI amounts.
