"""Fetch original-size images on demand and persist them under data/originals/."""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import flickrapi
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from flickrfinder.config import Config
from flickrfinder.core.db import init_db, session_scope
from flickrfinder.core.flickr_client import build_client
from flickrfinder.core.models import Download, Photo


class DownloadError(RuntimeError):
    pass


_SIZE_PREFERENCE = ("Original", "Large 2048", "Large 1600", "Large")


def _pick_source(sizes: list[dict], requested: str = "Original") -> tuple[str, str]:
    """Pick the best size we can. Returns (label, source URL)."""
    by_label = {s.get("label"): s for s in sizes}
    if requested in by_label and by_label[requested].get("source"):
        return requested, by_label[requested]["source"]
    for label in _SIZE_PREFERENCE:
        s = by_label.get(label)
        if s and s.get("source"):
            return label, s["source"]
    raise DownloadError("no downloadable size available for this photo")


def _ext_from_url(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    _, ext = os.path.splitext(name)
    return ext.lower() or ".jpg"


def get_download(s: Session, photo_id: str) -> Download | None:
    return s.execute(
        select(Download).where(Download.photo_id == photo_id, Download.size == "Original")
    ).scalar_one_or_none()


def download_original(cfg: Config, photo_id: str, *, force: bool = False) -> Download:
    """Download (or re-download) the original-size image for one photo."""
    init_db(cfg)
    with session_scope(cfg) as s:
        if s.get(Photo, photo_id) is None:
            raise DownloadError(f"photo {photo_id} not in local DB; sync first")
        existing = get_download(s, photo_id)
        if existing and not force and Path(existing.path).exists():
            return existing

    flickr = build_client(cfg)
    try:
        resp = flickr.photos.getSizes(photo_id=photo_id)
    except flickrapi.exceptions.FlickrError as e:
        raise DownloadError(f"getSizes failed: {e}") from e
    sizes = resp.get("sizes", {}).get("size", [])
    label, source_url = _pick_source(sizes)

    cfg.originals_dir.mkdir(parents=True, exist_ok=True)
    ext = _ext_from_url(source_url)
    final_path = cfg.originals_dir / f"{photo_id}{ext}"

    # Stream to a tmp file in the same directory, then atomic rename.
    fd, tmp_path = tempfile.mkstemp(suffix=ext, dir=cfg.originals_dir)
    os.close(fd)
    try:
        with requests.get(source_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        os.replace(tmp_path, final_path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise

    size_bytes = final_path.stat().st_size

    with session_scope(cfg) as s:
        existing = get_download(s, photo_id)
        if existing:
            existing.path = str(final_path)
            existing.bytes = size_bytes
            existing.source_url = source_url
            existing.downloaded_at = datetime.now(tz=UTC)
            existing.size = label
            s.flush()
            s.refresh(existing)
            return existing
        d = Download(
            photo_id=photo_id,
            size=label,
            path=str(final_path),
            bytes=size_bytes,
            source_url=source_url,
            downloaded_at=datetime.now(tz=UTC),
        )
        s.add(d)
        s.flush()
        s.refresh(d)
        return d
