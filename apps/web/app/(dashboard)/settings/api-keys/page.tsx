"use client";

import * as React from "react";
import useSWR, { mutate } from "swr";
import * as Dialog from "@radix-ui/react-dialog";
import { KeyRound, Plus, X, Copy, Check, AlertTriangle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/shared/empty-state";
import { useToast } from "@/components/shared/toast";
import { useAuthStore } from "@/stores/auth-store";
import { useRouter } from "next/navigation";
import type { APIKey, APIKeyCreated } from "@/types";

const KEYS_ENDPOINT = "/admin/api-keys";

function CreateKeyDialog() {
  const toast = useToast();
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  // Once created, hold the full plaintext key to show exactly once.
  const [created, setCreated] = React.useState<APIKeyCreated | null>(null);
  const [copied, setCopied] = React.useState(false);

  const reset = () => {
    setName("");
    setError("");
    setCreated(null);
    setCopied(false);
    setLoading(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError("");
    try {
      const key = await api.post<APIKeyCreated>(KEYS_ENDPOINT, { name: name.trim() });
      setCreated(key);
      mutate(KEYS_ENDPOINT);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    } finally {
      setLoading(false);
    }
  };

  const copyKey = async () => {
    if (!created) return;
    await navigator.clipboard.writeText(created.key);
    setCopied(true);
    toast.success("API key copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <Dialog.Trigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" />
          Create API Key
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary p-6 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Close className="absolute right-4 top-4 text-text-tertiary hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </Dialog.Close>

          {!created ? (
            <>
              <Dialog.Title className="text-base font-semibold text-text-primary">
                Create API Key
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Give the key a name so you can recognise it later (e.g. the
                platform that will use it).
              </Dialog.Description>

              <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text-secondary">
                    Name
                  </label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Meta uploader"
                    autoFocus
                  />
                </div>
                {error && <p className="text-xs text-status-error">{error}</p>}
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={loading}>
                    Create Key
                  </Button>
                </div>
              </form>
            </>
          ) : (
            <>
              <Dialog.Title className="text-base font-semibold text-text-primary">
                API Key created
              </Dialog.Title>
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-status-warning/30 bg-status-warning/10 p-3">
                <AlertTriangle className="h-4 w-4 shrink-0 text-status-warning mt-0.5" />
                <p className="text-xs text-text-secondary">
                  Copy this key now — for security it will{" "}
                  <span className="font-medium text-text-primary">
                    never be shown again
                  </span>
                  . If you lose it, revoke it and create a new one.
                </p>
              </div>

              <div className="mt-3 flex items-center gap-2 rounded-lg border border-border bg-bg-tertiary p-2.5">
                <code className="flex-1 break-all font-mono text-xs text-text-primary">
                  {created.key}
                </code>
                <button
                  type="button"
                  onClick={copyKey}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-tertiary hover:bg-bg-hover hover:text-text-primary transition-colors"
                  title="Copy key"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-status-success" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
              </div>

              <div className="mt-4 flex justify-end">
                <Button size="sm" onClick={() => setOpen(false)}>
                  Done
                </Button>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function ApiKeysPage() {
  const { user, isSuperAdmin } = useAuthStore();
  const router = useRouter();
  const toast = useToast();

  const { data: keys, isLoading } = useSWR<APIKey[]>(
    isSuperAdmin ? KEYS_ENDPOINT : null,
    () => api.get<APIKey[]>(KEYS_ENDPOINT),
  );

  React.useEffect(() => {
    if (user && !isSuperAdmin) {
      router.replace("/");
    }
  }, [user, isSuperAdmin, router]);

  const baseUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/api/public/v1`
      : "/api/public/v1";

  const handleRevoke = async (key: APIKey) => {
    if (
      !confirm(
        `Revoke "${key.name}"? Any platform using this key will immediately lose access.`,
      )
    )
      return;
    try {
      await api.delete(`${KEYS_ENDPOINT}/${key.id}`);
      mutate(KEYS_ENDPOINT);
      toast.success("API key revoked");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke key");
    }
  };

  const copyEndpoint = async () => {
    await navigator.clipboard.writeText(`${baseUrl}/videos`);
    toast.success("Endpoint URL copied");
  };

  if (!isSuperAdmin) {
    return null;
  }

  return (
    <div className="p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-muted">
          <KeyRound className="h-5 w-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-text-primary">API Keys</h1>
          <p className="text-sm text-text-secondary">
            Grant external platforms read access to your videos
          </p>
        </div>
      </div>

      {/* How to use */}
      <section className="rounded-lg border border-border bg-bg-secondary p-5 space-y-3">
        <h2 className="text-sm font-semibold text-text-primary">Using the API</h2>
        <p className="text-sm text-text-secondary">
          Send your key in the{" "}
          <code className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-text-primary">
            X-API-Key
          </code>{" "}
          header. List and search videos, then download the originals to push
          elsewhere (e.g. the Meta API).
        </p>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-tertiary p-2.5">
          <code className="flex-1 break-all font-mono text-xs text-text-primary">
            GET {baseUrl}/videos
          </code>
          <button
            type="button"
            onClick={copyEndpoint}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-tertiary hover:bg-bg-hover hover:text-text-primary transition-colors"
            title="Copy endpoint URL"
          >
            <Copy className="h-4 w-4" />
          </button>
        </div>
        <p className="text-xs text-text-tertiary">
          Filters:{" "}
          <code className="font-mono">search</code> (name),{" "}
          <code className="font-mono">author</code> (name or email),{" "}
          <code className="font-mono">status</code>,{" "}
          <code className="font-mono">page</code>,{" "}
          <code className="font-mono">per_page</code>. Each result includes a
          ready-to-use <code className="font-mono">download_url</code>. Download
          a single video directly via{" "}
          <code className="font-mono">GET {baseUrl}/videos/{"{id}"}/download</code>
          .
        </p>
      </section>

      {/* Keys table */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">Keys</h2>
          <CreateKeyDialog />
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-lg bg-bg-tertiary"
              />
            ))}
          </div>
        ) : !keys || keys.length === 0 ? (
          <div className="rounded-lg border border-border bg-bg-secondary">
            <EmptyState
              icon={KeyRound}
              title="No API keys yet"
              description="Create a key to let an external platform pull your videos."
            />
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-bg-secondary overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-tertiary">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">
                    Name
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">
                    Key
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">
                    Last used
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">
                    Created
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-text-tertiary">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr
                    key={k.id}
                    className="border-b border-border last:border-0 hover:bg-bg-tertiary transition-colors"
                  >
                    <td className="px-4 py-3">
                      <p className="text-sm font-medium text-text-primary">
                        {k.name}
                      </p>
                      {k.created_by_name && (
                        <p className="text-xs text-text-tertiary">
                          by {k.created_by_name}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <code className="font-mono text-xs text-text-secondary">
                        {k.key_prefix}…
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      {k.is_active ? (
                        <span className="inline-flex items-center rounded-full bg-status-success/15 px-2 py-0.5 text-xs font-medium text-status-success">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-status-error/15 px-2 py-0.5 text-xs font-medium text-status-error">
                          Revoked
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-tertiary">
                      {k.last_used_at
                        ? new Date(k.last_used_at).toLocaleString()
                        : "Never"}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-tertiary">
                      {new Date(k.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end">
                        {k.is_active ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRevoke(k)}
                            className="gap-1 text-status-error hover:text-status-error"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Revoke
                          </Button>
                        ) : (
                          <span className="text-xs text-text-tertiary italic">
                            —
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
