from __future__ import annotations

import contextlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from flickrfinder import __version__
from flickrfinder.config import load_config
from flickrfinder.core import downloads as downloads_engine
from flickrfinder.core import facets as facets_engine
from flickrfinder.core import search as search_engine
from flickrfinder.core import sync as sync_engine
from flickrfinder.core.db import init_db, session_factory
from flickrfinder.core.models import Download, Exif, Photo, SyncJob

app = FastAPI(title="flickrfinder", version=__version__)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.on_event("startup")
def _on_startup() -> None:
    cfg = load_config()
    sync_engine.reap_zombie_jobs(cfg)


def get_session() -> Session:
    cfg = load_config()
    init_db(cfg)
    sf = session_factory(cfg)
    s = sf()
    try:
        yield s
    finally:
        s.close()


SessionDep = Annotated[Session, Depends(get_session)]


class PhotoOut(BaseModel):
    id: str
    title: str
    taken_at: datetime | None
    uploaded_at: datetime | None
    url_t: str | None
    url_m: str | None
    url_l: str | None
    is_public: bool
    exif: dict[str, str]


class SearchOut(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[PhotoOut]


class FacetValueOut(BaseModel):
    value: str
    count: int


class FacetsOut(BaseModel):
    cameras: list[FacetValueOut]
    lenses: list[FacetValueOut]
    tags: list[FacetValueOut]
    exif_tags: list[FacetValueOut]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/me")
def me(s: SessionDep) -> dict[str, str | int]:
    cfg = load_config()
    from sqlalchemy import func, select

    photos = s.scalar(select(func.count()).select_from(Photo)) or 0
    nsid = s.scalar(select(Photo.owner_nsid).limit(1)) or ""
    return {"data_dir": str(cfg.data_dir), "owner_nsid": nsid, "photos": photos}


@app.get("/api/photos/{photo_id}", response_model=PhotoOut)
def get_photo(photo_id: str, s: SessionDep) -> PhotoOut:
    photo = s.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="not found")
    # Fetch a richer EXIF map for the detail view
    from sqlalchemy import select

    from flickrfinder.core.models import Exif

    exif_rows = s.execute(select(Exif).where(Exif.photo_id == photo_id)).scalars().all()
    exif = {e.tag: e.raw for e in exif_rows}
    return PhotoOut(
        id=photo.id,
        title=photo.title,
        taken_at=photo.taken_at,
        uploaded_at=photo.uploaded_at,
        url_t=photo.url_t,
        url_m=photo.url_m,
        url_l=photo.url_l,
        is_public=photo.is_public,
        exif=exif,
    )


def search_filter(
    camera: str | None = None,
    make: str | None = None,
    model: str | None = None,
    lens: str | None = None,
    focal_length: float | None = None,
    focal_min: float | None = None,
    focal_max: float | None = None,
    aperture: float | None = None,
    aperture_min: float | None = None,
    aperture_max: float | None = None,
    shutter: float | None = None,
    shutter_min: float | None = None,
    shutter_max: float | None = None,
    shutter_faster_than: float | None = None,
    shutter_slower_than: float | None = None,
    iso: int | None = None,
    iso_min: int | None = None,
    iso_max: int | None = None,
    taken_after: datetime | None = None,
    taken_before: datetime | None = None,
    uploaded_after: datetime | None = None,
    uploaded_before: datetime | None = None,
    tag: list[str] = Query(default_factory=list),
    public: bool | None = None,
    exif: list[str] = Query(default_factory=list),
    limit: int = 50,
    offset: int = 0,
    order: Literal["taken", "uploaded", "focal", "iso", "aperture", "shutter"] = "taken",
    direction: Literal["asc", "desc"] = "desc",
) -> search_engine.Filter:
    """FastAPI dependency that builds a Filter from query params.

    Shared by /api/search and /api/exif-values so both endpoints accept
    the same filter surface.
    """
    try:
        exif_exprs = [search_engine.ExifExpr.parse(e) for e in exif]
    except search_engine.FilterError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return search_engine.Filter(
        camera=camera,
        make=make,
        model=model,
        lens=lens,
        focal_length=focal_length,
        focal_min=focal_min,
        focal_max=focal_max,
        aperture=aperture,
        aperture_min=aperture_min,
        aperture_max=aperture_max,
        shutter=shutter,
        shutter_min=shutter_min,
        shutter_max=shutter_max,
        shutter_faster_than=shutter_faster_than,
        shutter_slower_than=shutter_slower_than,
        iso=iso,
        iso_min=iso_min,
        iso_max=iso_max,
        taken_after=taken_after,
        taken_before=taken_before,
        uploaded_after=uploaded_after,
        uploaded_before=uploaded_before,
        tags=tag,
        public=public,
        exif=exif_exprs,
        limit=limit,
        offset=offset,
        sort=order,
        direction=direction,
    )


FilterDep = Annotated[search_engine.Filter, Depends(search_filter)]


@app.get("/api/search", response_model=SearchOut)
def api_search(s: SessionDep, f: FilterDep) -> SearchOut:
    try:
        results, total = search_engine.search(s, f)
    except search_engine.FilterError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return SearchOut(
        total=total,
        limit=f.limit,
        offset=f.offset,
        results=[
            PhotoOut(
                id=r.id,
                title=r.title,
                taken_at=r.taken_at,
                uploaded_at=r.uploaded_at,
                url_t=r.url_t,
                url_m=r.url_m,
                url_l=None,
                is_public=r.is_public,
                exif=r.exif,
            )
            for r in results
        ],
    )


def _to_facet_out(fvs: list[facets_engine.FacetValue]) -> list[FacetValueOut]:
    return [FacetValueOut(value=v.value, count=v.count) for v in fvs]


@app.get("/api/facets", response_model=FacetsOut)
def api_facets(s: SessionDep, top: int = 25) -> FacetsOut:
    result = facets_engine.compute_facets(s, top=top)
    return FacetsOut(
        cameras=_to_facet_out(result.cameras),
        lenses=_to_facet_out(result.lenses),
        tags=_to_facet_out(result.tags),
        exif_tags=_to_facet_out(result.exif_tags),
    )


class ExifTagOut(BaseModel):
    tag: str
    count: int


@app.get("/api/exif-tags", response_model=list[ExifTagOut])
def api_exif_tags(s: SessionDep) -> list[ExifTagOut]:
    """Every distinct EXIF tag in the local DB with its photo count."""
    rows = s.execute(
        select(Exif.tag, func.count(func.distinct(Exif.photo_id)))
        .group_by(Exif.tag)
        .order_by(desc(func.count(func.distinct(Exif.photo_id))))
    ).all()
    return [ExifTagOut(tag=t, count=c) for t, c in rows]


@app.get("/api/exif-values", response_model=list[FacetValueOut])
def api_exif_values(
    s: SessionDep,
    f: FilterDep,
    key: str,
    limit: int = 200,
) -> list[FacetValueOut]:
    """Group distinct values for one EXIF tag (the `key` query param) and count
    photos per value. Honors all the standard search-filter query params, so the
    result is a drill-down over the currently-filtered subset of the library.

    Note: the EXIF tag is passed as `key`, not `tag`, because `tag` already
    means "Flickr tag" in the shared filter surface.
    """
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    rows = facets_engine.exif_value_counts(s, key, filter=f, limit=limit)
    return _to_facet_out(rows)


# ---------------------------------------------------------------------------
# Sync jobs


class SyncJobOut(BaseModel):
    id: int
    kind: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total: int
    done: int
    error_count: int
    last_error: str | None


class SyncIdsIn(BaseModel):
    ids: list[str]


def _job_to_out(j: SyncJob) -> SyncJobOut:
    return SyncJobOut(
        id=j.id,
        kind=j.kind,
        status=j.status,
        started_at=j.started_at,
        finished_at=j.finished_at,
        total=j.total,
        done=j.done,
        error_count=j.error_count,
        last_error=j.last_error,
    )


def _start_background_sync(kind: str, target, **kwargs) -> int:
    """Pre-create the SyncJob row, then run `target(job_id=..., **kwargs)` in a thread."""
    cfg = load_config()
    running = sync_engine.get_running_job_id(cfg)
    if running is not None:
        return running
    job_id = sync_engine.start_job_row(cfg, kind)

    def _runner() -> None:
        # sync_full/sync_ids already mark the job as 'error' before re-raising.
        with contextlib.suppress(Exception):
            target(cfg, job_id=job_id, **kwargs)

    threading.Thread(target=_runner, daemon=True, name=f"sync-{job_id}").start()
    return job_id


@app.post("/api/sync/full", response_model=SyncJobOut)
def api_sync_full(s: SessionDep) -> SyncJobOut:
    job_id = _start_background_sync("full", sync_engine.sync_full)
    job = s.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="job vanished")
    return _job_to_out(job)


@app.post("/api/sync/photos", response_model=SyncJobOut)
def api_sync_photos(body: SyncIdsIn, s: SessionDep) -> SyncJobOut:
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids[] is required")
    job_id = _start_background_sync("ids", sync_engine.sync_ids, photo_ids=body.ids)
    job = s.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="job vanished")
    return _job_to_out(job)


@app.get("/api/sync/jobs", response_model=list[SyncJobOut])
def api_sync_jobs(s: SessionDep, limit: int = 25) -> list[SyncJobOut]:
    rows = (
        s.execute(select(SyncJob).order_by(desc(SyncJob.started_at)).limit(limit)).scalars().all()
    )
    return [_job_to_out(j) for j in rows]


@app.get("/api/sync/jobs/{job_id}", response_model=SyncJobOut)
def api_sync_job(job_id: int, s: SessionDep) -> SyncJobOut:
    job = s.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_to_out(job)


# ---------------------------------------------------------------------------
# Downloads


class DownloadOut(BaseModel):
    photo_id: str
    size: str
    path: str
    bytes: int
    source_url: str
    downloaded_at: datetime


def _dl_to_out(d: Download) -> DownloadOut:
    return DownloadOut(
        photo_id=d.photo_id,
        size=d.size,
        path=d.path,
        bytes=d.bytes,
        source_url=d.source_url,
        downloaded_at=d.downloaded_at,
    )


@app.get("/api/downloads/{photo_id}", response_model=DownloadOut)
def api_get_download(photo_id: str, s: SessionDep) -> DownloadOut:
    dl = downloads_engine.get_download(s, photo_id)
    if dl is None:
        raise HTTPException(status_code=404, detail="not downloaded")
    if not Path(dl.path).exists():
        raise HTTPException(status_code=410, detail="file missing on disk")
    return _dl_to_out(dl)


@app.post("/api/downloads/{photo_id}", response_model=DownloadOut)
def api_post_download(photo_id: str, force: bool = False) -> DownloadOut:
    cfg = load_config()
    try:
        dl = downloads_engine.download_original(cfg, photo_id, force=force)
    except downloads_engine.DownloadError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return _dl_to_out(dl)


@app.get("/api/files/{photo_id}")
def api_file(photo_id: str, s: SessionDep) -> FileResponse:
    dl = downloads_engine.get_download(s, photo_id)
    if dl is None:
        raise HTTPException(status_code=404, detail="not downloaded")
    path = Path(dl.path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="file missing on disk")
    return FileResponse(path, filename=path.name)


_INDEX_HTML = _WEB_DIR / "index.html"
if _INDEX_HTML.exists():
    app.mount("/assets", StaticFiles(directory=_WEB_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "docs" or full_path == "openapi.json":
            raise HTTPException(status_code=404)
        candidate = _WEB_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX_HTML)
else:

    @app.get("/", include_in_schema=False)
    def spa_missing() -> dict[str, str]:
        return {
            "status": "no_spa",
            "message": (
                "Web UI not built. Run `cd web && bun install && bun run build` "
                "to enable the SPA at /."
            ),
        }
