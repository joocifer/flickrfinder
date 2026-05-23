"""Aggregations that tell the user what's actually searchable in their DB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from flickrfinder.core.models import Exif, PhotoTag

if TYPE_CHECKING:
    from flickrfinder.core.search import Filter


@dataclass
class FacetValue:
    value: str
    count: int


@dataclass
class Facets:
    cameras: list[FacetValue]
    lenses: list[FacetValue]
    tags: list[FacetValue]
    exif_tags: list[FacetValue]  # tag name → photo count


def _top_values_for_exif_tag(s: Session, tag: str | list[str], top: int) -> list[FacetValue]:
    where = Exif.tag == tag if isinstance(tag, str) else Exif.tag.in_(tag)
    q = (
        select(Exif.clean_str, func.count(func.distinct(Exif.photo_id)))
        .where(where, Exif.clean_str.is_not(None))
        .group_by(Exif.clean_str)
        .order_by(desc(func.count(func.distinct(Exif.photo_id))))
        .limit(top)
    )
    return [FacetValue(value=v, count=c) for v, c in s.execute(q).all() if v]


def compute_facets(s: Session, top: int = 25) -> Facets:
    cameras = _top_values_for_exif_tag(s, "Model", top=top)
    lenses = _top_values_for_exif_tag(s, ["LensModel", "Lens"], top=top)

    tags_q = (
        select(PhotoTag.tag, func.count(func.distinct(PhotoTag.photo_id)))
        .group_by(PhotoTag.tag)
        .order_by(desc(func.count(func.distinct(PhotoTag.photo_id))))
        .limit(top)
    )
    tags = [FacetValue(value=t, count=c) for t, c in s.execute(tags_q).all()]

    exif_tags_q = (
        select(Exif.tag, func.count(func.distinct(Exif.photo_id)))
        .group_by(Exif.tag)
        .order_by(desc(func.count(func.distinct(Exif.photo_id))))
        .limit(top)
    )
    exif_tags = [FacetValue(value=t, count=c) for t, c in s.execute(exif_tags_q).all()]

    return Facets(cameras=cameras, lenses=lenses, tags=tags, exif_tags=exif_tags)


def exif_value_counts(
    s: Session,
    tag: str,
    *,
    filter: Filter | None = None,
    limit: int = 200,
) -> list[FacetValue]:
    """Group distinct values for one EXIF tag and count photos per value.

    If `filter` is given, only photos matching the filter contribute to the
    counts — this is what makes the summary view a true drill-down view.
    """
    q = (
        select(Exif.clean_str, func.count(func.distinct(Exif.photo_id)).label("c"))
        .where(Exif.tag == tag, Exif.clean_str.is_not(None))
        .group_by(Exif.clean_str)
        .order_by(desc("c"))
        .limit(limit)
    )
    if filter is not None and _filter_has_predicates(filter):
        from flickrfinder.core.search import build_query, clone_without_paging

        filtered = build_query(clone_without_paging(filter)).subquery()
        q = q.where(Exif.photo_id.in_(select(filtered.c.id)))
    return [FacetValue(value=v, count=c) for v, c in s.execute(q).all()]


def _filter_has_predicates(f: Filter) -> bool:
    """Cheap check: does this filter actually narrow anything? Skip the subquery if not."""
    for attr, default in (
        ("camera", None),
        ("make", None),
        ("model", None),
        ("lens", None),
        ("focal_length", None),
        ("focal_min", None),
        ("focal_max", None),
        ("aperture", None),
        ("aperture_min", None),
        ("aperture_max", None),
        ("shutter", None),
        ("shutter_min", None),
        ("shutter_max", None),
        ("shutter_faster_than", None),
        ("shutter_slower_than", None),
        ("iso", None),
        ("iso_min", None),
        ("iso_max", None),
        ("taken_after", None),
        ("taken_before", None),
        ("uploaded_after", None),
        ("uploaded_before", None),
        ("public", None),
    ):
        if getattr(f, attr) != default:
            return True
    return bool(f.tags) or bool(f.exif)
