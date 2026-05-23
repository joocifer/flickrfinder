import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api";

type Props = {
  photoId: string;
  onClose: () => void;
};

export function PhotoDetail({ photoId, onClose }: Props) {
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["photo", photoId],
    queryFn: () => api.photo(photoId),
  });

  const download = useQuery({
    queryKey: ["download", photoId],
    queryFn: () => api.getDownload(photoId),
  });

  const startDownload = useMutation({
    mutationFn: () => api.startDownload(photoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["download", photoId] });
    },
  });

  const refresh = useMutation({
    mutationFn: () => api.syncPhotos([photoId]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["photo", photoId] });
      qc.invalidateQueries({ queryKey: ["search"] });
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hasFile = download.data && !download.isFetching;
  const downloadBytes = download.data ? Math.round((download.data.bytes / 1024 / 1024) * 10) / 10 : 0;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-zinc-950 border border-zinc-800 rounded-lg max-w-6xl w-full max-h-[95vh] flex flex-col lg:flex-row overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="lg:flex-1 bg-black flex items-center justify-center min-h-[40vh] lg:min-h-0 lg:max-h-[95vh]">
          {isLoading && <div className="text-zinc-500">Loading…</div>}
          {error && <div className="text-red-400">Failed to load.</div>}
          {data?.url_m && (
            <img
              src={data.url_l || data.url_m}
              alt={data.title || data.id}
              className="max-w-full max-h-[60vh] lg:max-h-[95vh] object-contain"
            />
          )}
        </div>
        <div className="lg:w-96 lg:shrink-0 border-t lg:border-t-0 lg:border-l border-zinc-800 flex flex-col">
          <div className="p-4 border-b border-zinc-800 flex items-start justify-between gap-2">
            <div>
              <h2 className="font-semibold text-zinc-100">
                {data?.title || <span className="text-zinc-500">untitled</span>}
              </h2>
              <p className="text-xs text-zinc-500 mt-1">
                ID {photoId} · {data?.is_public ? "Public" : "Private"}
              </p>
              {data?.taken_at && (
                <p className="text-xs text-zinc-500">
                  Taken {new Date(data.taken_at).toLocaleString()}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-zinc-400 hover:text-zinc-100 text-2xl leading-none"
              aria-label="close"
            >
              ×
            </button>
          </div>

          <div className="p-3 border-b border-zinc-800 flex flex-wrap items-center gap-2">
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="text-xs px-3 py-1 rounded border border-zinc-800 hover:border-amber-400 hover:text-amber-400 disabled:opacity-40"
              title="Re-fetch metadata + EXIF from Flickr"
            >
              {refresh.isPending ? "Refreshing…" : "Refresh metadata"}
            </button>
            {hasFile ? (
              <div className="flex items-center gap-2 text-xs">
                <a
                  href={api.fileUrl(photoId)}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1 rounded border border-emerald-700 text-emerald-300 hover:bg-emerald-900/40"
                >
                  ↓ Open original ({downloadBytes} MB)
                </a>
                <button
                  onClick={() => startDownload.mutate()}
                  disabled={startDownload.isPending}
                  className="text-zinc-500 hover:text-zinc-300 disabled:opacity-40"
                  title="Re-download from Flickr"
                >
                  ⟳
                </button>
              </div>
            ) : (
              <button
                onClick={() => startDownload.mutate()}
                disabled={startDownload.isPending}
                className="text-xs px-3 py-1 rounded border border-zinc-800 hover:border-amber-400 hover:text-amber-400 disabled:opacity-40"
                title="Fetch the full-size original from Flickr"
              >
                {startDownload.isPending ? "Downloading…" : "Download original"}
              </button>
            )}
            {startDownload.error && (
              <span className="text-xs text-red-400 w-full">
                {String(startDownload.error)}
              </span>
            )}
            {refresh.error && (
              <span className="text-xs text-red-400 w-full">{String(refresh.error)}</span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 text-sm">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">
              EXIF
            </h3>
            <dl className="space-y-1">
              {data &&
                Object.entries(data.exif)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-zinc-500 shrink-0">{k}</dt>
                      <dd className="text-zinc-200 text-right break-all">{v}</dd>
                    </div>
                  ))}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
