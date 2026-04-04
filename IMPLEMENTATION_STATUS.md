# DOLI Projection System — Implementation Status

## Overview
Self-updating epoch projection system for DOLI blockchain node operations.
VPS1 detects epoch closes, fetches real data, recalibrates, regenerates projections,
commits and pushes to GitHub. Mac syncs automatically via launchd git pull.

## Status: Complete — 10-Flaw Fix Applied

### Simulation Engine (`simulate.py`)
- [x] Epoch-by-epoch simulation with nested vps1/vps2 JSON structure
- [x] Pessimistic model: structural alternating accumulate/burst
- [x] VPS1 and VPS2 independent autobond at >= 10.01
- [x] Epoch-deferred bond application
- [x] `real` field marking confirmed vs projected epochs
- [x] s rounded to 8 decimal places (was 4 — Flaw 3 fix)
- [x] Mid miner growth distributed evenly across epochs (was burst-only — Flaw 4 fix)

### Query Interface (`query.py`)
- [x] Natural language CLI queries against projections.json
- [x] Recalibration command
- [x] Accuracy check command
- [x] Correct default growth rates 35/70 (was 22/44 — Flaw 6 fix)

### Self-Updating Service (`update.py`)
- [x] Detects epoch boundary via `floor(height / 360)`
- [x] Sleeps until epoch boundary + 60s buffer (was 5-min polling — Flaw 5 fix)
- [x] 60s maturation wait after epoch close (Flaw 10 fix)
- [x] Fetches real data via JSON-RPC (getChainInfo, getProducers, getBalance)
- [x] Both VPS balances fetched from local RPC (chain knows all addresses)
- [x] Bond count sanity check on RPC response (Flaw 7 fix)
- [x] VPS2 RPC failure aborts regeneration (was silent fallback — Flaw 8 fix)
- [x] Recalibrates growth rates after 3+ data points (defaults 35/70 — Flaw 6 fix)
- [x] Commits and pushes to GitHub per epoch (Flaw 9 fix for deep-space-network)

### GitHub Pipeline
- [x] Repo: mapusimito/deep-space-network
- [x] VPS1 deploy key with write access
- [x] Commit format: `E{epoch} | bonds={total} | s={value} | acc={accuracy}% | vps1={bonds}b vps2={bonds}b`
- [x] Every epoch = one commit (network log from genesis)

### Mac Sync
- [x] Launchd service `com.doli.sync` pulls every 2 minutes
- [x] Local clone at `~/.doli/deep-space-network/`
- [x] Claude Code reads projections locally (no SSH needed)
- [x] Webhook listener built (`webhook.py`) — ready if port forwarding set up

### VPS1 Services (187.124.148.105)
- [x] `doli-projections.service` — update loop (active)
- [x] `doli-projections-http.service` — port 8888 (active)

## Current State
- Anchor: E19 (668 real bonds, s=0.53892216)
- Accuracy log: E19=99.7% (E20 entry removed — was premature/fabricated, Flaw 2 fix)
- VPS2 spendable corrected to 0.31 at anchor (was wrong — Flaw 1 fix)
- Structural growth defaults: accumulate=35, burst=70

## Files
- `simulate.py` — Simulation engine
- `query.py` — CLI query interface
- `update.py` — Self-updating service (runs on VPS1)
- `webhook.py` — Mac webhook listener (standby)
- `~/.doli/deep-space-network/` — Local synced projections
