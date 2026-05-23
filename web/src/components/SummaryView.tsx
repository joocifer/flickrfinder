import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type FilterState } from "../api";

type Props = {
  filters: FilterState;
  onPick: (tag: string, value: string) => void;
  onClose: () => void;
};

const DEFAULT_TAG = "Make";

export function SummaryView({ filters, onPick, onClose }: Props) {
  const [tag, setTag] = useState<string>(DEFAULT_TAG);

  const tags = useQuery({
    queryKey: ["exif-tags"],
    queryFn: api.exifTags,
    staleTime: 5 * 60_000,
  });

  const values = useQuery({
    queryKey: ["exif-values", tag, filters],
    queryFn: () => api.exifValues(tag, filters),
    enabled: !!tag,
  });

  const data = values.data ?? [];
  const totalShown = data.reduce((sum, v) => sum + v.count, 0);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-zinc-400">Summary by</span>
          <select
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            className="rounded bg-zinc-950 border border-zinc-800 px-2 py-1 text-sm focus:border-amber-400 focus:outline-none"
          >
            {tags.data?.map((t) => (
              <option key={t.tag} value={t.tag}>
                {t.tag} ({t.count.toLocaleString()})
              </option>
            ))}
          </select>
          <span className="text-xs text-zinc-500">
            {data.length > 0 && `${data.length} distinct value${data.length === 1 ? "" : "s"}`}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1 rounded border border-zinc-800 hover:border-zinc-600"
        >
          ← Back to grid
        </button>
      </div>

      {values.isPending && (
        <div className="text-sm text-zinc-500 py-16 text-center">Computing…</div>
      )}
      {values.error && (
        <div className="text-sm text-red-400 py-16 text-center">{String(values.error)}</div>
      )}
      {values.data && data.length === 0 && (
        <div className="text-sm text-zinc-500 py-16 text-center">
          No photos in the current selection have this EXIF tag.
        </div>
      )}
      {data.length > 0 && (
        <div className="overflow-y-auto max-h-[calc(100vh-220px)]">
          <table className="w-full text-sm">
            <thead className="text-xs text-zinc-500 uppercase tracking-wider sticky top-0 bg-zinc-900 border-b border-zinc-800">
              <tr>
                <th className="text-left font-medium px-4 py-2">Value</th>
                <th className="text-right font-medium px-4 py-2 w-32">Photos</th>
                <th className="text-right font-medium px-4 py-2 w-20">%</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => {
                const pct = totalShown > 0 ? (row.count / totalShown) * 100 : 0;
                return (
                  <tr
                    key={row.value}
                    onClick={() => onPick(tag, row.value)}
                    className="border-b border-zinc-800/60 hover:bg-zinc-800/60 cursor-pointer"
                    title={`Click to filter to ${tag}=${row.value}`}
                  >
                    <td className="px-4 py-2 text-zinc-100 break-all">{row.value}</td>
                    <td className="px-4 py-2 text-right text-zinc-300 tabular-nums">
                      {row.count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right text-zinc-500 tabular-nums">
                      {pct.toFixed(1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
