"""Configuration helpers for Manifest Server."""
import os
from pathlib import Path

# Resolve project root based on this file's location
BASE_DIR = Path(__file__).resolve().parent.parent

# Provide sensible defaults that are not CWD-dependent
WEBTORRENT_BIN = os.environ.get("WEBTORRENT_BIN", "webtorrent")
DEFAULT_MANIFEST_DIR = BASE_DIR / "manifests"
MANIFEST_DIR = Path(os.environ.get("MANIFEST_DIR", DEFAULT_MANIFEST_DIR))
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

WAIT_SEED_TIMEOUT = int(os.environ.get("WAIT_SEED_TIMEOUT", "300"))  # seconds 