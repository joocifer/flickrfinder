export type Photo = {
  id: string;
  title: string;
  taken_at: string | null;
  uploaded_at: string | null;
  url_t: string | null;
  url_m: string | null;
  url_l: string | null;
  is_public: boolean;
  exif: Record<string, string>;
};

export type SearchResult = {
  total: number;
  limit: number;
  offset: number;
  results: Photo[];
};

export type FacetValue = { value: string; count: number };
export type Facets = {
  cameras: FacetValue[];
  lenses: FacetValue[];
  tags: FacetValue[];
  exif_tags: FacetValue[];
};

export type Me = {
  data_dir: string;
  owner_nsid: string;
  photos: number;
};

export type FilterState = {
  camera: string;
  lens: string;
  focal_min: string;
  focal_max: string;
  aperture_min: string;
  aperture_max: string;
  iso_min: string;
  iso_max: string;
  shutter_faster_than: string;
  shutter_slower_than: string;
  taken_after: string;
  taken_before: string;
  tag: string[];
  exif: string[];
  public: "" | "public" | "private";
  order: "taken" | "uploaded" | "focal" | "iso" | "aperture" | "shutter";
  direction: "asc" | "desc";
  limit: number;
  offset: number;
};

export const emptyFilters: FilterState = {
  camera: "",
  lens: "",
  focal_min: "",
  focal_max: "",
  aperture_min: "",
  aperture_max: "",
  iso_min: "",
  iso_max: "",
  shutter_faster_than: "",
  shutter_slower_than: "",
  taken_after: "",
  taken_before: "",
  tag: [],
  exif: [],
  public: "",
  order: "taken",
  direction: "desc",
  limit: 60,
  offset: 0,
};

function buildSearchParams(f: FilterState): URLSearchParams {
  const p = new URLSearchParams();
  const single: (keyof FilterState)[] = [
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
  ];
  for (const k of single) {
    const v = f[k] as string;
    if (v) p.set(k, v);
  }
  for (const t of f.tag) if (t) p.append("tag", t);
  for (const e of f.exif) if (e) p.append("exif", e);
  if (f.public === "public") p.set("public", "true");
  else if (f.public === "private") p.set("public", "false");
  p.set("order", f.order);
  p.set("direction", f.direction);
  p.set("limit", String(f.limit));
  p.set("offset", String(f.offset));
  return p;
}

async function getJson<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = params && params.toString() ? `${path}?${params.toString()}` : path;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export type SyncJob = {
  id: number;
  kind: string;
  status: "running" | "ok" | "error" | "cancelled";
  started_at: string;
  finished_at: string | null;
  total: number;
  done: number;
  error_count: number;
  last_error: string | null;
};

export type Download = {
  photo_id: string;
  size: string;
  path: string;
  bytes: number;
  source_url: string;
  downloaded_at: string;
};

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text || r.statusText}`);
  }
  return r.json();
}

export type ExifTag = { tag: string; count: number };
export type ExifValue = { value: string; count: number };

export const api = {
  me: () => getJson<Me>("/api/me"),
  search: (f: FilterState) => getJson<SearchResult>("/api/search", buildSearchParams(f)),
  facets: (top = 25) =>
    getJson<Facets>("/api/facets", new URLSearchParams({ top: String(top) })),
  exifTags: () => getJson<ExifTag[]>("/api/exif-tags"),
  exifValues: (key: string, filters: FilterState, limit = 200) => {
    const p = buildSearchParams(filters);
    p.set("key", key);
    p.set("limit", String(limit));
    p.delete("offset");
    return getJson<ExifValue[]>("/api/exif-values", p);
  },
  photo: (id: string) => getJson<Photo>(`/api/photos/${encodeURIComponent(id)}`),

  syncFull: () => postJson<SyncJob>("/api/sync/full"),
  syncPhotos: (ids: string[]) => postJson<SyncJob>("/api/sync/photos", { ids }),
  syncJob: (id: number) => getJson<SyncJob>(`/api/sync/jobs/${id}`),

  getDownload: async (id: string): Promise<Download | null> => {
    const r = await fetch(`/api/downloads/${encodeURIComponent(id)}`);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  startDownload: (id: string) =>
    postJson<Download>(`/api/downloads/${encodeURIComponent(id)}`),
  fileUrl: (id: string) => `/api/files/${encodeURIComponent(id)}`,
};
