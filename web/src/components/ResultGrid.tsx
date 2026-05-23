import type { Photo } from "../api";
import { PhotoCard } from "./PhotoCard";

type Props = {
  photos: Photo[];
  onOpen: (id: string) => void;
};

export function ResultGrid({ photos, onOpen }: Props) {
  if (photos.length === 0) {
    return (
      <div className="text-zinc-500 text-sm py-16 text-center">
        No photos match these filters.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
      {photos.map((p) => (
        <PhotoCard key={p.id} photo={p} onOpen={() => onOpen(p.id)} />
      ))}
    </div>
  );
}
