"""Simple configuration module for the Auto-Sync daemon.
Values can be provided via environment variables or a .env file (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from .env if present (non-fatal if file doesn't exist)
load_dotenv()

# Manifest & group settings
MANIFEST_URL: str = os.getenv("MANIFEST_URL", "http://localhost:5000/manifest/family.json")
GROUP: str = os.getenv("GROUP", "family")

# Download location
DOWNLOAD_DIR: Path = Path(os.getenv("DOWNLOAD_DIR", "/media/movies")).expanduser().resolve()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Jellyfin integration
JELLYFIN_URL: str = os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096")
JELLYFIN_API_KEY: str | None = os.getenv("JELLYFIN_API_KEY")

# Sync behaviour
CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
RETRY_ATTEMPTS: int = int(os.getenv("RETRY_ATTEMPTS", "5"))
RETRY_ATTEMPTS_DOWNLOAD: int = int(os.getenv("RETRY_ATTEMPTS_DOWNLOAD", "3"))

# Disk space safety
MIN_FREE_GB: int = int(os.getenv("MIN_FREE_GB", "5"))

# External binaries
WEBTORRENT_BIN: str = os.getenv("WEBTORRENT_BIN", "webtorrent") 