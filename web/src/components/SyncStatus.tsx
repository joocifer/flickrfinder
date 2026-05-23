import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SyncJob } from "../api";

export function SyncStatus() {
  const qc = useQueryClient();
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  const start = useMutation({
    mutationFn: () => api.syncFull(),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const job = useQuery<SyncJob>({
    queryKey: ["syncJob", activeJobId],
    queryFn: () => api.syncJob(activeJobId as number),
    enabled: activeJobId !== null,
    refetchInterval: (q) => {
      const data = q.state.data;
      return data && data.status === "running" ? 2000 : false;
    },
  });

  // When a job finishes, refresh the search results once.
  useEffect(() => {
    if (job.data && job.data.status !== "running") {
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    }
  }, [job.data?.status, qc]);  // eslint-disable-line react-hooks/exhaustive-deps

  const running = job.data?.status === "running";
  const pct =
    job.data && job.data.total > 0 ? Math.round((job.data.done / job.data.total) * 100) : 0;

  return (
    <div className="flex items-center gap-3">
      {job.data && (
        <div className="hidden sm:flex items-center gap-2 text-xs">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              running
                ? "bg-amber-400 animate-pulse"
                : job.data.status === "ok"
                  ? "bg-emerald-400"
                  : job.data.status === "error"
                    ? "bg-red-400"
                    : "bg-zinc-500"
            }`}
          />
          {running ? (
            <span className="text-zinc-300">
              syncing {job.data.done.toLocaleString()}/{job.data.total.toLocaleString()} (
              {pct}%)
            </span>
          ) : (
            <span className="text-zinc-500">
              last sync: {job.data.status}
              {job.data.error_count > 0 && ` · ${job.data.error_count} errors`}
            </span>
          )}
        </div>
      )}
      <button
        disabled={start.isPending || running}
        onClick={() => start.mutate()}
        className="text-xs px-3 py-1 rounded border border-zinc-800 hover:border-amber-400 hover:text-amber-400 disabled:opacity-40"
        title="Pull new/changed photo metadata from Flickr"
      >
        {running ? "Syncing…" : "Sync now"}
      </button>
    </div>
  );
}
