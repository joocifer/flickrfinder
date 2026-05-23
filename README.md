# flickrfinder

Search your Flickr photos by EXIF data — focal length, exposure, ISO, aperture, camera, lens, and anything else Flickr exposes.

Runs locally on macOS. Pulls metadata in the background into a SQLite database, then lets you search via:

- **Web UI** — stylish, responsive, faceted search
- **REST API** — same data programmatically
- **CLI** — same searches from your terminal

Full-size originals are only downloaded when you ask for them, then cached on disk.

## Status

Early development. See [PLAN.md](./PLAN.md) for the phased build.

## Requirements

- macOS
- Python 3.11+
- A Flickr API key + secret — get one at https://www.flickr.com/services/apps/create/

## Quick start

> **First time installing?** Follow the step-by-step **[INSTALL.md](./INSTALL.md)** — it covers prerequisites, the Flickr API key, and every command in plain language. The short version below assumes you've done that or know the drill.

```bash
# Clone
git clone <your-repo-url>
cd flickrfinder

# Set up env
cp .env.example .env
# edit .env and paste your Flickr API key + secret

# Install
uv sync   # or: pip install -e .

# One-time OAuth login (opens your browser)
flickrfinder auth

# Confirm it works
flickrfinder whoami

# Pull all your photos' metadata + EXIF into the local DB
flickrfinder sync

# Search
flickrfinder search --camera "X-T5" --focal-length 23 --iso-max 800

# Download the original-size image for one photo
flickrfinder download 54757642594

# Start the web UI + API on http://127.0.0.1:8765
flickrfinder serve
```

## Searching

The CLI mirrors the REST API. Typed flags cover the common cases; an `--exif` escape hatch lets you query any field Flickr exposes.

```bash
# Camera, lens, focal range, ISO ceiling
flickrfinder search --camera "X-T5" --focal-min 23 --focal-max 35 --iso-max 800

# Aperture and shutter ranges
flickrfinder search --aperture-max 2.8 --shutter-faster-than 0.005

# Tags (repeatable; ANDed)
flickrfinder search --tag portrait --tag studio

# Date range
flickrfinder search --taken-after 2024-01-01 --taken-before 2024-12-31

# Visibility
flickrfinder search --public      # or --private

# Anything else via the escape hatch
flickrfinder search --exif "WhiteBalance=Auto"
flickrfinder search --exif "FocalLengthIn35mmFormat>=35"
flickrfinder search --exif "Model~=X-T"

# Output formats
flickrfinder search --camera nikon --format ids        # one id per line, pipe-friendly
flickrfinder search --camera nikon --format json       # full JSON
```

Operators for `--exif`:
- `=`, `!=`, `~=` (case-insensitive substring) — string match
- `<`, `<=`, `>`, `>=` — numeric (require parseable numbers in EXIF)

### What's actually searchable in your library?

```bash
flickrfinder facets --top 10
```

Lists your most common cameras, lenses, tags, and the EXIF fields actually populated in your DB. Anything that shows up under "EXIF fields present" is usable with `--exif`.

Full flag reference: `flickrfinder search --help`.

## Web UI

The React SPA is built into the Python package and served by FastAPI:

```bash
# One-time build
cd web && bun install && bun run build && cd ..

# Run the API + UI on localhost
uv run flickrfinder serve
# open http://127.0.0.1:8765
```

By default the standalone `flickrfinder serve` binds to `127.0.0.1`. To expose it on your LAN, set `FLICKRFINDER_HOST=0.0.0.0` in `.env` or use the launchd service described below.

Features: faceted filter sidebar (camera/lens/focal/aperture/ISO/shutter/dates/tags/EXIF), responsive thumbnail grid, photo detail modal with full EXIF, sort by any indexed field, URL-synced filter state (refresh-safe, bookmarkable searches).

### Web UI development

```bash
# Terminal 1 — API only
uv run flickrfinder serve

# Terminal 2 — Vite dev server with /api proxy
cd web && bun run dev
# open http://localhost:5173
```

## REST API

`flickrfinder serve` starts a FastAPI app on `http://127.0.0.1:8765`:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health probe |
| `GET /api/me` | Owner NSID + total photos in your local DB |
| `GET /api/photos/{id}` | Single photo with full EXIF map |
| `GET /api/search` | Same filter parameters as the CLI |
| `GET /api/facets?top=N` | Top cameras/lenses/tags/EXIF fields |
| `POST /api/sync/full` | Start a full background sync; returns the job |
| `POST /api/sync/photos` | Force-refresh metadata for specific ids (body `{"ids":[...]}`) |
| `GET /api/sync/jobs` | List recent sync jobs |
| `GET /api/sync/jobs/{id}` | Poll a sync job for progress |
| `POST /api/downloads/{id}` | Fetch the original-size image and cache it |
| `GET /api/downloads/{id}` | Metadata about a cached original |
| `GET /api/files/{id}` | Serve the cached original-size image bytes |
| `GET /docs` | Auto-generated OpenAPI/Swagger UI |

## How it works

1. `flickrfinder auth` does a one-time Flickr OAuth 1.0a flow. The access token is cached by `flickrapi` under `~/.flickr/<api_key>/oauth-tokens.sqlite`.
2. `flickrfinder sync` walks your entire Flickr library via `flickr.people.getPhotos`, then per-photo calls `flickr.photos.getInfo` and `flickr.photos.getExif`. All metadata goes into a local SQLite database. The sync is resumable and rate-limited.
3. `flickrfinder serve` starts a FastAPI server that exposes the data as a REST API and serves the React web UI.
4. Searches run entirely against the local database — fast, offline-capable.
5. When you click "Download original" in the UI (or run `flickrfinder download <photo_id>`), the full-size image is fetched via `flickr.photos.getSizes` and stored under `data/originals/`.

## Run as a background service (macOS launchd)

To keep the server up across reboots and expose it on your LAN:

```bash
# After uv sync and bun build, install + start the LaunchAgent
./deploy/install-launchd.sh
```

That writes `~/Library/LaunchAgents/com.flickrfinder.server.plist`, loads it into launchd, and starts the server bound to `0.0.0.0:8765`. It will be reachable at:

- `http://127.0.0.1:8765` (this Mac)
- `http://<your-mac>.local:8765` (mDNS — from any device on the LAN)
- `http://<your-mac-LAN-ip>:8765`

macOS will prompt you to allow incoming connections the first time.

**No authentication.** The app exposes search, sync, and original-image download to any device on your LAN. If you need auth, ask — adding HTTP basic-auth is a small change.

Service control:

```bash
# Status
launchctl print gui/$(id -u)/com.flickrfinder.server

# Stop
launchctl bootout gui/$(id -u)/com.flickrfinder.server

# Re-start (or re-install after editing the plist template)
./deploy/install-launchd.sh

# Tail the log
tail -f data/flickrfinder.log
```

The plist template is at `deploy/com.flickrfinder.server.plist`; the install script substitutes the repo path and writes the final plist into `~/Library/LaunchAgents/`.

## Data location

- Metadata DB: `data/flickrfinder.db`
- Downloaded originals: `data/originals/`
- Service log: `data/flickrfinder.log`
- OAuth token: `~/.flickr/<api_key>/oauth-tokens.sqlite` (managed by `flickrapi`)

## License

MIT
