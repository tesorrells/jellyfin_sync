from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_from_directory
import threading
import logging

from .seed_manager import seed_manager

MANIFEST_DIR = Path(os.environ.get("MANIFEST_DIR", "manifests"))
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

logger = logging.getLogger(__name__)


# ---------- helpers -----------------------------------------------------------

def _manifest_path(group: str) -> Path:
    return MANIFEST_DIR / f"{group}.json"


# ---------- routes ------------------------------------------------------------

@app.route("/")
def root() -> Any:  # noqa: ANN401
    return jsonify({"status": "Manifest server online"})


@app.route("/manifest/<group>.json", methods=["GET", "POST"])
def manifest(group: str):  # noqa: ANN001
    path = _manifest_path(group)

    if request.method == "GET":
        if not path.exists():
            abort(404, description="Manifest not found")
        # send_from_directory handles correct mimetype + caching headers
        return send_from_directory(MANIFEST_DIR, path.name, mimetype="application/json")

    # POST → overwrite manifest
    try:
        data = request.get_json(force=True)
    except Exception:  # noqa: BLE001
        abort(400, description="Invalid JSON body")

    with path.open("w") as fh:
        json.dump(data, fh, indent=2)
    return jsonify({"status": "saved", "group": group}), 201


# ---------- seeding -----------------------------------------------------------

@app.route("/seed", methods=["POST"])
def seed_file():  # noqa: ANN001
    """Start seeding a local file or directory and update the manifest.

    Expected JSON body:
        {
          "path": "/absolute/path/to/file_or_dir",
          "group": "family",
          "title": "Optional Display Title",
          "dest_path": "Relative/Inside/Download/Dir.ext"
        }
    """
    try:
        data = request.get_json(force=True)
        source = Path(data["path"]).expanduser().resolve()
        group = data.get("group", "family")
        title = data.get("title", source.stem)
        dest_path = data.get("dest_path", source.name)
    except Exception as exc:  # noqa: BLE001
        abort(400, description=f"Invalid body: {exc}")

    if not source.exists():
        abort(404, description="Source path does not exist")

    # If already seeding we might already have a magnet
    current = seed_manager.active_seeds().get(str(source))

    if current and current != "pending":
        magnet = current
        status_code = 201
    else:
        magnet = None
        status_code = 202

        def _seed_task() -> None:
            try:
                m = seed_manager.seed(source)
                if not m:
                    return  # still pending; magnet thread will eventually set it

                # Update manifest once magnet available
                path = _manifest_path(group)
                if path.exists():
                    with path.open() as fh:
                        manifest_data = json.load(fh)
                else:
                    manifest_data = {"group": group, "items": []}

                for item in manifest_data["items"]:
                    if item.get("torrent") == m:
                        break
                else:
                    manifest_data["items"].append(
                        {
                            "title": title,
                            "torrent": m,
                            "path": dest_path,
                        }
                    )

                with path.open("w") as fh:
                    json.dump(manifest_data, fh, indent=2)

                logger.info("Seed ready %s", m)
            except Exception as exc:  # noqa: BLE001
                logger.error("Seed task failed for %s: %s", source, exc)

        threading.Thread(target=_seed_task, daemon=True).start()

    return jsonify({"status": "seeding", "magnet": magnet, "group": group}), status_code


@app.route("/seeds", methods=["GET"])
def list_seeds():  # noqa: ANN001
    """Return currently running seeds (path→magnet)."""
    return jsonify(seed_manager.active_seeds())


# ---------- CLI ---------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 