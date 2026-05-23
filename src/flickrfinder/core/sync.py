"""Two-phase sync from Flickr into the local DB.

Phase A: paginate flickr.people.getPhotos with extras → upsert photos +
         enqueue an EXIF work item per photo.
Phase B: drain the EXIF queue: getExif → normalize → store → mark done.

Re-running `sync` is idempotent — both phases use INSERT-OR-IGNORE/UPSERT
semantics, so an interrupted run resumes by simply running again.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import flickrapi
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from flickrfinder.config import Config
from flickrfinder.core import exif_normalize
from flickrfinder.core.db import init_db, session_scope
from flickrfinder.core.flickr_client import build_client
from flickrfinder.core.models import Exif, Photo, PhotoTag, SyncJob, SyncQueue

EXTRAS = ",".join(
    [
        "description",
        "date_upload",
        "date_taken",
        "last_update",
        "tags",
        "machine_tags",
        "o_dims",
        "views",
        "count_faves",
        "count_comments",
        "url_t",
        "url_m",
        "url_l",
        "url_o",
    ]
)

MAX_ATTEMPTS = 3


class RateLimiter:
    """Minimum interval between calls. 1.0s ≈ 3,600/hr — well under Flickr's limit."""

    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


def _parse_ts(value: str | int | None) -> datetime | None:
    """Parse a Flickr timestamp (unix int-as-string) into a datetime."""
    if value in (None, "", "0"):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (ValueError, TypeError):
        return None


def _parse_taken(value: str | None) -> datetime | None:
    """date_taken is 'YYYY-MM-DD HH:MM:SS' in the photographer's local time."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _photo_payload_from_extras(p: dict, owner_nsid: str) -> dict:
    return {
        "id": p["id"],
        "owner_nsid": owner_nsid,
        "title": p.get("title") or "",
        "description": (p.get("description") or {}).get("_content") or "",
        "taken_at": _parse_taken(p.get("datetaken")),
        "uploaded_at": _parse_ts(p.get("dateupload")),
        "last_updated": _parse_ts(p.get("lastupdate")),
        "is_public": bool(int(p.get("ispublic", 0))),
        "is_friend": bool(int(p.get("isfriend", 0))),
        "is_family": bool(int(p.get("isfamily", 0))),
        "url_t": p.get("url_t"),
        "url_m": p.get("url_m"),
        "url_l": p.get("url_l"),
        "url_o": p.get("url_o"),
        "width_o": int(p["width_o"]) if p.get("width_o") else None,
        "height_o": int(p["height_o"]) if p.get("height_o") else None,
        "views": int(p["views"]) if p.get("views") else None,
        "count_faves": int(p["count_faves"]) if p.get("count_faves") else None,
        "count_comments": int(p["count_comments"]) if p.get("count_comments") else None,
        "info_synced_at": datetime.now(tz=UTC),
    }


def _upsert_photo(s: Session, payload: dict) -> None:
    stmt = sqlite_insert(Photo).values(**payload)
    update_cols = {k: stmt.excluded[k] for k in payload if k != "id"}
    s.execute(stmt.on_conflict_do_update(index_elements=[Photo.id], set_=update_cols))


def _replace_photo_tags(s: Session, photo_id: str, tag_string: str) -> None:
    s.execute(delete(PhotoTag).where(PhotoTag.photo_id == photo_id))
    tags = [t for t in (tag_string or "").split() if t]
    if not tags:
        return
    s.execute(
        sqlite_insert(PhotoTag).values([{"photo_id": photo_id, "tag": t, "raw": t} for t in tags])
    )


def _enqueue_exif(s: Session, photo_id: str, *, force: bool = False) -> None:
    if not force:
        photo = s.get(Photo, photo_id)
        if photo is not None and photo.exif_synced_at is not None:
            return
    s.execute(
        sqlite_insert(SyncQueue)
        .values(
            photo_id=photo_id,
            kind="exif",
            attempts=0,
            enqueued_at=datetime.now(tz=UTC),
        )
        .on_conflict_do_nothing()
    )


def _store_exif(s: Session, photo_id: str, exif_rows: list[dict]) -> None:
    s.execute(delete(Exif).where(Exif.photo_id == photo_id))
    payload = []
    for e in exif_rows:
        tag = e.get("tag", "")
        raw = (e.get("raw") or {}).get("_content", "")
        clean_num, clean_str = exif_normalize.normalize(tag, raw)
        payload.append(
            {
                "photo_id": photo_id,
                "tagspace": e.get("tagspace", ""),
                "tag": tag,
                "label": e.get("label", ""),
                "raw": raw,
                "clean_num": clean_num,
                "clean_str": clean_str,
            }
        )
    if payload:
        s.execute(sqlite_insert(Exif).values(payload))


def _start_job(cfg: Config, kind: str) -> int:
    with session_scope(cfg) as s:
        job = SyncJob(
            kind=kind,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        s.add(job)
        s.flush()
        return job.id


def _finish_job(cfg: Config, job_id: int, *, status: str, last_error: str | None = None) -> None:
    with session_scope(cfg) as s:
        job = s.get(SyncJob, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = datetime.now(tz=UTC)
        if last_error:
            job.last_error = last_error


def sync_full(
    cfg: Config,
    *,
    max_photos: int | None = None,
    page_size: int = 500,
    console: Console | None = None,
    job_id: int | None = None,
) -> int:
    """Run (or resume) a full sync. Returns the SyncJob row id."""
    console = console or Console()
    init_db(cfg)
    flickr = build_client(cfg)
    nsid = flickr.test.login()["user"]["id"]

    if job_id is None:
        job_id = _start_job(cfg, "full")
    limiter = RateLimiter()
    try:
        _phase_a_photos(cfg, flickr, nsid, max_photos, page_size, limiter, console)
        _phase_b_exif(cfg, flickr, job_id, limiter, console)
        _finish_job(cfg, job_id, status="ok")
    except KeyboardInterrupt:
        _finish_job(cfg, job_id, status="cancelled")
        console.print("[yellow]Sync cancelled; queue preserved — re-run to resume.[/yellow]")
        raise
    except Exception as e:
        _finish_job(cfg, job_id, status="error", last_error=str(e))
        raise
    return job_id


def _phase_a_photos(
    cfg: Config,
    flickr: flickrapi.FlickrAPI,
    nsid: str,
    max_photos: int | None,
    page_size: int,
    limiter: RateLimiter,
    console: Console,
) -> None:
    console.print("[bold]Phase A:[/bold] paginating your photo list...")
    page = 1
    total_seen = 0
    with Progress(
        TextColumn("[bold blue]getPhotos"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("getPhotos", total=None)
        while True:
            limiter.wait()
            resp = flickr.people.getPhotos(
                user_id=nsid,
                page=page,
                per_page=page_size,
                extras=EXTRAS,
            )["photos"]
            if page == 1:
                progress.update(task, total=int(resp.get("total", 0)))
            for p in resp.get("photo", []):
                with session_scope(cfg) as s:
                    _upsert_photo(s, _photo_payload_from_extras(p, owner_nsid=nsid))
                    _replace_photo_tags(s, p["id"], p.get("tags", ""))
                    _enqueue_exif(s, p["id"])
                total_seen += 1
                progress.update(task, advance=1)
                if max_photos is not None and total_seen >= max_photos:
                    return
            if page >= int(resp.get("pages", 1)):
                return
            page += 1


def _phase_b_exif(
    cfg: Config,
    flickr: flickrapi.FlickrAPI,
    job_id: int,
    limiter: RateLimiter,
    console: Console,
) -> None:
    with session_scope(cfg) as s:
        pending = (
            s.scalar(select(func.count()).select_from(SyncQueue).where(SyncQueue.kind == "exif"))
            or 0
        )
        job = s.get(SyncJob, job_id)
        if job is not None:
            job.total = pending

    if pending == 0:
        console.print("[green]No EXIF work pending.[/green]")
        return

    console.print(f"[bold]Phase B:[/bold] fetching EXIF for {pending} photos...")
    done = 0
    errors = 0
    with Progress(
        TextColumn("[bold blue]getExif"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("getExif", total=pending)
        while True:
            with session_scope(cfg) as s:
                row = s.execute(
                    select(SyncQueue)
                    .where(SyncQueue.kind == "exif")
                    .order_by(SyncQueue.enqueued_at)
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    break
                photo_id = row.photo_id
                attempts = row.attempts

            limiter.wait()
            try:
                exif_resp = flickr.photos.getExif(photo_id=photo_id)
                exif_rows = exif_resp.get("photo", {}).get("exif", [])
                with session_scope(cfg) as s:
                    _store_exif(s, photo_id, exif_rows)
                    photo = s.get(Photo, photo_id)
                    if photo is not None:
                        photo.exif_synced_at = datetime.now(tz=UTC)
                        photo.sync_status = "ok"
                        photo.sync_error = None
                    s.execute(
                        delete(SyncQueue).where(
                            SyncQueue.photo_id == photo_id, SyncQueue.kind == "exif"
                        )
                    )
                    job = s.get(SyncJob, job_id)
                    if job is not None:
                        job.done += 1
                done += 1
            except flickrapi.exceptions.FlickrError as e:
                errors += 1
                with session_scope(cfg) as s:
                    if attempts + 1 >= MAX_ATTEMPTS:
                        photo = s.get(Photo, photo_id)
                        if photo is not None:
                            photo.sync_status = "error"
                            photo.sync_error = str(e)
                        s.execute(
                            delete(SyncQueue).where(
                                SyncQueue.photo_id == photo_id, SyncQueue.kind == "exif"
                            )
                        )
                    else:
                        q = s.execute(
                            select(SyncQueue).where(
                                SyncQueue.photo_id == photo_id, SyncQueue.kind == "exif"
                            )
                        ).scalar_one()
                        q.attempts = attempts + 1
                        q.last_error = str(e)
                    job = s.get(SyncJob, job_id)
                    if job is not None:
                        job.error_count += 1
                        job.last_error = str(e)
            progress.update(task, advance=1)

    console.print(f"[green]Phase B done.[/green] ok={done} errors={errors}")


def sync_ids(
    cfg: Config,
    photo_ids: list[str],
    console: Console | None = None,
    *,
    job_id: int | None = None,
) -> int:
    """Force-refresh EXIF for a list of photo IDs. Returns the SyncJob row id."""
    console = console or Console()
    init_db(cfg)
    flickr = build_client(cfg)
    if job_id is None:
        job_id = _start_job(cfg, "ids")
    try:
        with session_scope(cfg) as s:
            for pid in photo_ids:
                _enqueue_exif(s, pid, force=True)
        _phase_b_exif(cfg, flickr, job_id, RateLimiter(), console)
        _finish_job(cfg, job_id, status="ok")
    except Exception as e:
        _finish_job(cfg, job_id, status="error", last_error=str(e))
        raise
    return job_id


def start_job_row(cfg: Config, kind: str) -> int:
    """Public wrapper so the API/worker can pre-create a SyncJob row."""
    init_db(cfg)
    return _start_job(cfg, kind)


def reap_zombie_jobs(cfg: Config) -> int:
    """Mark any 'running' jobs as 'cancelled' (called at server startup)."""
    from sqlalchemy import update

    init_db(cfg)
    with session_scope(cfg) as s:
        r = s.execute(
            update(SyncJob)
            .where(SyncJob.status == "running")
            .values(
                status="cancelled",
                finished_at=datetime.now(tz=UTC),
                last_error="server restarted",
            )
        )
        return r.rowcount or 0


def get_running_job_id(cfg: Config) -> int | None:
    """Return the id of an in-progress sync, if any."""
    init_db(cfg)
    with session_scope(cfg) as s:
        return s.scalar(select(SyncJob.id).where(SyncJob.status == "running").limit(1))


def db_stats(cfg: Config) -> dict[str, int]:
    init_db(cfg)
    with session_scope(cfg) as s:
        return {
            "photos": s.scalar(select(func.count()).select_from(Photo)) or 0,
            "exif_rows": s.scalar(select(func.count()).select_from(Exif)) or 0,
            "photo_tags": s.scalar(select(func.count()).select_from(PhotoTag)) or 0,
            "queued_exif": s.scalar(
                select(func.count()).select_from(SyncQueue).where(SyncQueue.kind == "exif")
            )
            or 0,
            "photos_synced": s.scalar(
                select(func.count()).select_from(Photo).where(Photo.exif_synced_at.is_not(None))
            )
            or 0,
            "photos_errored": s.scalar(
                select(func.count()).select_from(Photo).where(Photo.sync_status == "error")
            )
            or 0,
        }
