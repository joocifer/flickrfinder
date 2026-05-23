"""Normalize Flickr EXIF raw strings to (numeric, string) forms.

Flickr returns EXIF values as opaque strings ("23 mm", "1/250", "f/2.8").
We keep the raw string and derive:
  - clean_num: float, when the tag is numeric and parses cleanly
  - clean_str: a tidy string representation suitable for facet filters
"""

from __future__ import annotations

import re


def _parse_focal_length(raw: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None


def _parse_exposure_time(raw: str) -> float | None:
    s = raw.strip()
    if "/" in s:
        try:
            num, den = s.split("/", 1)
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_fnumber(raw: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    return float(m.group(1)) if m else None


def _parse_iso(raw: str) -> float | None:
    m = re.search(r"(\d+)", raw)
    return float(m.group(1)) if m else None


_NUMERIC: dict[str, callable] = {
    "FocalLength": _parse_focal_length,
    "FocalLengthIn35mmFormat": _parse_focal_length,
    "FocalLengthIn35mmFilm": _parse_focal_length,
    "ExposureTime": _parse_exposure_time,
    "ShutterSpeed": _parse_exposure_time,
    "ShutterSpeedValue": _parse_exposure_time,
    "FNumber": _parse_fnumber,
    "ApertureValue": _parse_fnumber,
    "ISO": _parse_iso,
    "ISOSpeedRatings": _parse_iso,
    "PhotographicSensitivity": _parse_iso,
}


def normalize(tag: str, raw: str) -> tuple[float | None, str | None]:
    """Return (clean_num, clean_str) for an EXIF tag's raw value."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    parser = _NUMERIC.get(tag)
    if parser is not None:
        return parser(raw), raw
    return None, raw
