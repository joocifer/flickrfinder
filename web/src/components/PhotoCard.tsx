import type { Photo } from "../api";

type Props = {
  photo: Photo;
  onOpen: () => void;
};

export function PhotoCard({ photo, onOpen }: Props) {
  const camera = photo.exif["Model"] || photo.exif["Make"] || "";
  const focal = photo.exif["FocalLength"] || "";
  const fnum = photo.exif["FNumber"] ? `f/${photo.exif["FNumber"]}` : "";
  const shutter = photo.exif["ExposureTime"] || "";
  const iso = photo.exif["ISO"] || photo.exif["ISOSpeedRatings"] || "";

  return (
    <button
      onClick={onOpen}
      className="group text-left rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800 hover:border-amber-400/60 transition-colors"
    >
      <div className="aspect-square bg-zinc-950 overflow-hidden">
        {photo.url_m || photo.url_t ? (
          <img
            src={photo.url_m || photo.url_t || undefined}
            alt={photo.title || photo.id}
            loading="lazy"
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full grid place-items-center text-xs text-zinc-600">
            no thumbnail
          </div>
        )}
      </div>
      <div className="p-2.5 text-xs space-y-1">
        <div className="truncate text-zinc-100" title={photo.title}>
          {photo.title || <span className="text-zinc-500">untitled</span>}
        </div>
        <div className="text-zinc-500 truncate" title={camera}>
          {camera || "—"}
        </div>
        <div className="flex flex-wrap gap-1 text-[10px] text-zinc-400">
          {focal && <span>{focal}</span>}
          {fnum && <span>{fnum}</span>}
          {shutter && <span>{shutter}</span>}
          {iso && <span>ISO {iso}</span>}
        </div>
      </div>
    </button>
  );
}
