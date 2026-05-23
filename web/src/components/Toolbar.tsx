import type { FilterState } from "../api";
import { emptyFilters } from "../api";

type Props = {
  filters: FilterState;
  total: number;
  showingFrom: number;
  showingTo: number;
  searching?: boolean;
  summaryActive?: boolean;
  onToggleSummary?: () => void;
  onChange: (updater: (prev: FilterState) => FilterState) => void;
  onReset: () => void;
};

export function Toolbar({
  filters,
  total,
  showingFrom,
  showingTo,
  searching = false,
  summaryActive = false,
  onToggleSummary,
  onChange,
  onReset,
}: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3 border-b border-zinc-800">
      <div className="text-sm text-zinc-400 flex items-center gap-3">
        {total > 0 ? (
          <span>
            <span className="text-zinc-200 font-medium">{total.toLocaleString()}</span> photos
            <span className="ml-2 text-zinc-500">
              showing {showingFrom.toLocaleString()}–{showingTo.toLocaleString()}
            </span>
          </span>
        ) : (
          <span className="text-zinc-500">no matches</span>
        )}
        {searching && (
          <span className="text-xs text-amber-400 inline-flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            searching…
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 text-sm">
        <label className="text-zinc-500 text-xs">sort</label>
        <select
          value={filters.order}
          onChange={(e) =>
            onChange((f) => ({ ...f, order: e.target.value as FilterState["order"], offset: 0 }))
          }
          className="rounded bg-zinc-900 border border-zinc-800 px-2 py-1"
        >
          <option value="taken">Taken</option>
          <option value="uploaded">Uploaded</option>
          <option value="focal">Focal length</option>
          <option value="iso">ISO</option>
          <option value="aperture">Aperture</option>
          <option value="shutter">Shutter</option>
        </select>
        <button
          onClick={() =>
            onChange((f) => ({
              ...f,
              direction: f.direction === "desc" ? "asc" : "desc",
              offset: 0,
            }))
          }
          className="rounded border border-zinc-800 px-2 py-1 hover:border-zinc-600"
          title="Toggle sort direction"
        >
          {filters.direction === "desc" ? "↓" : "↑"}
        </button>
        <select
          value={filters.limit}
          onChange={(e) => onChange((f) => ({ ...f, limit: Number(e.target.value), offset: 0 }))}
          className="rounded bg-zinc-900 border border-zinc-800 px-2 py-1"
        >
          {[24, 48, 60, 120, 240].map((n) => (
            <option key={n} value={n}>
              {n} / page
            </option>
          ))}
        </select>
        <button
          onClick={onReset}
          disabled={
            JSON.stringify({ ...filters, offset: 0 }) === JSON.stringify(emptyFilters)
          }
          className="rounded border border-zinc-800 px-2 py-1 hover:border-zinc-600 disabled:opacity-30"
        >
          Clear
        </button>
        {onToggleSummary && (
          <button
            onClick={onToggleSummary}
            className={`rounded border px-2 py-1 ${
              summaryActive
                ? "border-amber-400 text-amber-400"
                : "border-zinc-800 hover:border-zinc-600"
            }`}
            title="Group photos in the current selection by an EXIF tag"
          >
            Summary
          </button>
        )}
      </div>
    </div>
  );
}
