"""Background seeding of files/directories using webtorrent-cli.
Only intended for use on the curator node.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Dict

from .config import WEBTORRENT_BIN


class SeedProcess:
    """Track a single webtorrent-cli seed."""

    def __init__(self, path: Path, magnet: str, proc: subprocess.Popen):
        self.path = path
        self.magnet = magnet
        self.proc = proc

    def is_alive(self) -> bool:
        return self.proc.poll() is None


class SeedManager:
    """Singleton-like manager that keeps webtorrent seed processes alive."""

    def __init__(self) -> None:
        self._seeds: Dict[Path, SeedProcess] = {}
        self._lock = threading.Lock()

    def seed(self, path: Path) -> str:
        """Start seeding *path*; return magnet URI (existing seed reused)."""
        path = path.expanduser().resolve()
        with self._lock:
            if path in self._seeds and self._seeds[path].is_alive():
                return self._seeds[path].magnet

            cmd = [
                WEBTORRENT_BIN,
                "seed",
                str(path),
                "--json",
                "--keep-seeding",
                "--quiet",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Read first line of stdout for JSON metadata
            line = proc.stdout.readline() if proc.stdout else ""
            try:
                info = json.loads(line)
                magnet = info["torrent"]["magnetURI"]
            except Exception as exc:  # noqa: BLE001
                proc.kill()
                raise RuntimeError(f"Failed to start seed: {exc}\nOutput: {line}") from exc

            self._seeds[path] = SeedProcess(path, magnet, proc)
            return magnet

    def active_seeds(self) -> Dict[str, str]:
        """Return mapping path->magnet for running seeds."""
        with self._lock:
            return {str(p): sp.magnet for p, sp in self._seeds.items() if sp.is_alive()}


# Global instance
seed_manager = SeedManager() 