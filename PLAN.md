# flickrfinder — Implementation Plan

A local macOS app to search your Flickr photos by EXIF and other metadata. Web UI + REST API + CLI, backed by a local SQLite database synced from Flickr in the background.

## Goals

1. Search any EXIF/metadata field Flickr exposes (focal length, exposure, ISO, aperture, camera, lens, dates, tags, sets, etc.).
2. Stylish, responsive web UI with faceted search and result thumbnails.
3. Same capabilities via REST API and CLI.
4. Local SQLite database that mirrors all metadata for the user's library.
5. Background sync, resumable and rate-limited.
6. On-demand full-size original download, cached to disk.
7. Refresh single photos, lists, or the entire library.

## Non-goals (for now)

- Multi-user / multi-account.
- Editing Flickr data from the app.
- Cloud deployment (this is a local app, binds to 127.0.0.1).
- Full-text OCR or image-content search.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  React + Vite + Tailwind + shadcn/ui            │  Web UI
│  (built static, served by FastAPI)              │
└─────────────────────────────────────────────────┘
                       │ HTTP
┌─────────────────────────────────────────────────┐
│  FastAPI                                        │  REST API
│  /api/photos, /api/search, /api/sync, ...       │
└─────────────────────────────────────────────────┘
                       │
┌──────────────┬──────────────┬───────────────────┐
│  core/       │  worker/     │  cli/             │
│  Flickr      │  APScheduler │  Typer            │
│  client,     │  background  │  (talks to DB     │
│  models,     │  sync jobs   │   directly + to   │
│  search,     │              │   shared core)    │
│  DB layer    │              │                   │
└──────────────┴──────────────┴───────────────────┘
                       │
              ┌────────┴────────┐
              │  SQLite (data/) │
              │  + originals/   │
              └─────────────────┘
```

One process runs FastAPI + the APScheduler worker (background tasks via `asyncio`). The CLI is a separate entry point that imports `core/` and reads/writes the same database directly — no HTTP round-trip required for local commands.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Language | Python 3.11+ | One language for API, CLI, worker |
| API | FastAPI | Async, OpenAPI auto-docs, fast |
| CLI | Typer | Same author as FastAPI, ergonomic |
| DB | SQLite + SQLAlchemy 2.x | Local, zero-ops, full SQL |
| Migrations | Alembic | Schema evolution |
| Flickr client | `flickrapi` | Mature, handles OAuth 1.0a |
| Background jobs | APScheduler (in-process) | No extra services |
| Secret storage | `keyring` (macOS Keychain) | OAuth token never in plaintext |
| Env loading | `python-dotenv` | `.env` for API key/secret |
| Rate limiting | Token bucket (in-house) | Respect Flickr's 3,600/hr limit |
| FE | React 19 + Vite + Tailwind + shadcn/ui + TanStack Query | Modern, responsive, fast |
| Packaging | `uv` | Fast deps; `flickrfinder` console script |
| Tests | pytest + httpx | API + unit |

## Data model

```
photos
  id (Flickr photo id, PK)
  owner_nsid
  title
  description
  taken_at            -- from Flickr (when shutter fired)
  uploaded_at
  last_updated        -- Flickr's lastupdate
  is_public
  is_friend
  is_family
  url_sq, url_t, url_s, url_m, url_l, url_o   -- common sizes (lazy-filled)
  width_o, height_o
  exif_synced_at      -- when we last pulled getExif
  info_synced_at      -- when we last pulled getInfo
  sync_status         -- pending / ok / error
  sync_error

exif
  photo_id  FK photos.id
  tagspace          -- IFD0, EXIF, etc.
  tag               -- e.g. FocalLength, ExposureTime, ISO, Aperture, Make, Model, LensModel
  label             -- Flickr's human label
  raw               -- raw value string from Flickr
  clean             -- normalized (numeric where possible)
  PRIMARY KEY (photo_id, tagspace, tag)

  index (tag, clean) for fast facet queries

tags
  photo_id, tag, raw, machine_tag

sets       -- albums
  id, title, description
photo_sets
  photo_id, set_id

downloads
  photo_id, size, path, bytes, downloaded_at, source_url
  PRIMARY KEY (photo_id, size)

sync_jobs
  id, kind (full | photo_list | single), status, started_at, finished_at,
  total, done, error_count, last_error
  -- one row per sync invocation, for UI progress

sync_queue
  photo_id, kind (info | exif | sizes), attempts, last_error, enqueued_at
  -- per-photo work units; lets us resume a half-finished sync

settings
  key, value
  -- e.g. last_full_sync_at, oauth_nsid, schema_version
```

### Why one row per EXIF tag?

Flickr exposes wildly varying EXIF tag sets per photo. A wide-column schema would mean nullable everything and frequent migrations. Tall storage (`(photo_id, tag)`) makes facet queries (`WHERE tag='FocalLength' AND clean BETWEEN 20 AND 35`) cheap and indexable, and never needs a migration when a new lens/camera shows up.

### Cleaning EXIF values

Flickr returns EXIF as strings. We store both `raw` and a normalized `clean`:

| Tag | Raw | Clean |
|---|---|---|
| FocalLength | `"23 mm"` | `23.0` |
| ExposureTime | `"1/250"` | `0.004` (seconds) |
| FNumber | `"f/2.8"` | `2.8` |
| ISO | `"400"` | `400` |
| Make | `"FUJIFILM"` | `"FUJIFILM"` |

Cleaners live in `core/exif/normalize.py`, one per tag, easy to extend.

## Flickr API usage

| Endpoint | Used for |
|---|---|
| `flickr.auth.oauth.*` | One-time OAuth login |
| `flickr.test.login` | `whoami` |
| `flickr.people.getPhotos` | Paginated walk of owner's library; supports `min_upload_date` for incremental sync; ask for extras (`date_upload`, `date_taken`, `last_update`, `tags`, `url_sq,url_t,url_s,url_m,url_l,url_o`, `o_dims`) to cut down on `getInfo` calls |
| `flickr.photos.getInfo` | Fields not in `getPhotos` extras (description, sets, full visibility flags) |
| `flickr.photos.getExif` | EXIF |
| `flickr.photos.getSizes` | URL for "Original" when downloading full-size |
| `flickr.photosets.getList` | Album list |

### Rate limits & sync math

- Flickr's polite limit is ~3,600 calls/hour. The token bucket caps us at 1 call/sec (sustained).
- For ~9,700 photos:
  - `getPhotos` with all extras paginated 500/page = ~20 calls.
  - `getExif` is one call per photo = 9,700 calls = ~2h 42m.
  - `getInfo` only when extras don't cover what we need; aim for ~0 most of the time.
- Sync is resumable: every photo's `sync_queue` row persists until done, so a crash/restart picks up where it left off.
- Incremental refresh uses `min_upload_date = max(uploaded_at)` and `lastupdate` watermarks for changed photos.

## REST API (sketch)

```
GET  /api/health
GET  /api/me
GET  /api/photos                  ?cursor=&limit=
GET  /api/photos/{id}
GET  /api/search                  faceted query
GET  /api/facets                  available filter values + counts
POST /api/sync/full
POST /api/sync/photos             body: { ids: [...] }
GET  /api/sync/jobs
GET  /api/sync/jobs/{id}
POST /api/downloads/{photo_id}    body: { size: "Original" }
GET  /api/downloads/{photo_id}
GET  /api/files/{photo_id}        serves the downloaded original
```

Search query parameters mirror EXIF tags:
`?camera=X-T5&lens=XF23&focal_min=20&focal_max=35&iso_max=800&aperture_max=2.8&taken_after=2024-01-01&tag=portrait&set=2025-summer`

## CLI surface

```
flickrfinder auth                      # one-time OAuth
flickrfinder whoami                    # confirm token
flickrfinder sync                      # full sync (resumable)
flickrfinder sync --since 7d           # incremental
flickrfinder sync --ids 1,2,3          # specific photos
flickrfinder search [filters]          # query
flickrfinder download <photo_id>       # fetch original
flickrfinder serve [--port 8765]       # start web UI + API
flickrfinder db migrate                # run migrations
flickrfinder db stats                  # row counts, sync state, disk use
```

## Phased build

Each phase ends in something you can run and verify.

### Phase 1 — Skeleton, OAuth, smoke test

1. Project layout, `pyproject.toml`, `uv` env, `.env` loading, `.gitignore`.
2. `flickrfinder auth` → OAuth 1.0a flow, token in Keychain.
3. `flickrfinder whoami` → calls `flickr.test.login`, prints user + photo count.
4. Smoke test: pull metadata + EXIF for 5 photos, dump to stdout.

**Verify:** `auth` works, `whoami` prints your username, smoke test prints real EXIF.

### Phase 2 — DB + full sync engine

1. SQLAlchemy models, Alembic migration for the schema above.
2. `core/sync/` — paginated `getPhotos`, enqueue work, run workers with token-bucket rate limit.
3. EXIF normalizers for the common tags.
4. `flickrfinder sync` (full) + `flickrfinder sync --ids …`.
5. Resume-on-restart logic.

**Verify:** sync ~9,700 photos end-to-end; restart mid-sync resumes; `db stats` shows expected row counts.

### Phase 3 — Search API + CLI

1. FastAPI app skeleton, `/api/health`, `/api/me`, `/api/photos`, `/api/search`, `/api/facets`.
2. Search query builder over the `exif` table with normalized values.
3. `flickrfinder search` mirrors API params.
4. pytest suite over a fixture DB.

**Verify:** searches by focal length / ISO / camera return same results via CLI and API; tests pass.

### Phase 4 — Web UI

1. Vite + React + Tailwind + shadcn/ui scaffold under `web/`.
2. TanStack Query client; faceted search page with thumbnails.
3. Filters: camera, lens, focal range, ISO range, aperture range, shutter range, date range, tags, sets.
4. Result grid with infinite scroll; photo detail page shows all EXIF.
5. `flickrfinder serve` builds + serves the SPA.

**Verify:** open http://127.0.0.1:8765, search visually matches CLI results, responsive at 375px / 768px / 1440px widths.

### Phase 5 — Refresh + full-size downloads

1. `POST /api/sync/photos` and `POST /api/sync/full` wired to UI buttons.
2. Sync progress polled via `/api/sync/jobs/{id}` and shown in UI.
3. "Download original" action → `getSizes` → fetch → store under `data/originals/`.
4. `GET /api/files/{photo_id}` serves downloaded originals.
5. `flickrfinder download <photo_id>` CLI.

**Verify:** refresh-by-id and refresh-all both visibly progress; download writes file + DB row; second download is a no-op.

### Phase 6 — Polish

1. Scheduled daily incremental sync (APScheduler cron).
2. Sync errors surfaced in the UI with retry button.
3. Disk-usage view (`data/originals/` size).
4. Packaging: `pipx install` or `uv tool install` so `flickrfinder` is on PATH globally.

## Security & privacy notes

- API key + secret live in `.env` (gitignored). `.env.example` is checked in.
- OAuth access token lives in macOS Keychain via `keyring`.
- Server binds to `127.0.0.1` only.
- No telemetry, no external network calls except to Flickr.

## Repo layout (target)

```
flickrfinder/
├── pyproject.toml
├── uv.lock
├── README.md
├── PLAN.md
├── CLAUDE.md
├── .env.example
├── .gitignore
├── alembic.ini
├── migrations/
├── src/flickrfinder/
│   ├── __init__.py
│   ├── config.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   └── routes/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── flickr_client.py
│   │   ├── auth.py
│   │   ├── rate_limit.py
│   │   ├── exif/
│   │   └── search.py
│   ├── worker/
│   │   └── sync.py
│   └── web/                # built React SPA goes here
├── web/                    # React source
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
├── tests/
└── data/                   # gitignored — SQLite + originals
```

## Open risks / things to watch

- **OAuth complexity.** `flickrapi` handles it but the first-run UX needs care. Verify in Phase 1.
- **Inconsistent EXIF tags.** Different cameras emit different fields; normalizers must tolerate missing tags gracefully.
- **Disk usage.** 9,700 mostly-large originals could easily exceed 100 GB. UI must show usage and let the user delete cached originals.
- **Flickr rate limiting under bursty load.** Token bucket handles steady state; we also back off on HTTP 429.
- **API key rotation.** The dev key was exposed in chat and will be rotated; `.env` makes swapping it a one-line change.
