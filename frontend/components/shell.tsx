"use client";

import { KeyRound, LayoutDashboard, LogOut, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ConfirmProvider, cx, Spinner, ToastProvider, useConfirm } from "./ui";

type Size = "normal" | "large" | "xlarge";
const SIZES: { v: Size; label: string; aria: string }[] = [
  { v: "normal", label: "A", aria: "Normal text" },
  { v: "large", label: "A+", aria: "Bigger text" },
  { v: "xlarge", label: "A++", aria: "Biggest text" },
];

function TextSize() {
  const [size, setSize] = useState<Size>("normal");
  useEffect(() => {
    let saved: Size = "normal";
    try { saved = (localStorage.getItem("vbt-text-size") as Size) || "normal"; } catch { /* storage blocked */ }
    setSize(saved);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.text = size;
    try { localStorage.setItem("vbt-text-size", size); } catch { /* ignore */ }
  }, [size]);
  return (
    <div className="flex overflow-hidden rounded-lg border-2 border-white/25" role="group" aria-label="Text size">
      {SIZES.map((s, i) => (
        <button key={s.v} onClick={() => setSize(s.v)} aria-label={s.aria} aria-pressed={size === s.v} title={s.aria}
          className={cx("min-h-10 min-w-10 px-2 font-semibold transition-colors", i > 0 && "border-l-2 border-white/25",
            size === s.v ? "bg-white text-sidebar" : "text-white hover:bg-white/10", ["text-sm", "text-base", "text-lg"][i])}>
          {s.label}
        </button>
      ))}
    </div>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2.5 text-base text-white hover:bg-white/10">
        <UserRound className="h-5 w-5" /><span className="hidden md:inline">{me?.full_name.split(" ")[0]}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-xl border border-line bg-white text-ink shadow-xl">
          <div className="border-b border-line px-4 py-3">
            <div className="font-semibold">{me?.full_name}</div>
            <div className="text-sm text-muted">{me?.role.name}</div>
          </div>
          <Link href="/change-password" onClick={() => setOpen(false)} className="flex min-h-12 items-center gap-2.5 px-4 text-base hover:bg-soft-2">
            <KeyRound className="h-5 w-5" /> Change my password
          </Link>
          <button onClick={async () => { setOpen(false); if (await confirm({ title: "Sign out?", message: "You will need your username and password to come back in.", yes: "Yes, sign out" })) logout(); }}
            className="flex min-h-12 w-full items-center gap-2.5 px-4 text-left text-base hover:bg-soft-2">
            <LogOut className="h-5 w-5" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Topbar() {
  const { can } = useAuth();
  const path = usePathname();
  const links = [
    { href: "/", label: "Overview", icon: LayoutDashboard, show: true },
    { href: "/settings", label: "Settings", icon: Settings, show: can("settings.manage") || can("users.manage") || can("audit.view") },
  ].filter((l) => l.show);
  return (
    <header className="no-print sticky top-0 z-30 bg-sidebar text-white shadow-sm">
      <div className="mx-auto flex min-h-16 max-w-[1280px] items-center gap-3 px-4 lg:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-lg font-bold">V</span>
          <span className="hidden leading-tight sm:block">
            <span className="block text-base font-semibold">Vishakan Bio Tech</span>
            <span className="block text-sm text-white/70">Business overview</span>
          </span>
        </Link>
        {links.length > 1 && (
          <nav className="ml-2 flex gap-1" aria-label="Main">
            {links.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link key={href} href={href} aria-current={active ? "page" : undefined}
                  className={cx("inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-base", active ? "bg-white/15 font-semibold" : "text-white/80 hover:bg-white/10")}>
                  <Icon className="h-5 w-5" /><span className="hidden sm:inline">{label}</span>
                </Link>
              );
            })}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
          <TextSize />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function Guard({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (loading) return;
    if (!me) router.replace(`/login?next=${encodeURIComponent(path)}`);
    else if (me.must_change_password && path !== "/change-password") router.replace("/change-password");
  }, [me, loading, router, path]);
  if (loading || !me) return <div className="flex min-h-screen items-center justify-center"><Spinner /></div>;
  return <>{children}</>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <ConfirmProvider>
          <Guard>
            <Topbar />
            <main className="mx-auto max-w-[1280px] px-4 py-6 lg:px-8 lg:py-8">{children}</main>
          </Guard>
        </ConfirmProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
