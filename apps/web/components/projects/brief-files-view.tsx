"use client";

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { FileImage, FolderOpen, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/shared/empty-state";
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
}

// A brief opened from a folder: every editor's submitted files on one screen.
// Each editor's work lives in that editor's own project, so the files are read
// from there and open in that project's file page.
export function BriefFilesView({ briefId }: BriefFilesViewProps) {
  const { data: subs, isLoading } = useSWR<BriefSubmission[]>(
    `/submission-links/${briefId}/submissions`,
    (key: string) => api.get<BriefSubmission[]>(key),
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex justify-end">
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
        subs.map((s) => <EditorFiles key={s.id} submission={s} />)
      )}
    </div>
  );
}

function EditorFiles({ submission }: { submission: BriefSubmission }) {
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
            <Link
              key={a.id}
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
