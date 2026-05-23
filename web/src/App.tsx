import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, emptyFilters } from "./api";
import { FilterSidebar } from "./components/FilterSidebar";
import { Pager } from "./components/Pager";
import { PhotoDetail } from "./components/PhotoDetail";
import { ResultGrid } from "./components/ResultGrid";
import { SummaryView } from "./components/SummaryView";
import { SyncStatus } from "./components/SyncStatus";
import { Toolbar } from "./components/Toolbar";
import { useFilters } from "./filters";

export default function App() {
  const [filters, committed, setFilters] = useFilters();
  const [openId, setOpenId] = useState<string | null>(null);
  const [summary, setSummary] = useState(false);

  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const results = useQuery({
    queryKey: ["search", committed],
    queryFn: () => api.search(committed),
    placeholderData: keepPreviousData,
    enabled: !summary,
  });

  const total = results.data?.total ?? 0;
  const photos = results.data?.results ?? [];
  const from = total === 0 ? 0 : committed.offset + 1;
  const to = Math.min(total, committed.offset + photos.length);
  const isStale = filters !== committed || results.isFetching;

  return (
    <div className="min-h-full">
      <header className="border-b border-zinc-800 bg-zinc-950 sticky top-0 z-30">
        <div className="max-w-[1600px] mx-auto px-4 lg:px-6 h-14 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <h1 className="text-lg font-semibold tracking-tight">
              <span className="text-amber-400">flickr</span>finder
            </h1>
            <span className="text-xs text-zinc-500">
              {me.data
                ? `${me.data.photos.toLocaleString()} photos · ${me.data.owner_nsid}`
                : ""}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <SyncStatus />
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              API docs →
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 lg:px-6 py-4 flex flex-col lg:flex-row gap-6">
        <FilterSidebar filters={filters} onChange={setFilters} />
        <section className="flex-1 min-w-0">
          <Toolbar
            filters={filters}
            total={total}
            showingFrom={from}
            showingTo={to}
            searching={isStale && !summary}
            summaryActive={summary}
            onToggleSummary={() => setSummary((v) => !v)}
            onChange={setFilters}
            onReset={() => setFilters(() => ({ ...emptyFilters }))}
          />
          {summary ? (
            <div className="py-4">
              <SummaryView
                filters={committed}
                onPick={(tag, value) => {
                  setFilters((f) => ({
                    ...f,
                    exif: [...f.exif, `${tag}=${value}`],
                    offset: 0,
                  }));
                  setSummary(false);
                }}
                onClose={() => setSummary(false)}
              />
            </div>
          ) : (
            <>
              <div className={`py-4 transition-opacity ${isStale ? "opacity-60" : ""}`}>
                {results.isPending ? (
                  <div className="text-sm text-zinc-500 py-16 text-center">Searching…</div>
                ) : results.error ? (
                  <div className="text-sm text-red-400 py-16 text-center">
                    {String(results.error)}
                  </div>
                ) : (
                  <ResultGrid photos={photos} onOpen={setOpenId} />
                )}
              </div>
              <Pager
                total={total}
                limit={committed.limit}
                offset={committed.offset}
                onChange={(offset) => setFilters((f) => ({ ...f, offset }))}
              />
            </>
          )}
        </section>
      </main>

      {openId && <PhotoDetail photoId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}
