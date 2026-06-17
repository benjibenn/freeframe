"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "@/lib/api";
import { useReviewStore } from "@/stores/review-store";
import type { AssetResponse, AssetVersion, Comment } from "@/types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CreateCommentPayload {
  body: string;
  version_id?: string;
  parent_id?: string;
  timecode_start?: number;
  timecode_end?: number;
  annotation?: { drawing_data: Record<string, unknown> };
}

interface ReviewContextValue {
  assetId: string;
  asset: AssetResponse | null;
  shareToken?: string;
  shareSession?: string | null;
  versions: AssetVersion[];
  comments: Comment[];
  isLoading: boolean;
  error: string | null;
  addComment: (payload: CreateCommentPayload) => Promise<Comment>;
  resolveComment: (commentId: string) => Promise<void>;
  seekTo: (time: number) => void;
  refetchComments: () => Promise<void>;
  refetchVersions: () => Promise<void>;
  pauseVideo: () => void;
  registerPauseHandler: (handler: () => void) => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const ReviewContext = createContext<ReviewContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

interface ReviewProviderProps {
  assetId: string;
  shareToken?: string; // If set, uses share token API instead of authenticated API
  shareSession?: string | null;
  children: React.ReactNode;
}

export function ReviewProvider({
  assetId,
  shareToken,
  shareSession,
  children,
}: ReviewProviderProps) {
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [versions, setVersions] = useState<AssetVersion[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pauseHandlerRef = useRef<(() => void) | null>(null);

  const { currentVersion, setCurrentAsset, setCurrentVersion, setPlayheadTime } =
    useReviewStore();

  // Track whether component is still mounted to avoid state updates after unmount
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const shareSessionParam = shareSession ? `&share_session=${encodeURIComponent(shareSession)}` : '';

  const fetchAsset = useCallback(async () => {
    try {
      let data: AssetResponse;

      if (shareToken) {
        // Share mode: fetch stream info to build a pseudo asset
        const API_URL =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const headers: Record<string, string> = {};
        try {
          const t = localStorage.getItem("ff_access_token");
          if (t) headers["Authorization"] = `Bearer ${t}`;
        } catch {}
        const streamRes = await fetch(
          `${API_URL}/share/${shareToken}/stream/${assetId}?_=1${shareSessionParam}`,
          { headers },
        );
        const streamData = streamRes.ok ? await streamRes.json() : null;
        // Build pseudo asset from available data
        data = {
          id: assetId,
          name: streamData?.name || "Asset",
          description: null,
          asset_type: streamData?.asset_type || "image",
          status: "in_review",
          rating: null,
          assignee_id: null,
          folder_id: null,
          due_date: null,
          keywords: [],
          project_id: "",
          created_by: "",
          created_at: "",
          updated_at: "",
          deleted_at: null,
          stream_url: streamData?.url,
          thumbnail_url: streamData?.thumbnail_url,
          latest_version: streamData?.version_id
            ? {
                id: streamData.version_id,
                asset_id: assetId,
                version_number: 1,
                processing_status: "ready",
                created_by: "",
                created_at: "",
                deleted_at: null,
                files: [],
              }
            : null,
        } as AssetResponse;
      } else {
        // Normal mode: authenticated API
        data = await api.get<AssetResponse>(`/assets/${assetId}`);
      }

      if (!mountedRef.current) return;
      setAsset(data);
      setCurrentAsset(data);

      if (!shareToken) {
        // Fetch all versions for the version switcher (not available in share mode)
        const allVersions = await api.get<AssetVersion[]>(
          `/assets/${assetId}/versions`,
        );
        if (!mountedRef.current) return;
        setVersions(allVersions ?? []);

        const readyVersion = (allVersions ?? [])
          .sort((a, b) => b.version_number - a.version_number)
          .find((v) => v.processing_status === "ready");
        if (readyVersion) {
          setCurrentVersion(readyVersion);
        } else if (data.latest_version) {
          setCurrentVersion(data.latest_version);
        }
      } else {
        // Share mode: load the asset's versions for the switcher. The share
        // endpoint returns ready-only versions newest-first and caps the list
        // to one when the link disables version history, so the UI hides the
        // switcher when fewer than two come back.
        try {
          const API_URL =
            process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          const headers: Record<string, string> = {};
          try {
            const t = localStorage.getItem("ff_access_token");
            if (t) headers["Authorization"] = `Bearer ${t}`;
          } catch {}
          const qs = shareSessionParam ? `?${shareSessionParam.slice(1)}` : "";
          const vRes = await fetch(
            `${API_URL}/share/${shareToken}/assets/${assetId}/versions${qs}`,
            { headers },
          );
          const vData: Array<{
            id: string;
            version_number: number;
            processing_status: AssetVersion["processing_status"];
            created_at: string | null;
          }> = vRes.ok ? await vRes.json() : [];
          if (!mountedRef.current) return;
          if (Array.isArray(vData) && vData.length > 0) {
            const mapped: AssetVersion[] = vData.map((v) => ({
              id: v.id,
              asset_id: assetId,
              version_number: v.version_number,
              processing_status: v.processing_status,
              created_by: "",
              created_at: v.created_at ?? "",
              deleted_at: null,
            }));
            setVersions(mapped);
            setCurrentVersion(mapped[0]); // endpoint returns newest-first
          } else if (data.latest_version) {
            setCurrentVersion(data.latest_version);
          }
        } catch {
          if (data.latest_version) setCurrentVersion(data.latest_version);
        }
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err.message : "Failed to load asset");
    }
  }, [assetId, shareToken, shareSessionParam, setCurrentAsset, setCurrentVersion]);

  const fetchComments = useCallback(async () => {
    try {
      let data: Comment[];
      if (shareToken) {
        const API_URL =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        // Scope comments to the selected version so switching versions shows
        // only that version's comments (the endpoint returns all when omitted).
        const versionQs = currentVersion?.id
          ? `&version_id=${currentVersion.id}`
          : "";
        const res = await fetch(
          `${API_URL}/share/${shareToken}/comments?asset_id=${assetId}${versionQs}${shareSessionParam}`,
        );
        if (res.ok) {
          const json = await res.json();
          // Handle both formats: array directly or {comments: [...]}
          data = Array.isArray(json) ? json : (json.comments ?? []);
        } else {
          data = [];
        }
      } else {
        data = await api.get<Comment[]>(`/assets/${assetId}/comments`);
      }
      if (!mountedRef.current) return;
      setComments(data ?? []);
    } catch {
      // Comments failing silently — asset is still viewable
    }
  }, [assetId, shareToken, shareSessionParam, currentVersion?.id]);

  const refetchComments = useCallback(async () => {
    await fetchComments();
  }, [fetchComments]);

  const refetchVersions = useCallback(async () => {
    if (shareToken) return;
    try {
      const allVersions = await api.get<AssetVersion[]>(`/assets/${assetId}/versions`);
      if (!mountedRef.current) return;
      setVersions(allVersions ?? []);
    } catch {
      // ignore
    }
  }, [assetId, shareToken]);

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    fetchAsset().finally(() => {
      if (mountedRef.current) setIsLoading(false);
    });
  }, [fetchAsset]);

  // Load comments independently of the asset so a version switch (which changes
  // fetchComments via currentVersion) re-fetches comments WITHOUT re-running
  // fetchAsset — re-running fetchAsset would reset currentVersion and loop.
  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  const addComment = useCallback(
    async (payload: CreateCommentPayload): Promise<Comment> => {
      let comment: Comment;
      if (shareToken) {
        const API_URL =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        try {
          const t = localStorage.getItem("ff_access_token");
          if (t) headers["Authorization"] = `Bearer ${t}`;
        } catch {}
        // Include guest identity if available (for non-authenticated users)
        const guestFields: Record<string, string> = {};
        try {
          const stored = localStorage.getItem("ff_guest_identity");
          if (stored) {
            const guest = JSON.parse(stored);
            guestFields.guest_name = guest.name;
            guestFields.guest_email = guest.email;
          }
        } catch {}
        const res = await fetch(`${API_URL}/share/${shareToken}/comment?_=1${shareSessionParam}`, {
          method: "POST",
          headers,
          body: JSON.stringify({ ...payload, ...guestFields, asset_id: assetId }),
        });
        if (!res.ok) throw new Error("Failed to post comment");
        comment = await res.json();
      } else {
        comment = await api.post<Comment>(
          `/assets/${assetId}/comments`,
          payload,
        );
      }
      if (mountedRef.current) {
        setComments((prev) => [...prev, comment]);
      }
      return comment;
    },
    [assetId],
  );

  const resolveComment = useCallback(
    async (commentId: string): Promise<void> => {
      await api.post(`/comments/${commentId}/resolve`);
      if (mountedRef.current) {
        setComments((prev) =>
          prev.map((c) => (c.id === commentId ? { ...c, resolved: true } : c)),
        );
      }
    },
    [],
  );

  const seekTo = useCallback(
    (time: number) => {
      setPlayheadTime(time);
    },
    [setPlayheadTime],
  );

  const pauseVideo = useCallback(() => {
    if (pauseHandlerRef.current) {
      pauseHandlerRef.current();
    }
  }, []);

  const registerPauseHandler = useCallback((handler: () => void) => {
    pauseHandlerRef.current = handler;
  }, []);

  const value = useMemo<ReviewContextValue>(
    () => ({
      assetId,
      asset,
      shareToken,
      shareSession,
      versions,
      comments,
      isLoading,
      error,
      addComment,
      resolveComment,
      seekTo,
      refetchComments,
      refetchVersions,
      pauseVideo,
      registerPauseHandler,
    }),
    [
      assetId,
      asset,
      versions,
      comments,
      isLoading,
      error,
      addComment,
      resolveComment,
      seekTo,
      refetchComments,
      refetchVersions,
      pauseVideo,
      registerPauseHandler,
    ],
  );

  return (
    <ReviewContext.Provider value={value}>{children}</ReviewContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useReview(): ReviewContextValue {
  const ctx = useContext(ReviewContext);
  if (!ctx) {
    throw new Error("useReview must be used inside <ReviewProvider>");
  }
  return ctx;
}
