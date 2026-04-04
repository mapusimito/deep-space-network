# DOLI Projection System — Implementation Status

## Overview
Self-updating epoch projection system for DOLI blockchain node operations.
VPS1 detects epoch closes, fetches real data, recalibrates, regenerates projections,
commits and pushes to GitHub. Mac syncs automatically via launchd git pull.

## Status: Complete — Live Pipeline Active

### Simulation Engine (`doli/simulate.py`)
- [x] Epoch-by-epoch simulation with nested vps1/vps2 JSON structure
- [x] Pessimistic model: structural alternating accumulate/burst
- [x] VPS1 and VPS2 independent autobond at >= 10.01
- [x] Epoch-deferred bond application
- [x] `real` field marking confirmed vs projected epochs

### Query Interface (`doli/query.py`)
- [x] Natural language CLI queries against projections.json
- [x] Recalibration command
- [x] Accuracy check command

### Self-Updating Service (`doli/update.py`)
- [x] Detects epoch boundary via `floor(height / 360)`
- [x] 60s maturation wait after epoch close
- [x] Fetches real data via JSON-RPC (getChainInfo, getProducers, getBalance)
- [x] Both VPS balances fetched from local RPC (chain knows all addresses)
- [x] Recalibrates growth rates after 3+ data points
- [x] Commits and pushes to GitHub per epoch

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
- Anchor: E21 (713 real bonds, s=0.5049)
- Accuracy log: E19=99.7%, E20=97.2%, E21=97.2%
- Structural growth: accumulate=15, burst=30 (recalibrated from real data)

## Files
- `doli/simulate.py` — Simulation engine
- `doli/query.py` — CLI query interface
- `doli/update.py` — Self-updating service (runs on VPS1)
- `doli/webhook.py` — Mac webhook listener (standby)
- `~/.doli/deep-space-network/` — Local synced projections
