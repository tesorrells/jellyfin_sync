# Decentralized Media Sync

An open-source reference implementation of the "Decentralized Media Sharing System" described in `decentralized_media_sync.md`.  
It consists of two small Python components:

1. **Auto-Sync Daemon** (`autosync/`) – runs on each end-user node.  
   • Downloads new content referenced in a manifest via the `webtorrent-cli` binary.  
   • Avoids duplicate downloads, verifies file hashes when provided.  
   • Triggers a Jellyfin library rescan after new files arrive.  
   • Runs on a configurable interval (or once-off for testing).

2. **Manifest Server** (`manifest_server/`) – a lightweight Flask application for power users / curators.  
   • Serves JSON manifest files at `/manifest/<group>.json`.  
   • Allows manifests to be updated via `POST` requests.  
   • Can be fronted by any web server or published as a Docker image.

Both pieces are intentionally simple so that non-technical users can deploy them on Raspberry Pi, Intel NUC, or any small server.

---

## Repository layout

```
.
├── autosync/                # client-side sync daemon
│   ├── __init__.py
│   └── daemon.py
├── manifest_server/         # curator API
│   ├── __init__.py
│   └── app.py
├── manifests/               # example / runtime manifest files (git-ignored)
├── requirements.txt         # Python dependencies
├── .env.example             # sample configuration
└── README.md
```

## Prerequisites

1. **Python** 3.9 or newer
2. **webtorrent-cli** on any machine that seeds or downloads. Two options:  
   • **Node build (recommended)** – fast hashing & JSON output:
   ```bash
   npm install -g webtorrent-cli
   ```
   • **Go build (apt package)** – available on Debian/Ubuntu (`sudo apt install webtorrent`). Works but hashes large files slower and lacks `--json` support.
3. **Jellyfin** running on the same host as the Auto-Sync daemon
4. **ffmpeg** – dependency of Jellyfin
5. **Node.js** only if you choose the Node `webtorrent-cli` build.

### Debian / Ubuntu quick install

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm ffmpeg
sudo npm install -g webtorrent-cli
```

---

## Getting started (developer mode)

```bash
# clone & create virtualenv
git clone https://github.com/youruser/jellyfin_sync.git
cd jellyfin_sync
python3 -m venv .venv
source .venv/bin/activate

# install Python deps
pip install -r requirements.txt

# copy env template and adjust values
cp .env.example .env

# run a single sync cycle (simulate cron)
python -m autosync.daemon --once

# start the manifest server on localhost:5000
python -m manifest_server.app
```

Visit `http://localhost:5000` to verify the Manifest Server is running.  
Key endpoints:

- `GET /` – health check
- `GET /manifest/<group>.json` – fetch manifest
- `POST /seed` – seed a local file/dir & auto-update manifest (see below)
- `GET /seeds` – list active/pending seeds

When the manifest changes, Auto-Sync daemons will pick it up on their next cycle.

---

## Running continuously with systemd

Create `/etc/systemd/system/autosync.service`:

```ini
[Unit]
Description=Decentralized Media Auto-Sync Daemon
After=network.target

[Service]
User=media
Group=media
WorkingDirectory=/opt/jellyfin_sync
EnvironmentFile=/opt/jellyfin_sync/.env
ExecStart=/opt/jellyfin_sync/.venv/bin/python -m autosync.daemon
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable & start:

```bash
sudo systemctl enable autosync.service
sudo systemctl start autosync.service
```

---

## Manifest JSON format

```json
{
  "group": "family",
  "items": [
    {
      "title": "Spirited Away (2001)",
      "torrent": "magnet:?xt=urn:btih:<INFO_HASH>",
      "path": "Spirited Away (2001)/Spirited Away.mkv",
      "sha256": "<OPTIONAL_FILE_HASH>"
    }
  ]
}
```

- `torrent` – magnet URI or a .torrent URL.
- `path` – relative location inside `DOWNLOAD_DIR` where the file/folder will end up.
- `sha256` – optional; if present the daemon verifies file integrity.

---

## Adding content & seeding (all inside the Manifest Server)

1. Copy or move the file(s) you want to share onto the curator node.
2. Start (or keep running) the Manifest Server:

```bash
python -m manifest_server.app --host 0.0.0.0
```

3. Seed and add to a manifest with a single HTTP call:

```bash
curl -X POST http://<CURATOR_IP>:5000/seed \
     -H "Content-Type: application/json" \
     -d '{
           "path": "/home/user/Movies/YourClip.mp4",
           "group": "family",
           "dest_path": "YourClip/YourClip.mp4",
           "title": "Your Clip (2023)"
         }'
```

The server will:
• Spawn `webtorrent seed` in the background and keep it alive.  
• Return the `magnet:` URI used.  
• Automatically append a new item to `manifests/family.json` (creating the file if needed).

4. Laptops / Pi boxes running the Auto-Sync daemon will pick up the new item on their next poll and start downloading.

---

## Client configuration

Each downloader needs to know where its manifest lives. Edit `.env` on the client:

```ini
# .env on client
MANIFEST_URL=http://<CURATOR_IP>:5000/manifest/family.json
GROUP=family
DOWNLOAD_DIR=~/Videos/synced

# (optional) trigger Jellyfin rescan after download
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=<API_KEY>
```

Run once to test:

```bash
python -m autosync.daemon --once
```

Then run continuously (systemd or screen) – new content will appear automatically.

---

## Contribution guidelines

- Keep files ≤ 300 lines; factor out helpers when needed.
- Run linters before pushing:

```bash
pip install ruff black
ruff check .
black .
```

---

## License

MIT
