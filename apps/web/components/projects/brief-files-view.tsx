"use client";

import * as React from "react";
import Link from "next/link";
import useSWR, { useSWRConfig } from "swr";
import { Download, FileImage, FolderOpen, Loader2, Settings2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { getAccessToken, refreshAccessToken } from "@/lib/auth";
import { useToast } from "@/components/shared/toast";
import { EmptyState } from "@/components/shared/empty-state";
import { BulkStatusMenu } from "@/components/projects/bulk-status-menu";
import type { AssetResponse } from "@/types";

// One editor's submission against a brief (GET /submission-links/{id}/submissions).
interface BriefSubmission {
  id: string;
  user_name: string;
  user_email: string;
  display_name: string | null;
  project_id: string;
  asset_count: number;
}

interface BriefFilesViewProps {
  briefId: string;
  /** Names the ZIP; the files inside are named by the API. */
  briefTitle: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Every file of the brief as one ZIP, each named "<brief title> - <language>". */
async function downloadBriefZip(briefId: string, briefTitle: string): Promise<void> {
  const path = `${API_URL}/submission-links/${briefId}/download-all`;
  const get = (token: string | null) =>
    fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  let res = await get(getAccessToken());
  if (res.status === 401) {
    const token = await refreshAccessToken();
    if (token) res = await get(token);
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `${briefTitle.replace(/[\\/:*?"<>|]/g, "").trim() || "Brief"}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

/** One file, saved as "<brief title> - <language>" (named by the API's presigned URL). */
async function downloadBriefFile(briefId: string, assetId: string): Promise<void> {
  const { url } = await api.get<{ url: string }>(
    `/submission-links/${briefId}/files/${assetId}/download`,
  );
  const iframe = document.createElement("iframe");
  iframe.style.display = "none";
  iframe.src = url;
  document.body.appendChild(iframe);
  setTimeout(() => iframe.remove(), 30000);
}

// A brief opened from a folder: every editor's submitted files on one screen.
// Each editor's work lives in that editor's own project, so the files are read
// from there and open in that project's file page.
export function BriefFilesView({ briefId, briefTitle }: BriefFilesViewProps) {
  const toast = useToast();
  const { mutate } = useSWRConfig();
  const [zipping, setZipping] = React.useState(false);
  const { data: subs, isLoading } = useSWR<BriefSubmission[]>(
    `/submission-links/${briefId}/submissions`,
    (key: string) => api.get<BriefSubmission[]>(key),
  );
  const totalFiles = (subs ?? []).reduce((n, s) => n + s.asset_count, 0);

  const downloadAll = async () => {
    setZipping(true);
    try {
      await downloadBriefZip(briefId, briefTitle);
    } catch {
      toast.error("Download failed. Try again.");
    } finally {
      setZipping(false);
    }
  };
  const downloadOne = (assetId: string) =>
    downloadBriefFile(briefId, assetId).catch(() => toast.error("Download failed. Try again."));

  // The brief's files sit in each submitter's own project, so the stage is set
  // server-side by brief. Each editor section is its own SWR key, so they are
  // revalidated one by one once the call lands.
  const setStage = async (stageId: string | null) => {
    try {
      const { updated } = await api.patch<{ updated: number }>(
        "/submission-links/bulk/stage",
        { link_ids: [briefId], task_stage_id: stageId },
      );
      await Promise.all(
        (subs ?? []).map((s) => mutate(`/projects/${s.project_id}/assets`)),
      );
      toast.success(
        updated
          ? `Status set on ${updated} file${updated === 1 ? "" : "s"}`
          : "This brief has no files",
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Bulk status failed");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-end gap-4">
        {/* Renders nothing for non-admins (the menu self-gates). */}
        <BulkStatusMenu
          side="bottom"
          label="Bulk status"
          scopeHint="Every file in this brief (all editors)"
          triggerClassName="border border-border bg-bg-secondary px-3 text-xs"
          onSetStage={setStage}
        />
        {totalFiles > 0 && (
          <button
            type="button"
            onClick={downloadAll}
            disabled={zipping}
            className="rounded-md border border-border bg-bg-secondary px-3 h-8 inline-flex items-center gap-1.5 text-xs font-medium text-text-secondary hover:text-text-primary disabled:opacity-50"
          >
            {zipping ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            {zipping ? "Preparing ZIP…" : `Download all (${totalFiles})`}
          </button>
        )}
        <Link
          href={`/projects/requests/${briefId}`}
          className="inline-flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary"
        >
          <Settings2 className="h-3.5 w-3.5" />
          Brief settings
        </Link>
      </div>
      {isLoading ? (
        <TileSkeletons />
      ) : !subs || subs.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No submissions yet"
          description="Files appear here when an editor submits work against this brief."
        />
      ) : (
        subs.map((s) => <EditorFiles key={s.id} submission={s} onDownload={downloadOne} />)
      )}
    </div>
  );
}

function EditorFiles({
  submission,
  onDownload,
}: {
  submission: BriefSubmission;
  onDownload: (assetId: string) => void;
}) {
  const { data: assets, isLoading } = useSWR<AssetResponse[]>(
    `/projects/${submission.project_id}/assets`,
    (key: string) => api.get<AssetResponse[]>(key),
  );
  const label =
    submission.display_name || submission.user_name || submission.user_email;

  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-medium text-text-secondary">
        {label}
        <span className="ml-2 text-2xs text-text-tertiary">
          {submission.asset_count} file{submission.asset_count !== 1 ? "s" : ""}
        </span>
      </h3>
      {isLoading ? (
        <TileSkeletons />
      ) : !assets || assets.length === 0 ? (
        <p className="text-xs text-text-tertiary">No files yet.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {assets.map((a) => (
            <div key={a.id} className="group relative">
            <Link
              href={`/projects/${submission.project_id}/assets/${a.id}`}
              className="block rounded-xl overflow-hidden bg-bg-secondary border border-border hover:border-accent/40 transition-all duration-200"
            >
              <div className="relative aspect-square w-full overflow-hidden bg-bg-tertiary">
                {a.thumbnail_url ? (
                  <img
                    src={a.thumbnail_url}
                    alt={a.name}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <FileImage className="h-10 w-10 text-text-tertiary" />
                  </div>
                )}
              </div>
              <p className="px-3 py-2.5 text-xs text-text-primary line-clamp-2">
                {a.name}
              </p>
            </Link>
            <button
              type="button"
              onClick={() => onDownload(a.id)}
              aria-label={`Download ${a.name}`}
              title="Download"
              className="absolute right-2 top-2 rounded-full bg-black/50 p-1.5 text-white transition-colors hover:bg-black/70"
            >
              <Download className="h-4 w-4" />
            </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function TileSkeletons() {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="aspect-square animate-pulse rounded-xl bg-bg-tertiary" />
      ))}
    </div>
  );
}
