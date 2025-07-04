"""Auto-Sync daemon

Periodically fetches a manifest JSON, downloads new torrents with `webtorrent-cli`,
and triggers a Jellyfin library refresh. Designed to run under systemd or as a
one-shot script (`--once`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
import schedule
from rich.logging import RichHandler
import random
import shutil

from . import config

logger = logging.getLogger("autosync")


# ---------- Helper utilities -------------------------------------------------

def setup_logging() -> None:
    """Configure colourful console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """Return SHA-256 hash of *path*. Large files are streamed."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def has_enough_free_space(min_free_gb: int) -> bool:
    """Return True if the partition holding DOWNLOAD_DIR has *min_free_gb* or more free space."""
    total, used, free = shutil.disk_usage(config.DOWNLOAD_DIR)
    free_gb = free / (1024 ** 3)
    return free_gb >= min_free_gb


# ---------- Jellyfin integration ---------------------------------------------

def trigger_jellyfin_scan() -> None:
    """Ask Jellyfin to refresh the library if an API key is configured."""
    if not config.JELLYFIN_API_KEY:
        logger.info("[Jellyfin] No API key provided – skipping library refresh")
        return

    url = f"{config.JELLYFIN_URL.rstrip('/')}/Library/Refresh?api_key={config.JELLYFIN_API_KEY}"
    try:
        resp = requests.post(url, timeout=10)
        resp.raise_for_status()
        logger.info("[Jellyfin] Library refresh triggered")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Jellyfin] Failed to trigger library refresh: %s", exc)


# ---------- Torrent downloading ----------------------------------------------

def download_torrent(magnet_uri: str) -> None:
    """Invoke `webtorrent-cli` to download *magnet_uri* into DOWNLOAD_DIR."""
    logger.info("[Torrent] Starting download → %s", magnet_uri)
    cmd = [
        config.WEBTORRENT_BIN,
        "download",
        magnet_uri,
        "--out",
        str(config.DOWNLOAD_DIR),
        "--quiet",
        "--timeout",
        "600",
        "--recheck",
    ]
    try:
        subprocess.run(cmd, check=True)
        logger.info("[Torrent] Download completed")
    except subprocess.CalledProcessError as exc:
        logger.error("[Torrent] webtorrent exited with code %s", exc.returncode)
        raise


# ---------- Manifest processing ----------------------------------------------

def load_manifest() -> dict[str, Any]:
    """Fetch the manifest JSON with retry/back-off."""
    delay = 60  # 1 min initial
    for attempt in range(1, config.RETRY_ATTEMPTS + 1):
        try:
            logger.debug("Fetching manifest (attempt %s/%s)…", attempt, config.RETRY_ATTEMPTS)
            resp = requests.get(config.MANIFEST_URL, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Manifest fetch failed (attempt %s): %s", attempt, exc)
            if attempt == config.RETRY_ATTEMPTS:
                raise
            time.sleep(delay + random.uniform(0, 5))
            delay *= 2  # exponential back-off


def process_item(item: dict[str, Any]) -> None:
    """Ensure *item* (one entry from manifest) exists locally, downloading if necessary."""
    target_path = config.DOWNLOAD_DIR / item["path"]

    if target_path.exists():
        # If a hash is provided, verify integrity
        if "sha256" in item:
            local_hash = sha256_file(target_path)
            if local_hash.lower() == item["sha256"].lower():
                logger.info("[Skip] %s already present and hash verified", target_path)
                return
            else:
                logger.warning(
                    "Hash mismatch for %s – re-downloading", target_path.name
                )
                target_path.unlink(missing_ok=True)
        else:
            logger.info("[Skip] %s already present", target_path)
            return

    # Ensure we have disk space before starting download
    if not has_enough_free_space(config.MIN_FREE_GB):
        logger.error("Insufficient disk space (< %s GB) – skipping %s", config.MIN_FREE_GB, target_path.name)
        return

    # Ensure parent directories exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Retry download if necessary
    for attempt in range(1, config.RETRY_ATTEMPTS_DOWNLOAD + 1):
        try:
            download_torrent(item["torrent"])
            break  # success
        except Exception as exc:  # noqa: BLE001
            logger.warning("Download failed (attempt %s/%s): %s", attempt, config.RETRY_ATTEMPTS_DOWNLOAD, exc)
            if attempt == config.RETRY_ATTEMPTS_DOWNLOAD:
                logger.error("Giving up on %s after %s attempts", target_path.name, attempt)
                return
            time.sleep(30 * attempt)

    # Verify hash post-download (if provided)
    if "sha256" in item:
        local_hash = sha256_file(target_path)
        if local_hash.lower() != item["sha256"].lower():
            logger.error("Hash mismatch after download for %s", target_path.name)
            quarantine_dir = config.DOWNLOAD_DIR / "corrupt"
            quarantine_dir.mkdir(exist_ok=True)
            target_path.rename(quarantine_dir / target_path.name)
            return


def sync_cycle() -> None:
    """Execute a single sync cycle."""
    try:
        manifest = load_manifest()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch manifest: %s", exc)
        return

    items = manifest.get("items", [])
    logger.info("Processing %d items from manifest", len(items))
    for entry in items:
        try:
            process_item(entry)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error while processing item %s: %s", entry.get("title"), exc)

    trigger_jellyfin_scan()


# ---------- Entry point -------------------------------------------------------

def main(run_once: bool = False) -> None:  # noqa: D401
    """Run the daemon."""
    setup_logging()
    logger.info("Auto-Sync daemon started | group=%s | interval=%s min", config.GROUP, config.CHECK_INTERVAL_MINUTES)

    if run_once:
        sync_cycle()
        return

    # Schedule periodic execution
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(sync_cycle)
    sync_cycle()  # run immediately on startup

    while True:  # simple scheduler loop
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decentralized Media Auto-Sync Daemon")
    parser.add_argument("--once", action="store_true", help="run a single sync cycle and exit")
    args = parser.parse_args()
    try:
        main(run_once=args.once)
    except KeyboardInterrupt:
        sys.exit(0) 