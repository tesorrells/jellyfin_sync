"""Configuration helpers for Manifest Server."""
import os

WEBTORRENT_BIN = os.environ.get("WEBTORRENT_BIN", "webtorrent")
WAIT_SEED_TIMEOUT = int(os.environ.get("WAIT_SEED_TIMEOUT", "300"))  # seconds 