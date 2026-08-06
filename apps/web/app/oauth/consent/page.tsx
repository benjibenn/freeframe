"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { KeyRound, ShieldCheck, ExternalLink, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth-store";

type ConsentInfo = {
  client_name: string;
  scopes: string[];
  redirect_uri: string;
};

type ConsentResult = { redirect_to: string };

const SCOPE_LABELS: Record<string, string> = {
  "briefs:read": "View video requests, projects and folders",
  "briefs:write": "Create, duplicate, re-file and edit video requests",
};

/**
 * OAuth consent screen.
 *
 * The authorization server parks the request and sends the browser here; no
 * authorization code exists until the button below is pressed, so abandoning
 * this page leaves nothing redeemable.
 *
 * Route auth is handled by middleware, which bounces a signed-out visitor to
 * /login?from=… carrying the query string — the request_id is the only thing
 * identifying which request is being approved.
 */
function ConsentScreen() {
  const params = useSearchParams();
  const requestId = params.get("request_id");
  const { user, isSuperAdmin, isSubAdmin, fetchUser } = useAuthStore();

  const [info, setInfo] = React.useState<ConsentInfo | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  React.useEffect(() => {
    if (!requestId) {
      setError("This link is missing its request id.");
      return;
    }
    api
      .get<ConsentInfo>(`/oauth/consent/${requestId}`)
      .then(setInfo)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "This request has expired."),
      );
  }, [requestId]);

  const decide = async (approve: boolean) => {
    if (!requestId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<ConsentResult>("/oauth/consent", {
        request_id: requestId,
        approve,
      });
      // Hand control back to the OAuth client. Deliberately a full navigation,
      // not a router push: the destination is outside this app.
      window.location.href = res.redirect_to;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not complete the request");
      setBusy(false);
    }
  };

  // Shown verbatim. The MCP authorization spec requires the redirect host on the
  // consent screen, because a loopback redirect can be claimed by any local
  // process — the user is the only one who can spot a wrong destination.
  let redirectHost = info?.redirect_uri ?? "";
  try {
    if (info) redirectHost = new URL(info.redirect_uri).host;
  } catch {
    /* keep the raw value if it will not parse */
  }
  const isLoopback = /^(localhost|127\.0\.0\.1)/.test(redirectHost);
  const canApprove = isSuperAdmin || isSubAdmin;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-4">
      <div className="w-full max-w-md space-y-6 rounded-xl border border-border bg-bg-secondary p-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-muted">
            <KeyRound className="h-5 w-5 text-accent" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-text-primary">
              Connect to Freeframe
            </h1>
            {user && (
              <p className="text-sm text-text-secondary">Signed in as {user.email}</p>
            )}
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-status-error/40 bg-status-error/10 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-error" />
            <p className="text-sm text-text-primary">{error}</p>
          </div>
        )}

        {info && (
          <>
            <p className="text-sm text-text-secondary">
              <span className="font-medium text-text-primary">{info.client_name}</span>{" "}
              wants to act on your behalf in Freeframe.
            </p>

            <div className="space-y-2 rounded-lg border border-border bg-bg-tertiary p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">
                It will be able to
              </p>
              <ul className="space-y-1.5">
                {info.scopes.map((s) => (
                  <li key={s} className="flex items-start gap-2 text-sm text-text-primary">
                    <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                    <span>{SCOPE_LABELS[s] ?? s}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-1 rounded-lg border border-border bg-bg-tertiary p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">
                You will be sent back to
              </p>
              <p className="flex items-center gap-1.5 break-all font-mono text-xs text-text-primary">
                <ExternalLink className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                {redirectHost}
              </p>
              {isLoopback && (
                <p className="text-xs text-status-warning">
                  This sends the approval to an application running on your own
                  computer. Only continue if you started this yourself.
                </p>
              )}
            </div>

            {!canApprove && (
              <div className="flex items-start gap-2 rounded-lg border border-status-error/40 bg-status-error/10 p-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-error" />
                <p className="text-sm text-text-primary">
                  Connecting a client needs admin access. Ask an administrator to
                  approve this instead.
                </p>
              </div>
            )}

            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="flex-1"
                disabled={busy}
                onClick={() => decide(false)}
              >
                Deny
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                disabled={busy || !canApprove}
                onClick={() => decide(true)}
              >
                Approve
              </Button>
            </div>
          </>
        )}

        {!info && !error && (
          <div className="h-24 animate-pulse rounded-lg bg-bg-tertiary" />
        )}
      </div>
    </div>
  );
}

/**
 * useSearchParams forces client-side rendering, which Next requires be fenced
 * off behind Suspense or the whole route fails to prerender.
 */
export default function OAuthConsentPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-bg-primary p-4">
          <div className="h-40 w-full max-w-md animate-pulse rounded-xl bg-bg-secondary" />
        </div>
      }
    >
      <ConsentScreen />
    </React.Suspense>
  );
}
