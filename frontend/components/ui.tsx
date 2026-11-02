"use client";

// Building blocks sized and worded for people who are not used to computers:
// large text and buttons, plain words, nothing hidden behind hover, and a clear
// message whenever something happens.

import { AlertTriangle, CheckCircle2, ChevronRight, Info, Loader2, X, XCircle } from "lucide-react";
import Link from "next/link";
import { createContext, forwardRef, useCallback, useContext, useEffect, useRef, useState } from "react";
import { inr, type Money } from "@/lib/format";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

// ---------- Layout ----------
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 text-base text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="no-print flex flex-wrap items-center gap-2.5">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className, pad = true }: {
  title?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={cx("rounded-xl border border-line bg-white shadow-card", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {actions}
        </div>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}

// ---------- Buttons ----------
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" | "lg"; busy?: boolean; icon?: React.ReactNode;
};

const BTN_BASE = "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap";
const BTN_SIZE = { sm: "min-h-10 px-3.5 text-sm", md: "min-h-11 px-5 text-base", lg: "min-h-13 px-6 text-lg" };
const BTN_VARIANT = {
  primary: "bg-sidebar text-white hover:bg-sidebar-hover shadow-sm",
  secondary: "border-2 border-soft bg-white text-ink hover:border-accent hover:bg-soft-2",
  ghost: "text-accent-strong underline-offset-4 hover:bg-soft-2 hover:underline",
  danger: "border-2 border-bad/40 bg-white text-bad hover:bg-bad-bg",
};

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "secondary", size = "md", busy, icon, className, children, disabled, type = "button", ...rest }, ref) {
  return (
    <button ref={ref} type={type} className={cx(BTN_BASE, BTN_SIZE[size], BTN_VARIANT[variant], className)} disabled={disabled || busy} {...rest}>
      {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : icon}
      {busy ? "Please wait…" : children}
    </button>
  );
});

export function LinkButton({ href, children, variant = "secondary", icon, size = "md" }: { href: string; children: React.ReactNode; variant?: "primary" | "secondary"; icon?: React.ReactNode; size?: "sm" | "md" | "lg" }) {
  return (
    <Link href={href} className={cx(BTN_BASE, BTN_SIZE[size], BTN_VARIANT[variant])}>
      {icon}{children}
    </Link>
  );
}

// ---------- Form fields ----------
export function Field({ label, hint, error, children, className, required }: {
  label: string; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; className?: string; required?: boolean;
}) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-base font-medium text-ink">
        {label}
        {required && <span className="ml-1 text-sm font-normal text-bad">(must fill)</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1.5 block text-sm text-muted">{hint}</span>}
      {error && <span className="mt-1.5 flex items-center gap-1.5 text-sm font-medium text-bad"><AlertTriangle className="h-4 w-4" />{error}</span>}
    </label>
  );
}

// A caller's own width class (w-auto, w-64…) replaces the default full width.
const widthed = (base: string, className?: string) => (/(^|\s)w-/.test(className ?? "") ? base.replace("w-full ", "") : base);
const inputCls = "min-h-11 w-full rounded-lg border-2 border-soft bg-white px-3.5 text-base text-ink placeholder:text-muted focus:border-accent-strong focus:outline-none focus:ring-4 focus:ring-accent/20 disabled:bg-soft-2 disabled:text-muted";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cx(widthed(inputCls, className), p.type === "number" && "num text-right", className)} {...p} />;
});

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx(widthed(inputCls, className), "cursor-pointer pr-9", className)} {...p}>{children}</select>;
}

export function Textarea({ className, ...p }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(inputCls, "min-h-[84px] py-2.5", className)} {...p} />;
}

export function Checkbox({ label, ...p }: React.InputHTMLAttributes<HTMLInputElement> & { label: React.ReactNode }) {
  return (
    <label className="inline-flex min-h-11 cursor-pointer items-center gap-3 text-base text-ink">
      <input type="checkbox" className="h-5 w-5 shrink-0 cursor-pointer rounded border-soft accent-[#34443F]" {...p} />
      {label}
    </label>
  );
}

// ---------- Display ----------
export function Amount({ value, className, strong, muted }: { value: Money; className?: string; strong?: boolean; muted?: boolean }) {
  return <span className={cx("num whitespace-nowrap", strong && "font-semibold", muted && "text-muted", className)}>{inr(value)}</span>;
}

// Plain words for every status. Each badge also carries a symbol so colour is never the only signal.
const BADGE: Record<string, [string, string]> = {
  paid: ["✓ Paid", "bg-ok-bg text-ok"], posted: ["✓ Saved", "bg-ok-bg text-ok"], partial: ["◐ Part paid", "bg-info-bg text-info"],
  unpaid: ["○ Not paid", "bg-soft-2 text-ink"], overdue: ["! Late", "bg-bad-bg text-bad"], draft: ["✎ Not finished", "bg-soft-2 text-ink"],
  cancelled: ["✕ Cancelled", "bg-soft-2 text-muted"], pending_approval: ["⏳ Waiting for approval", "bg-warn-bg text-warn"],
  rejected: ["✕ Rejected", "bg-bad-bg text-bad"], verify: ["⏳ Waiting for checking", "bg-warn-bg text-warn"], locked: ["🔒 Locked", "bg-soft-2 text-ink"],
  active: ["✓ Active", "bg-ok-bg text-ok"], inactive: ["Turned off", "bg-soft-2 text-muted"], opening: ["From old books", "bg-info-bg text-info"],
};

export function Badge({ kind, children }: { kind: string; children?: React.ReactNode }) {
  const [label, cls] = BADGE[kind] ?? [kind, "bg-soft-2 text-ink"];
  return <span className={cx("inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-1 text-sm font-medium", cls)}>{children ?? label}</span>;
}

/** Status for an invoice/bill combining saved status and payment status. */
export function DocStatus({ status, payment_status, is_overdue, overdue_days, draftLabel }: {
  status: string; payment_status?: string; is_overdue?: boolean; overdue_days?: number; draftLabel?: string;
}) {
  if (status === "draft") return <Badge kind={draftLabel === "verify" ? "verify" : "draft"} />;
  if (status !== "posted") return <Badge kind={status} />;
  if (payment_status === "paid") return <Badge kind="paid" />;
  if (is_overdue) return <Badge kind="overdue">{`! Late by ${overdue_days} day${overdue_days === 1 ? "" : "s"}`}</Badge>;
  return <Badge kind={payment_status ?? "unpaid"} />;
}

export function Spinner({ label = "Loading, please wait…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-14 text-base text-muted" role="status">
      <Loader2 className="h-6 w-6 animate-spin" /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 border-bad/25 bg-bad-bg px-5 py-4 text-base text-bad" role="alert">
      <span className="flex items-center gap-2"><XCircle className="h-5 w-5 shrink-0" />{message}</span>
      {onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="px-6 py-14 text-center">
      <p className="text-lg font-medium text-ink">{title}</p>
      {children && <div className="mt-1.5 text-base text-muted">{children}</div>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "bad" | "ok"; children: React.ReactNode }) {
  const t = { info: "bg-info-bg text-info", warn: "bg-warn-bg text-warn", bad: "bg-bad-bg text-bad", ok: "bg-ok-bg text-ok" }[tone];
  const Icon = { info: Info, warn: AlertTriangle, bad: XCircle, ok: CheckCircle2 }[tone];
  return (
    <div className={cx("flex gap-3 rounded-lg px-4 py-3 text-base", t)} role={tone === "bad" ? "alert" : undefined}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" /><div>{children}</div>
    </div>
  );
}

/** "Please fill these before saving" list — shown instead of a silently greyed-out button. */
export function MissingList({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <Notice tone="warn">
      <div className="font-semibold">Before saving, please:</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">{items.map((i) => <li key={i}>{i}</li>)}</ul>
    </Notice>
  );
}

// ---------- Tabs ----------
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[] }) {
  return (
    <div className="no-print mb-6 flex flex-wrap gap-2" role="tablist">
      {items.map((it) => {
        const on = value === it.value;
        return (
          <button key={it.value} role="tab" aria-selected={on} onClick={() => onChange(it.value)}
            className={cx("min-h-11 rounded-lg border-2 px-4 text-base font-medium transition-colors",
              on ? "border-sidebar bg-sidebar text-white" : "border-soft bg-white text-ink hover:border-accent")}>
            {it.label}
            {!!it.count && <span className={cx("ml-2 rounded-full px-2 py-0.5 text-sm", on ? "bg-white/20" : "bg-warn-bg text-warn")}>{it.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

// ---------- Table ----------
export type Col<T> = { key: string; label: string; align?: "right" | "left"; render: (row: T) => React.ReactNode; className?: string };

/** Rows that can be opened get a visible "Open" button — no hidden click targets. */
export function Table<T>({ cols, rows, onRowClick, rowKey, foot, empty = "Nothing here yet.", emptyAction, openLabel = "Open" }: {
  cols: Col<T>[]; rows: T[]; onRowClick?: (r: T) => void; rowKey: (r: T) => string | number; foot?: React.ReactNode;
  empty?: string; emptyAction?: React.ReactNode; openLabel?: string;
}) {
  if (!rows.length) return <Empty title={empty} action={emptyAction} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-base">
        <thead>
          <tr className="border-b-2 border-line bg-soft-2">
            {cols.map((c) => (
              <th key={c.key} className={cx("whitespace-nowrap px-4 py-3 text-sm font-semibold text-ink",
                c.align === "right" ? "text-right" : "text-left")}>{c.label}</th>
            ))}
            {onRowClick && <th className="w-24 px-4 py-3"><span className="sr-only">Open</span></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={cx("border-b border-line last:border-0", onRowClick && "cursor-pointer hover:bg-soft-2")}>
              {cols.map((c) => (
                <td key={c.key} className={cx("px-4 py-3.5 align-middle", c.align === "right" && "text-right", c.className)}>{c.render(r)}</td>
              ))}
              {onRowClick && (
                <td className="px-3 py-2 text-right">
                  <span className="inline-flex items-center gap-0.5 rounded-lg border-2 border-soft px-3 py-1.5 text-sm font-medium text-ink">
                    {openLabel}<ChevronRight className="h-4 w-4" />
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
        {foot && <tfoot className="border-t-2 border-soft bg-soft-2 font-semibold">{foot}</tfoot>}
      </table>
    </div>
  );
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return <div className="px-4 py-3 text-sm text-muted">Showing all {total}</div>;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-base text-muted">
      <span>Page {page} of {pages} · {total} in total</span>
      <div className="flex gap-2">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Previous page</Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next page →</Button>
      </div>
    </div>
  );
}

// ---------- Modal ----------
export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  // Clicking outside does NOT close it, so half-typed work is never lost by accident.
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 pt-[6vh]">
      <div className={cx("w-full rounded-xl bg-white shadow-2xl", wide ? "max-w-4xl" : "max-w-xl")} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-center justify-between gap-3 border-b border-line px-6 py-4">
          <h3 className="text-xl font-semibold">{title}</h3>
          <button onClick={onClose} className="inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-base text-muted hover:bg-soft-2" aria-label="Close this window">
            <X className="h-5 w-5" /> Close
          </button>
        </div>
        <div className="max-h-[72vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2.5 border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

/** Ask for a reason (cancel / reject). */
export function ReasonModal({ open, title, confirmLabel, onClose, onConfirm, note }: {
  open: boolean; title: string; confirmLabel: string; onClose: () => void; onConfirm: (reason: string) => Promise<void>; note?: React.ReactNode;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setReason(""); setErr(null); } }, [open]);
  return (
    <Modal open={open} onClose={onClose} title={title} footer={<>
      <Button onClick={onClose}>No, go back</Button>
      <Button variant="danger" busy={busy} onClick={async () => {
        if (reason.trim().length < 3) return setErr("Please write a short reason (a few words).");
        setBusy(true); setErr(null);
        try { await onConfirm(reason.trim()); onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
      }}>{confirmLabel}</Button>
    </>}>
      {note && <div className="mb-4"><Notice tone="warn">{note}</Notice></div>}
      <Field label="Why? (a few words)" error={err}>
        <Textarea autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="For example: wrong dealer selected" />
      </Field>
    </Modal>
  );
}

// ---------- Confirm (replaces the browser's small confirm box) ----------
type ConfirmOpts = { title: string; message: React.ReactNode; yes: string; no?: string; danger?: boolean };
const ConfirmCtx = createContext<(o: ConfirmOpts) => Promise<boolean>>(async () => false);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOpts | null>(null);
  const resolver = useRef<(v: boolean) => void>(() => {});
  const ask = useCallback((o: ConfirmOpts) => new Promise<boolean>((res) => { resolver.current = res; setOpts(o); }), []);
  const done = (v: boolean) => { resolver.current(v); setOpts(null); };
  return (
    <ConfirmCtx.Provider value={ask}>
      {children}
      <Modal open={!!opts} onClose={() => done(false)} title={opts?.title ?? ""} footer={opts && <>
        <Button onClick={() => done(false)}>{opts.no ?? "No, go back"}</Button>
        <Button variant={opts.danger ? "danger" : "primary"} onClick={() => done(true)}>{opts.yes}</Button>
      </>}>
        <div className="text-base text-ink">{opts?.message}</div>
      </Modal>
    </ConfirmCtx.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmCtx);

// ---------- Messages ----------
type Toast = { id: number; text: string; tone: "ok" | "bad" | "warn" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

/** Large messages at the top of the screen that stay long enough to read, and can be closed. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const remove = (id: number) => setItems((x) => x.filter((t) => t.id !== id));
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), tone === "ok" ? 7000 : 12000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="no-print fixed inset-x-0 top-4 z-[60] flex flex-col items-center gap-2 px-4" aria-live="polite">
        {items.map((t) => {
          const Icon = t.tone === "ok" ? CheckCircle2 : t.tone === "warn" ? AlertTriangle : XCircle;
          return (
            <div key={t.id} className={cx("flex w-full max-w-xl items-start gap-3 rounded-xl px-5 py-4 text-lg shadow-2xl",
              t.tone === "ok" ? "bg-sidebar text-white" : t.tone === "warn" ? "border-2 border-warn/30 bg-warn-bg text-warn" : "border-2 border-bad/30 bg-bad-bg text-bad")}>
              <Icon className="mt-0.5 h-6 w-6 shrink-0" />
              <span className="flex-1">{t.text}</span>
              <button onClick={() => remove(t.id)} className="rounded p-1 opacity-80 hover:opacity-100" aria-label="Close message"><X className="h-5 w-5" /></button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
