import { Suspense } from "react";
import { AppShell } from "@/components/shell";

// The whole app is client-rendered behind a sign-in, so the shell streams in after a tiny static frame.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page" />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
