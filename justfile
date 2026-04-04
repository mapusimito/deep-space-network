# DOLI projection system
# Queries run against ~/.doli/deep-space-network (auto-synced from VPS1)

dsn := "~/.doli/deep-space-network"

# Show current projection summary
summary:
    python3 {{dsn}}/query.py "summary"

# When does a VPS next bond? (vps1 or vps2)
next-bond vps="vps1":
    python3 {{dsn}}/query.py "when does {{vps}} next bond"

# Show share value at a given epoch
share epoch:
    python3 {{dsn}}/query.py "what is s at epoch {{epoch}}"

# Show combined reward at a given epoch
reward epoch:
    python3 {{dsn}}/query.py "combined reward at epoch {{epoch}}"

# Free-form query
query *Q:
    python3 {{dsn}}/query.py "{{Q}}"

# Recalibrate with real epoch data
recalibrate *ARGS:
    python3 {{dsn}}/query.py "recalibrate {{ARGS}}"

# Pull latest projections from GitHub
pull:
    git -C {{dsn}} pull --ff-only origin main

# Show raw projections table
table:
    cat {{dsn}}/projections.md

# Show accuracy log
accuracy:
    python3 -c "import json; [print(f'E{e[\"epoch\"]}: projected={e[\"projected_bonds\"]} real={e[\"real_bonds\"]} acc={e[\"accuracy_pct\"]}%') for e in json.load(open('{{dsn}}/projections.json'))['accuracy_log']]"

# Check VPS1 service status
vps1-status:
    ssh -i ~/.ssh/id_ed25519 root@187.124.148.105 "systemctl status doli-projections.service --no-pager"

# Check VPS1 service logs
vps1-logs lines="20":
    ssh -i ~/.ssh/id_ed25519 root@187.124.148.105 "journalctl -u doli-projections.service --no-pager -n {{lines}}"

# Run doli history on VPS1
history:
    ssh -i ~/.ssh/id_ed25519 root@187.124.148.105 "doli history"
