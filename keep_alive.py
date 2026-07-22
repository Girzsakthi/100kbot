"""
Keep-alive web server for free-tier hosts (e.g. Replit) that spin down a
project when it receives no HTTP traffic. Runs a tiny Flask server on a
background thread alongside the Telegram bot's polling loop; an external
uptime pinger (UptimeRobot, cron-job.org, etc.) hits it every few minutes to
keep the process alive.

Not needed on hosts that keep the process running regardless of HTTP
traffic (a VM, a container platform, Replit's "Always On"/Reserved VM).
"""

import logging
import os
import threading

from flask import Flask

logger = logging.getLogger("100k_bot.keep_alive")

app = Flask(__name__)


@app.route("/")
def _health() -> str:
    return "100K Launch Bot is alive."


def _run() -> None:
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)


def start() -> None:
    """Start the keep-alive server on a background thread."""
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("Keep-alive server started on port %s", os.getenv("PORT", "8080"))
