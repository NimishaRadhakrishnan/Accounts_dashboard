"use client";

import {
  ArrowLeftRight, BarChart3, Clock3, FileText, Home, KeyRound, LogOut, Menu, Settings, ShoppingCart, Wallet, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";
import { fyRange, today } from "@/lib/format";
import { ConfirmProvider, cx, Spinner, ToastProvider, useConfirm } from "./ui";

// Every menu item says in plain words what is inside it, so nobody needs a guided tour.
const NAV = [
  { href: "/", label: "Home", hint: "Today's summary", icon: Home, perm: ["dashboard.view"] },
  { href: "/sales", label: "Sales & Invoices", hint: "Bills we give to dealers", icon: FileText, perm: ["sales.view"] },
  { href: "/purchases", label: "Purchase Bills", hint: "Bills we get from suppliers", icon: ShoppingCart, perm: ["purchases.view"] },
  { href: "/payments", label: "Payments & Receipts", hint: "Money in and money out", icon: ArrowLeftRight, perm: ["receipts.view", "payments.view"] },
  { href: "/expenses", label: "Expenses", hint: "Office and daily spending", icon: Wallet, perm: ["expenses.view"] },
  { href: "/outstanding", label: "Outstanding", hint: "Who owes us, whom we owe", icon: Clock3, perm: ["outstanding.view"] },
  { href: "/reports", label: "Reports", hint: "Excel and PDF reports", icon: BarChart3, perm: ["reports.view"] },
  { href: "/settings", label: "Settings", hint: "Dealers, products, users", icon: Settings, perm: ["masters.view", "settings.manage", "users.manage", "audit.view"] },
];

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
    <div className="flex items-center gap-1.5" role="group" aria-label="Text size">
      <span className="hidden text-sm text-muted md:inline">Text size</span>
      <div className="flex overflow-hidden rounded-lg border-2 border-soft bg-white">
        {SIZES.map((s, i) => (
          <button key={s.v} onClick={() => setSize(s.v)} aria-label={s.aria} aria-pressed={size === s.v} title={s.aria}
            className={cx("min-h-10 min-w-11 px-2.5 font-semibold transition-colors", i > 0 && "border-l-2 border-soft",
              size === s.v ? "bg-sidebar text-white" : "text-ink hover:bg-soft-2", ["text-sm", "text-base", "text-lg"][i])}>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { me, can, logout } = useAuth();
  const confirm = useConfirm();
  const path = usePathname();
  const items = NAV.filter((n) => n.perm.some(can));
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-ink/40 lg:hidden" onClick={onClose} />}
      <aside className={cx("fixed inset-y-0 left-0 z-40 flex w-72 flex-col overflow-y-auto bg-sidebar text-white transition-transform lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-3 px-5 pb-5 pt-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-xl font-bold">V</div>
          <div className="leading-tight">
            <div className="text-lg font-semibold">Vishakan Bio Tech</div>
            <div className="text-sm text-white/75">Accounts Department</div>
          </div>
          <button className="ml-auto inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-white/80 lg:hidden" onClick={onClose} aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Main menu">
          {items.map(({ href, label, hint, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} onClick={onClose} aria-current={active ? "page" : undefined}
                className={cx("flex items-center gap-3 rounded-lg border-l-4 px-3 py-2.5 transition-colors",
                  active ? "border-accent bg-white/12 text-white" : "border-transparent text-white/85 hover:bg-white/8 hover:text-white")}>
                <Icon className="h-6 w-6 shrink-0" strokeWidth={1.8} />
                <span className="leading-tight">
                  <span className={cx("block text-base", active && "font-semibold")}>{label}</span>
                  <span className="block text-sm text-white/65">{hint}</span>
                </span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 border-t border-white/15 px-5 py-5">
          <div className="text-sm text-white/65">Signed in as</div>
          <div className="text-base font-semibold">{me?.full_name}</div>
          <div className="text-sm text-white/75">{me?.role.name}</div>
          <div className="mt-4 grid gap-2">
            <Link href="/change-password" onClick={onClose} className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-base text-white/85 hover:bg-white/8">
              <KeyRound className="h-5 w-5" /> Change my password
            </Link>
            <button onClick={async () => { if (await confirm({ title: "Sign out?", message: "You will need your username and password to come back in.", yes: "Yes, sign out" })) logout(); }}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border-2 border-white/25 px-3 text-base font-medium hover:bg-white/10">
              <LogOut className="h-5 w-5" /> Sign out
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const fy = fyRange();
  const label = `Year ${fy.from.slice(0, 4)}–${fy.to.slice(2, 4)}`;
  const t = new Date(today()).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return (
    <header className="sticky top-0 z-20 flex min-h-16 items-center gap-3 border-b border-line bg-page/95 px-4 backdrop-blur lg:px-8">
      <button className="inline-flex min-h-11 items-center gap-2 rounded-lg border-2 border-soft bg-white px-3 text-base font-medium lg:hidden" onClick={onMenu}>
        <Menu className="h-5 w-5" /> Menu
      </button>
      <div className="hidden text-base text-ink sm:block">Today is <span className="font-semibold">{t}</span></div>
      <div className="ml-auto flex items-center gap-4">
        <span className="hidden rounded-full bg-soft px-3 py-1 text-sm font-medium text-ink md:inline" title="Financial year (April to March)">{label}</span>
        <TextSize />
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
  const [open, setOpen] = useState(false);
  return (
    <AuthProvider>
      <ToastProvider>
        <ConfirmProvider>
          <Guard>
            <Sidebar open={open} onClose={() => setOpen(false)} />
            <div className="lg:pl-72">
              <Topbar onMenu={() => setOpen(true)} />
              <main className="mx-auto max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">{children}</main>
            </div>
          </Guard>
        </ConfirmProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
