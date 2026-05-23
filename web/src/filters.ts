import { useCallback, useEffect, useRef, useState } from "react";
import { emptyFilters, type FilterState } from "./api";

function readFromUrl(): FilterState {
  const p = new URLSearchParams(window.location.search);
  const f: FilterState = { ...emptyFilters };
  const keys = [
    "camera",
    "lens",
    "focal_min",
    "focal_max",
    "aperture_min",
    "aperture_max",
    "iso_min",
    "iso_max",
    "shutter_faster_than",
    "shutter_slower_than",
    "taken_after",
    "taken_before",
  ] as const;
  for (const k of keys) {
    const v = p.get(k);
    if (v !== null) (f as Record<string, unknown>)[k] = v;
  }
  f.tag = p.getAll("tag");
  f.exif = p.getAll("exif");
  const pub = p.get("public");
  f.public = pub === "true" ? "public" : pub === "false" ? "private" : "";
  const order = p.get("order");
  if (order && ["taken", "uploaded", "focal", "iso", "aperture", "shutter"].includes(order))
    f.order = order as FilterState["order"];
  const dir = p.get("direction");
  if (dir === "asc" || dir === "desc") f.direction = dir;
  const limit = Number(p.get("limit"));
  if (Number.isFinite(limit) && limit > 0) f.limit = limit;
  const offset = Number(p.get("offset"));
  if (Number.isFinite(offset) && offset >= 0) f.offset = offset;
  return f;
}

function writeToUrl(f: FilterState): void {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (k === "tag" || k === "exif") {
      for (const item of v as string[]) if (item) p.append(k, item);
    } else if (typeof v === "string") {
      if (v) p.set(k, v);
    } else if (typeof v === "number") {
      if ((k === "limit" && v !== emptyFilters.limit) || (k === "offset" && v !== 0))
        p.set(k, String(v));
    }
  }
  if (f.order !== emptyFilters.order) p.set("order", f.order);
  if (f.direction !== emptyFilters.direction) p.set("direction", f.direction);
  const next = p.toString();
  const newUrl = next ? `?${next}` : window.location.pathname;
  window.history.replaceState(null, "", newUrl);
}

/**
 * Two-tier filter state:
 *  - `filters` updates immediately for fast typing/UI feedback
 *  - `committed` lags `filters` by `debounceMs` and is what drives searches
 * The URL is updated from `committed` so reload restores the actual query.
 */
export function useFilters(
  debounceMs = 300,
): [
  FilterState,
  FilterState,
  (updater: (prev: FilterState) => FilterState) => void,
] {
  const initial = readFromUrl();
  const [filters, setFilters] = useState<FilterState>(initial);
  const [committed, setCommitted] = useState<FilterState>(initial);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (timer.current !== undefined) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCommitted(filters), debounceMs);
    return () => {
      if (timer.current !== undefined) window.clearTimeout(timer.current);
    };
  }, [filters, debounceMs]);

  useEffect(() => {
    writeToUrl(committed);
  }, [committed]);

  const update = useCallback(
    (updater: (prev: FilterState) => FilterState) => setFilters((prev) => updater(prev)),
    [],
  );

  return [filters, committed, update];
}
