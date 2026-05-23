type Props = {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
};

export function Pager({ total, limit, offset, onChange }: Props) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  const prev = Math.max(0, offset - limit);
  const next = offset + limit;
  return (
    <div className="flex items-center justify-center gap-2 py-6 text-sm">
      <button
        onClick={() => onChange(prev)}
        disabled={offset === 0}
        className="px-3 py-1 rounded border border-zinc-800 disabled:opacity-30 hover:border-zinc-600"
      >
        ← Prev
      </button>
      <span className="text-zinc-400 px-2">
        Page {page} of {pages}
      </span>
      <button
        onClick={() => onChange(next)}
        disabled={next >= total}
        className="px-3 py-1 rounded border border-zinc-800 disabled:opacity-30 hover:border-zinc-600"
      >
        Next →
      </button>
    </div>
  );
}
