from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from flickrfinder.core.models import Base, Exif, Photo, PhotoTag
from flickrfinder.core.search import ExifExpr, Filter, FilterError, search


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine, expire_on_commit=False)
    s = SF()
    try:
        _seed(s)
        s.commit()
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed(s: Session) -> None:
    # Photo A: D800, 24-70 f/2.8, 35mm, ISO 400, 1/250
    s.add(
        Photo(
            id="A",
            owner_nsid="me",
            title="Beach",
            is_public=True,
            taken_at=datetime(2024, 6, 1, 12, 0, 0),
        )
    )
    s.add_all(
        [
            Exif(
                photo_id="A",
                tagspace="IFD0",
                tag="Make",
                raw="NIKON CORPORATION",
                clean_num=None,
                clean_str="NIKON CORPORATION",
            ),
            Exif(
                photo_id="A",
                tagspace="IFD0",
                tag="Model",
                raw="NIKON D800",
                clean_num=None,
                clean_str="NIKON D800",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="FocalLength",
                raw="35 mm",
                clean_num=35.0,
                clean_str="35 mm",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="FNumber",
                raw="2.8",
                clean_num=2.8,
                clean_str="2.8",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="ISO",
                raw="400",
                clean_num=400.0,
                clean_str="400",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="ExposureTime",
                raw="1/250",
                clean_num=0.004,
                clean_str="1/250",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="LensModel",
                raw="24-70mm f/2.8",
                clean_num=None,
                clean_str="24-70mm f/2.8",
            ),
            Exif(
                photo_id="A",
                tagspace="EXIF",
                tag="WhiteBalance",
                raw="Auto",
                clean_num=None,
                clean_str="Auto",
            ),
        ]
    )
    s.add(PhotoTag(photo_id="A", tag="beach", raw="beach"))
    s.add(PhotoTag(photo_id="A", tag="vacation", raw="vacation"))

    # Photo B: X-T5, XF23mm f/2, 23mm, ISO 1600, 1/60
    s.add(
        Photo(
            id="B",
            owner_nsid="me",
            title="Cafe",
            is_public=False,
            taken_at=datetime(2025, 1, 10, 19, 0, 0),
        )
    )
    s.add_all(
        [
            Exif(
                photo_id="B",
                tagspace="IFD0",
                tag="Make",
                raw="FUJIFILM",
                clean_num=None,
                clean_str="FUJIFILM",
            ),
            Exif(
                photo_id="B",
                tagspace="IFD0",
                tag="Model",
                raw="X-T5",
                clean_num=None,
                clean_str="X-T5",
            ),
            Exif(
                photo_id="B",
                tagspace="EXIF",
                tag="FocalLength",
                raw="23 mm",
                clean_num=23.0,
                clean_str="23 mm",
            ),
            Exif(
                photo_id="B", tagspace="EXIF", tag="FNumber", raw="2", clean_num=2.0, clean_str="2"
            ),
            Exif(
                photo_id="B",
                tagspace="EXIF",
                tag="ISO",
                raw="1600",
                clean_num=1600.0,
                clean_str="1600",
            ),
            Exif(
                photo_id="B",
                tagspace="EXIF",
                tag="ExposureTime",
                raw="1/60",
                clean_num=1 / 60,
                clean_str="1/60",
            ),
            Exif(
                photo_id="B",
                tagspace="EXIF",
                tag="LensModel",
                raw="XF23mmF2 R WR",
                clean_num=None,
                clean_str="XF23mmF2 R WR",
            ),
        ]
    )
    s.add(PhotoTag(photo_id="B", tag="indoor", raw="indoor"))


def test_camera_substring(session: Session) -> None:
    r, total = search(session, Filter(camera="X-T5"))
    assert total == 1
    assert r[0].id == "B"


def test_focal_length_range(session: Session) -> None:
    r, total = search(session, Filter(focal_min=20, focal_max=30))
    assert total == 1
    assert r[0].id == "B"


def test_combined_filters(session: Session) -> None:
    r, total = search(session, Filter(camera="NIKON", aperture_max=3.0, iso_max=500))
    assert total == 1 and r[0].id == "A"


def test_tag_filter_anded(session: Session) -> None:
    _, total = search(session, Filter(tags=["beach", "vacation"]))
    assert total == 1
    _, total = search(session, Filter(tags=["beach", "indoor"]))
    assert total == 0


def test_public_filter(session: Session) -> None:
    _, public_only = search(session, Filter(public=True))
    _, private_only = search(session, Filter(public=False))
    assert public_only == 1 and private_only == 1


def test_exif_string_eq(session: Session) -> None:
    r, total = search(session, Filter(exif=[ExifExpr.parse("WhiteBalance=Auto")]))
    assert total == 1 and r[0].id == "A"


def test_exif_numeric_gte(session: Session) -> None:
    _, total = search(session, Filter(exif=[ExifExpr.parse("FocalLength>=30")]))
    assert total == 1


def test_exif_substring(session: Session) -> None:
    _, total = search(session, Filter(exif=[ExifExpr.parse("Model~=X-T")]))
    assert total == 1


def test_invalid_exif_expr() -> None:
    with pytest.raises(FilterError):
        ExifExpr.parse("nope")


def test_default_sort_taken_desc(session: Session) -> None:
    r, _ = search(session, Filter(limit=10))
    # B (2025) before A (2024)
    assert [p.id for p in r] == ["B", "A"]
