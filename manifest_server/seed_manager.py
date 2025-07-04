"""Background seeding of files/directories using webtorrent-cli.
Only intended for use on the curator node.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Dict, Optional, Callable
import time

from .config import WEBTORRENT_BIN, WAIT_SEED_TIMEOUT


class SeedProcess:
    """Track a single webtorrent-cli seed."""

    def __init__(self, path: Path, proc: subprocess.Popen):
        self.path = path
        self.magnet: Optional[str] = None
        self.proc = proc

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def set_magnet(self, uri: str) -> None:
        self.magnet = uri


class SeedManager:
    """Singleton-like manager that keeps webtorrent seed processes alive."""

    def __init__(self) -> None:
        self._seeds: Dict[Path, SeedProcess] = {}
        self._lock = threading.Lock()

    def seed(self, path: Path, on_magnet: Optional[Callable[[str], None]] = None) -> str:
        """Start seeding *path*; return magnet URI (existing seed reused).
        If *on_magnet* is provided it will be called once the magnet URI is known."""
        path = path.expanduser().resolve()
        with self._lock:
            if path in self._seeds and self._seeds[path].is_alive():
                return self._seeds[path].magnet or "pending"

            cmd = [
                WEBTORRENT_BIN,
                "seed",
                str(path),
                "--json",
                "--keep-seeding",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Wait for JSON metadata line (webtorrent prints exactly one JSON line)
            magnet: str | None = None
            if proc.stdout:
                iterations = int(WAIT_SEED_TIMEOUT / 0.2)
                for _ in range(iterations):
                    line = proc.stdout.readline() or (proc.stderr.readline() if proc.stderr else "")
                    if not line:
                        time.sleep(0.2)
                        continue

                    stripped = line.strip()

                    # 1. Attempt JSON parse
                    try:
                        info = json.loads(stripped)
                        magnet = info["torrent"]["magnetURI"]
                        break
                    except json.JSONDecodeError:
                        pass  # not JSON

                    # 2. Fallback: look for a raw magnet URI line
                    if stripped.startswith("magnet:?xt=urn:btih:"):
                        magnet = stripped
                        break

            if not magnet:
                proc.kill()
                raise RuntimeError(
                    "webtorrent did not emit JSON metadata within timeout. Is webtorrent-cli installed ≥0.115?"
                )

            sp = SeedProcess(path, proc)
            self._seeds[path] = sp
            threading.Thread(target=self._collect_magnet, args=(sp, on_magnet), daemon=True).start()
            return None

    def active_seeds(self) -> Dict[str, str]:
        """Return mapping path->magnet for running seeds."""
        with self._lock:
            return {str(p): sp.magnet or "pending" for p, sp in self._seeds.items()}

    def _collect_magnet(self, sp: "SeedProcess", cb: Optional[Callable[[str], None]]) -> None:
        """Read process output until magnet URI obtained or process exits.
        Calls *cb* when magnet becomes available."""
        # Wait for JSON metadata line (webtorrent prints exactly one JSON line)
        if sp.proc.stdout:
            iterations = int(WAIT_SEED_TIMEOUT / 0.2)
            for _ in range(iterations):
                line = sp.proc.stdout.readline() or (sp.proc.stderr.readline() if sp.proc.stderr else "")
                if not line:
                    time.sleep(0.2)
                    continue

                stripped = line.strip()

                # 1. Attempt JSON parse
                try:
                    info = json.loads(stripped)
                    uri = info["torrent"]["magnetURI"]
                    sp.set_magnet(uri)
                    if cb:
                        cb(uri)
                    return
                except json.JSONDecodeError:
                    pass  # not JSON

                # 2. Fallback: look for a raw magnet URI line
                if stripped.startswith("magnet:?xt=urn:btih:"):
                    uri = stripped
                    sp.set_magnet(uri)
                    if cb:
                        cb(uri)
                    return


# Global instance
seed_manager = SeedManager() 