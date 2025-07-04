from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_from_directory

MANIFEST_DIR = Path(os.environ.get("MANIFEST_DIR", "manifests"))
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


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


# ---------- CLI ---------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 