"""Search and faceting over the local Flickr metadata DB.

The same Filter dataclass and query builder is used by both the CLI and the
HTTP API. Numeric filters hit Exif.clean_num; string filters hit Exif.clean_str.
String matching is case-insensitive substring unless otherwise noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

from flickrfinder.core.models import Exif, Photo, PhotoTag

SortKey = Literal["taken", "uploaded", "focal", "iso", "aperture", "shutter"]
SortDir = Literal["asc", "desc"]


class FilterError(ValueError):
    pass


@dataclass
class ExifExpr:
    tag: str
    op: str  # one of: =, !=, <, <=, >, >=, ~=
    value: str

    _OPS = ("~=", "!=", ">=", "<=", "=", "<", ">")

    @classmethod
    def parse(cls, expr: str) -> ExifExpr:
        for op in cls._OPS:
            idx = expr.find(op)
            if idx > 0:
                return cls(tag=expr[:idx].strip(), op=op, value=expr[idx + len(op) :].strip())
        raise FilterError(
            f"invalid --exif expression {expr!r}; expected TAG OP VALUE "
            f"(operators: =, !=, ~=, <, <=, >, >=)"
        )


@dataclass
class Filter:
    camera: str | None = None
    make: str | None = None
    model: str | None = None
    lens: str | None = None

    focal_length: float | None = None
    focal_min: float | None = None
    focal_max: float | None = None

    aperture: float | None = None
    aperture_min: float | None = None
    aperture_max: float | None = None

    shutter: float | None = None
    shutter_min: float | None = None
    shutter_max: float | None = None
    shutter_faster_than: float | None = None
    shutter_slower_than: float | None = None

    iso: int | None = None
    iso_min: int | None = None
    iso_max: int | None = None

    taken_after: datetime | None = None
    taken_before: datetime | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None

    tags: list[str] = field(default_factory=list)
    public: bool | None = None  # None = either, True/False = filter

    exif: list[ExifExpr] = field(default_factory=list)

    limit: int = 50
    offset: int = 0
    sort: SortKey = "taken"
    direction: SortDir = "desc"


_SORT_PHOTO_COLUMNS = {
    "taken": Photo.taken_at,
    "uploaded": Photo.uploaded_at,
}
_SORT_EXIF_TAGS = {
    "focal": "FocalLength",
    "iso": "ISO",
    "aperture": "FNumber",
    "shutter": "ExposureTime",
}


def _exif_photo_ids(*, tag: str | list[str], **conds):
    """Build a `SELECT photo_id FROM exif WHERE ...` subquery.

    Used inside `Photo.id.in_(...)`. This is dramatically faster than a
    correlated EXISTS subquery: SQLite range-scans the (tag, clean_*) index
    once instead of re-running it for every parent Photo row.
    """
    where = [Exif.tag == tag] if isinstance(tag, str) else [Exif.tag.in_(tag)]
    for col, predicate in conds.items():
        where.append(predicate(getattr(Exif, col)))
    return select(Exif.photo_id).where(*where)


def _exif_num_ids(tag: str, *, op: str, value: float):
    ops = {
        "=": lambda c: c == value,
        "!=": lambda c: c != value,
        "<": lambda c: c < value,
        "<=": lambda c: c <= value,
        ">": lambda c: c > value,
        ">=": lambda c: c >= value,
    }
    return _exif_photo_ids(tag=tag, clean_num=ops[op])


def _exif_str_ids(tag: str | list[str], *, op: str, value: str):
    v = value.lower()
    ops = {
        "=": lambda c: func.lower(c) == v,
        "!=": lambda c: func.lower(c) != v,
        "~=": lambda c: func.lower(c).like(f"%{v}%"),
    }
    return _exif_photo_ids(tag=tag, clean_str=ops[op])


def build_query(f: Filter) -> Select:
    q: Select = select(Photo)

    if f.camera:
        q = q.where(Photo.id.in_(_exif_str_ids(["Make", "Model"], op="~=", value=f.camera)))
    if f.make:
        q = q.where(Photo.id.in_(_exif_str_ids("Make", op="~=", value=f.make)))
    if f.model:
        q = q.where(Photo.id.in_(_exif_str_ids("Model", op="~=", value=f.model)))
    if f.lens:
        q = q.where(Photo.id.in_(_exif_str_ids(["LensModel", "Lens"], op="~=", value=f.lens)))

    if f.focal_length is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FocalLength", op="=", value=f.focal_length)))
    if f.focal_min is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FocalLength", op=">=", value=f.focal_min)))
    if f.focal_max is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FocalLength", op="<=", value=f.focal_max)))

    if f.aperture is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FNumber", op="=", value=f.aperture)))
    if f.aperture_min is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FNumber", op=">=", value=f.aperture_min)))
    if f.aperture_max is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("FNumber", op="<=", value=f.aperture_max)))

    if f.shutter is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ExposureTime", op="=", value=f.shutter)))
    if f.shutter_min is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ExposureTime", op=">=", value=f.shutter_min)))
    if f.shutter_max is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ExposureTime", op="<=", value=f.shutter_max)))
    if f.shutter_faster_than is not None:
        q = q.where(
            Photo.id.in_(_exif_num_ids("ExposureTime", op="<", value=f.shutter_faster_than))
        )
    if f.shutter_slower_than is not None:
        q = q.where(
            Photo.id.in_(_exif_num_ids("ExposureTime", op=">", value=f.shutter_slower_than))
        )

    if f.iso is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ISO", op="=", value=float(f.iso))))
    if f.iso_min is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ISO", op=">=", value=float(f.iso_min))))
    if f.iso_max is not None:
        q = q.where(Photo.id.in_(_exif_num_ids("ISO", op="<=", value=float(f.iso_max))))

    if f.taken_after is not None:
        q = q.where(Photo.taken_at >= f.taken_after)
    if f.taken_before is not None:
        q = q.where(Photo.taken_at <= f.taken_before)
    if f.uploaded_after is not None:
        q = q.where(Photo.uploaded_at >= f.uploaded_after)
    if f.uploaded_before is not None:
        q = q.where(Photo.uploaded_at <= f.uploaded_before)

    for tag in f.tags:
        q = q.where(
            Photo.id.in_(
                select(PhotoTag.photo_id).where(func.lower(PhotoTag.tag) == tag.lower())
            )
        )

    if f.public is True:
        q = q.where(Photo.is_public.is_(True))
    elif f.public is False:
        q = q.where(Photo.is_public.is_(False))

    for e in f.exif:
        if e.op in ("<", "<=", ">", ">="):
            try:
                v = float(e.value)
            except ValueError as err:
                raise FilterError(
                    f"--exif {e.tag}{e.op}{e.value!r} requires a numeric value"
                ) from err
            q = q.where(Photo.id.in_(_exif_num_ids(e.tag, op=e.op, value=v)))
        elif e.op in ("=", "!=", "~="):
            q = q.where(Photo.id.in_(_exif_str_ids(e.tag, op=e.op, value=e.value)))
        else:
            raise FilterError(f"unsupported operator: {e.op}")

    # Sort
    if f.sort in _SORT_PHOTO_COLUMNS:
        col = _SORT_PHOTO_COLUMNS[f.sort]
        q = q.order_by(desc(col) if f.direction == "desc" else asc(col))
    else:
        # Sort by an EXIF numeric: subquery the value
        tag = _SORT_EXIF_TAGS[f.sort]
        sort_val = (
            select(Exif.clean_num)
            .where(Exif.photo_id == Photo.id, Exif.tag == tag)
            .limit(1)
            .scalar_subquery()
        )
        q = q.order_by(
            desc(sort_val).nullslast() if f.direction == "desc" else asc(sort_val).nullsfirst()
        )

    q = q.limit(f.limit).offset(f.offset)
    return q


@dataclass
class PhotoResult:
    id: str
    title: str
    taken_at: datetime | None
    uploaded_at: datetime | None
    url_t: str | None
    url_m: str | None
    is_public: bool
    exif: dict[str, str]  # tag → raw, only the common display tags


_DISPLAY_TAGS = (
    "Make",
    "Model",
    "LensModel",
    "Lens",
    "FocalLength",
    "FocalLengthIn35mmFormat",
    "FNumber",
    "ExposureTime",
    "ISO",
    "ISOSpeedRatings",
)


def search(s: Session, f: Filter) -> tuple[list[PhotoResult], int]:
    """Run a search. Returns (results, total_matching)."""
    base = build_query(f)
    # total ignores limit/offset
    total_q = select(func.count()).select_from(build_query(_clone_without_paging(f)).subquery())
    total = s.scalar(total_q) or 0

    photos: list[Photo] = list(s.execute(base).scalars().all())
    if not photos:
        return [], total

    ids = [p.id for p in photos]
    exif_rows = (
        s.execute(select(Exif).where(Exif.photo_id.in_(ids), Exif.tag.in_(_DISPLAY_TAGS)))
        .scalars()
        .all()
    )
    by_photo: dict[str, dict[str, str]] = {}
    for e in exif_rows:
        d = by_photo.setdefault(e.photo_id, {})
        # First write wins (across tagspaces); raw is enough for display
        d.setdefault(e.tag, e.raw)

    results = [
        PhotoResult(
            id=p.id,
            title=p.title,
            taken_at=p.taken_at,
            uploaded_at=p.uploaded_at,
            url_t=p.url_t,
            url_m=p.url_m,
            is_public=p.is_public,
            exif=by_photo.get(p.id, {}),
        )
        for p in photos
    ]
    return results, total


def clone_without_paging(f: Filter) -> Filter:
    g = Filter(**dict(f.__dict__))
    g.limit = 10**9
    g.offset = 0
    return g


_clone_without_paging = clone_without_paging  # backwards-compat alias
