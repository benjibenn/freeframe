"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { useUploadStore } from "@/stores/upload-store";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { CommandPalette } from "@/components/layout/command-palette";
import { UploadsPanel } from "@/components/layout/uploads-panel";
import { UploadSSEBridge } from "@/components/layout/upload-sse-bridge";
import { cn } from "@/lib/utils";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(true);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
  const [commandOpen, setCommandOpen] = React.useState(false);
  const { fetchUser } = useAuthStore();
  const { fetchHistory } = useUploadStore();

  // Hide header on asset viewer pages — the viewer has its own top bar
  const isAssetViewer = /\/projects\/[^/]+\/assets\/[^/]+/.test(pathname);

  // Close the mobile nav drawer whenever the route changes.
  React.useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    fetchUser();
    fetchHistory();
  }, [fetchUser, fetchHistory]);

  // Global keyboard shortcut for command palette
  React.useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />

      {/* Backdrop for the mobile nav drawer */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Main content area. No left margin on mobile (drawer overlays); the
          sidebar offset only applies at md+ where it's persistent. */}
      <main
        className={cn(
          "flex flex-1 flex-col overflow-hidden transition-[margin] duration-200 ease-spring",
          "ml-0",
          sidebarCollapsed ? "md:ml-[52px]" : "md:ml-[220px]",
        )}
      >
        {!isAssetViewer && (
          <Header
            onSearchOpen={() => setCommandOpen(true)}
            onMenuOpen={() => setMobileNavOpen(true)}
          />
        )}

        <div className="relative flex-1 overflow-y-auto">{children}</div>
      </main>

      <UploadsPanel />
      <UploadSSEBridge />
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
