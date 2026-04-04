#!/usr/bin/env python3
"""
DOLI Projections Webhook Listener

Runs on Mac as a launchd service. Listens for GitHub webhook pushes
on port 9000, validates HMAC-SHA256 signature, and runs git pull
on the deep-space-network repo to keep projections fresh.

No external dependencies — uses stdlib http.server only.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- Configuration ---
PORT = 9000
WEBHOOK_SECRET = os.environ.get("DOLI_WEBHOOK_SECRET", "")
REPO_DIR = os.path.expanduser("~/Desktop/doli/deep-space-network")

LOG_FILE = os.path.expanduser("~/Desktop/doli/webhook.log")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("doli-webhook")


def verify_signature(payload: bytes, signature: str) -> bool:
    """Validate GitHub webhook HMAC-SHA256 signature."""
    if not WEBHOOK_SECRET:
        log.warning("No webhook secret configured — skipping verification")
        return True

    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)


def git_pull():
    """Pull latest from origin/main."""
    try:
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "pull", "--ff-only", "origin", "main"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log.info(f"git pull success: {result.stdout.strip()}")
        else:
            log.error(f"git pull failed: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        log.error(f"git pull error: {e}")
        return False


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)

        # Verify signature
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(payload, signature):
            log.warning(f"Invalid signature from {self.client_address[0]}")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Invalid signature")
            return

        # Parse event
        event = self.headers.get("X-GitHub-Event", "")
        if event != "push":
            log.info(f"Ignoring event: {event}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK (ignored)")
            return

        # Parse payload
        try:
            data = json.loads(payload)
            ref = data.get("ref", "")
            commits = data.get("commits", [])
            if commits:
                latest = commits[-1].get("message", "")[:80]
            else:
                latest = "(no commits)"
        except json.JSONDecodeError:
            latest = "(parse error)"
            ref = ""

        log.info(f"Push received on {ref}: {latest}")

        # Only pull for main branch
        if ref == "refs/heads/main":
            success = git_pull()
            if success:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Pulled successfully")
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Pull failed")
        else:
            log.info(f"Ignoring push to {ref}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK (not main)")

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"DOLI webhook listener active")

    def log_message(self, format, *args):
        """Suppress default request logging (we use our own)."""
        pass


def main():
    if not WEBHOOK_SECRET:
        log.warning("DOLI_WEBHOOK_SECRET not set — running without signature verification")

    if not os.path.isdir(REPO_DIR):
        log.info(f"Repo dir {REPO_DIR} doesn't exist — cloning")
        subprocess.run(
            ["git", "clone", "https://github.com/mapusimito/deep-space-network.git", REPO_DIR],
            timeout=60,
        )

    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    log.info(f"Webhook listener starting on port {PORT}")
    log.info(f"Repo: {REPO_DIR}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
