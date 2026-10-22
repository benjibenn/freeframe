import { ApiError } from "@/lib/api";
import { getAccessToken, refreshAccessToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Every file of the chosen briefs as one ZIP, a folder per brief.
 *
 * Not the iframe trick the asset downloads use: that works only for a GET to a
 * presigned URL, and the selection can be longer than a URL should carry, so the
 * brief ids go in a POST body. That means fetching the bytes here and handing the
 * browser a blob, including the 401-then-refresh retry the single-brief ZIP does.
 */
export async function downloadBriefsZip(linkIds: string[]): Promise<void> {
  const post = (token: string | null) =>
    fetch(`${API_URL}/submission-links/bulk/download`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ link_ids: linkIds }),
    });

  let res = await post(getAccessToken());
  if (res.status === 401) {
    const token = await refreshAccessToken();
    if (token) res = await post(token);
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);

  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  // The API names the file too; this is the fallback when the header is dropped.
  a.download = linkIds.length === 1 ? "Brief.zip" : `${linkIds.length} briefs.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
