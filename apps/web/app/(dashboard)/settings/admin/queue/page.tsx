"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import { ArrowLeft, RefreshCw, AlertCircle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useRouter } from "next/navigation";

type QueueAsset = {
  version_id: string;
  asset_id: string;
  asset_name: string;
  project_id: string;
  project_name: string;
  version_number: number;
  processing_status: string;
  created_at: string;
};

function stalledMinutes(createdAt: string): number {
  return Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000);
}

export default function QueueDetailPage() {
  const { isSuperAdmin, user } = useAuthStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "processing";

  const swrKey = isSuperAdmin ? `/admin/queue/assets?status=${status}` : null;
  const { data, isLoading, mutate: refresh } = useSWR<QueueAsset[]>(
    swrKey,
    () => api.get<QueueAsset[]>(`/admin/queue/assets?processing_status=${status}`),
    { refreshInterval: 10000 },
  );

  const [reprocessing, setReprocessing] = React.useState<Record<string, boolean>>({});

  React.useEffect(() => {
    if (user && !isSuperAdmin) router.replace("/");
  }, [user, isSuperAdmin, router]);

  const handleReprocess = async (item: QueueAsset, priority = false) => {
    setReprocessing((prev) => ({ ...prev, [item.version_id]: true }));
    try {
      await api.post(`/assets/${item.asset_id}/versions/${item.version_id}/reprocess?priority=${priority}`);
      await refresh();
      mutate(`/admin/queue`);
    } finally {
      setReprocessing((prev) => ({ ...prev, [item.version_id]: false }));
    }
  };

  const handleReprocessAll = async () => {
    if (!data) return;
    for (const item of data) {
      setReprocessing((prev) => ({ ...prev, [item.version_id]: true }));
      try {
        await api.post(`/assets/${item.asset_id}/versions/${item.version_id}/reprocess`);
      } catch {
        // continue with others
      }
    }
    await refresh();
    mutate(`/admin/queue`);
    setReprocessing({});
  };

  const title = status === "failed" ? "Failed" : "Processing";
  const statusColor =
    status === "failed" ? "text-status-error" : "text-status-warning";

  if (!isSuperAdmin) return null;

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/settings/admin"
          className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Admin
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            <span className={statusColor}>{data?.length ?? "—"}</span>{" "}
            {title} Assets
          </h1>
          <p className="text-sm text-text-secondary mt-0.5">
            {status === "failed"
              ? "Files are in Backblaze — click Reprocess to re-run transcoding."
              : "Assets currently in the processing queue."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refresh()}
            className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-primary border border-border rounded-md px-3 py-1.5 transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
          {status === "failed" && data && data.length > 0 && (
            <button
              onClick={handleReprocessAll}
              className="flex items-center gap-1.5 text-xs text-text-primary bg-accent hover:bg-accent/90 rounded-md px-3 py-1.5 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              Reprocess All
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-bg-tertiary" />
          ))}
        </div>
      ) : !data || data.length === 0 ? (
        <div className="rounded-lg border border-border bg-bg-secondary flex items-center justify-center py-16">
          <div className="flex flex-col items-center gap-2 text-center">
            <AlertCircle className="h-8 w-8 text-text-tertiary" />
            <p className="text-sm text-text-secondary">No {title.toLowerCase()} assets</p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-bg-secondary overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-tertiary">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">Asset</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary hidden sm:table-cell">Project</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary hidden md:table-cell">Version</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary hidden md:table-cell">Age</th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-text-tertiary">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((item) => {
                  const mins = stalledMinutes(item.created_at);
                  const isReprocessing = reprocessing[item.version_id];
                  return (
                    <tr key={item.version_id} className="hover:bg-bg-tertiary/50 transition-colors">
                      <td className="px-4 py-3">
                        <Link
                          href={`/projects/${item.project_id}/assets/${item.asset_id}`}
                          className="text-xs font-medium text-text-primary hover:text-accent transition-colors truncate max-w-[200px] block"
                        >
                          {item.asset_name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="text-xs text-text-secondary">{item.project_name}</span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <span className="text-xs text-text-tertiary">v{item.version_number}</span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <span className={cn(
                          "text-xs",
                          mins > 60 ? "text-status-error" : mins > 10 ? "text-status-warning" : "text-text-tertiary"
                        )}>
                          {mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            onClick={() => handleReprocess(item, true)}
                            disabled={isReprocessing}
                            title="Jump to front of queue"
                            className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent/80 border border-accent/30 rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
                          >
                            {isReprocessing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                            Priority
                          </button>
                          <button
                            onClick={() => handleReprocess(item, false)}
                            disabled={isReprocessing}
                            className="inline-flex items-center gap-1 text-xs text-text-tertiary hover:text-text-primary border border-border rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
                          >
                            <RefreshCw className="h-3 w-3" />
                            Normal
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
