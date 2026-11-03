"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronRight, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { inr, money, num, type Money } from "@/lib/format";
import { cx, ErrorBox, Modal, Spinner } from "./ui";

export const GREEN = "#1d7f5f"; // validated series colour (see dataviz check in README)
export const LAST_YEAR = "#8b968f"; // context series: always grey, always labelled

// ---------- change chip: arrow + words, colour only reinforces ----------
export function Change({ pct, goodWhenUp = true, vs, size = "md" }: { pct: number | null | undefined; goodWhenUp?: boolean; vs?: string; size?: "sm" | "md" }) {
  if (pct === null || pct === undefined || !isFinite(pct)) {
    return vs ? <span className="text-sm text-muted">Nothing to compare with {vs}</span> : null;
  }
  const flat = Math.abs(pct) < 1;
  const up = pct > 0;
  const good = flat ? null : up === goodWhenUp;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cx("inline-flex items-center gap-1 font-semibold", size === "sm" ? "text-sm" : "text-base",
      good === null ? "text-muted" : good ? "text-ok" : "text-bad")}>
      <Icon className={size === "sm" ? "h-4 w-4" : "h-5 w-5"} strokeWidth={2.5} />
      {flat ? "Same" : up && pct >= 100 ? `${pct >= 900 ? "10+" : (1 + pct / 100).toFixed(1)} times as much` : `${Math.abs(pct).toFixed(0)}% ${up ? "more" : "less"}`}
      {vs && <span className="hidden font-normal text-muted sm:inline">{up && pct >= 100 ? "as" : "than"} {vs}</span>}
    </span>
  );
}

// ---------- 12-month sparkline ----------
export function Spark({ values, labels }: { values: Money[]; labels?: string[] }) {
  const v = values.map(num);
  if (v.length < 2) return null;
  const w = 120, h = 36, pad = 4;
  const min = Math.min(...v), max = Math.max(...v);
  const span = max - min || 1;
  const pts = v.map((y, i) => [pad + (i * (w - pad * 2)) / (v.length - 1), h - pad - ((y - min) / span) * (h - pad * 2)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-[120px]" role="img"
      aria-label={`Last 12 months${labels ? ` (${labels[0]}–${labels[labels.length - 1]})` : ""}: lowest ${money(min)}, highest ${money(max)}`}>
      <path d={d} fill="none" stroke={GREEN} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={3.5} fill={GREEN} stroke="#fff" strokeWidth={2} />
    </svg>
  );
}

// ---------- horizontal bars ----------
export function BarRow({ label, value, max, sub, right, onClick }: {
  label: React.ReactNode; value: Money; max: number; sub?: React.ReactNode; right?: React.ReactNode; onClick?: () => void;
}) {
  const w = max > 0 ? Math.max(1.5, (Math.abs(num(value)) / max) * 100) : 0;
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={cx("block w-full py-2.5 text-left", onClick && "rounded-lg px-2 -mx-2 hover:bg-soft-2")}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-base font-medium">{label}</span>
        <span className="num shrink-0 text-base font-semibold">{money(value)}</span>
      </div>
      <div className="mt-1.5 h-2.5 rounded-full bg-soft-2">
        <div className="h-2.5 rounded-full" style={{ width: `${w}%`, background: GREEN }} />
      </div>
      {(sub || right) && (
        <div className="mt-1 flex items-center justify-between gap-3 text-sm text-muted">
          <span>{sub}</span><span>{right}</span>
        </div>
      )}
    </Tag>
  );
}

// ---------- story line ----------
const TONE: Record<string, { icon: typeof ArrowUpRight; cls: string; label: string }> = {
  up: { icon: ArrowUpRight, cls: "bg-ok-bg text-ok", label: "Went up" },
  down: { icon: ArrowDownRight, cls: "bg-bad-bg text-bad", label: "Went down" },
  warn: { icon: AlertTriangle, cls: "bg-warn-bg text-warn", label: "Needs attention" },
  good: { icon: CheckCircle2, cls: "bg-ok-bg text-ok", label: "Good news" },
  neutral: { icon: Minus, cls: "bg-soft-2 text-muted", label: "Note" },
};

export function StoryLine({ tone, text, onClick }: { tone: string; text: string; onClick?: () => void }) {
  const t = TONE[tone] ?? TONE.neutral;
  const Icon = t.icon;
  return (
    <li>
      <button onClick={onClick} className="flex w-full items-start gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-soft-2">
        <span className={cx("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", t.cls)} title={t.label}>
          <Icon className="h-5 w-5" strokeWidth={2.5} /><span className="sr-only">{t.label}:</span>
        </span>
        <span className="flex-1 text-lg leading-snug">{text}</span>
        <ChevronRight className="mt-1.5 h-5 w-5 shrink-0 text-muted" />
      </button>
    </li>
  );
}

// ---------- detail sheet ----------
type Row = Record<string, Money | string | number | null | undefined> & { label: string; value: Money };
type Section = { title: string; kind: "bars" | "sum" | "ageing"; rows: Row[] };
type Detail = { title: string; explain: string; sections: Section[] };

export function DetailSheet({ kind, period, onClose }: { kind: string | null; period: string; onClose: () => void }) {
  const [data, setData] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!kind) return;
    setData(null); setErr(null);
    get<Detail>(`/api/overview/${kind}?period=${period}`).then(setData).catch((e) => setErr(e.message));
  }, [kind, period]);
  return (
    <Modal open={!!kind} onClose={onClose} wide title={data?.title ?? "Details"}>
      {err ? <ErrorBox message={err} /> : !data ? <Spinner /> : (
        <div className="space-y-6">
          <p className="text-base text-muted">{data.explain}</p>
          {data.sections.map((s) => (
            <section key={s.title}>
              <h4 className="mb-2 text-lg font-semibold">{s.title}</h4>
              {s.kind === "bars" && <Bars rows={s.rows} />}
              {s.kind === "sum" && <Sum rows={s.rows} />}
              {s.kind === "ageing" && <Ageing rows={s.rows} />}
              {!s.rows.length && <p className="text-base text-muted">Nothing for this period.</p>}
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}

function Bars({ rows }: { rows: Row[] }) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(num(r.value))));
  return (
    <div className="divide-y divide-line">
      {rows.map((r) => (
        <BarRow key={r.label} label={r.label} value={r.value} max={max}
          sub={(r.sub as string) ?? (r.note as string) ?? (typeof r.share === "number" && r.share ? `${(r.share as number).toFixed(0)}% of the total` : undefined)}
          right={r.change_pct !== undefined ? <Change pct={r.change_pct as number | null} size="sm" /> : undefined} />
      ))}
    </div>
  );
}

function Sum({ rows }: { rows: Row[] }) {
  return (
    <dl className="space-y-1">
      {rows.map((r, i) => {
        const last = i === rows.length - 1;
        return (
          <div key={r.label} className={cx("flex justify-between px-3 py-2.5 text-lg", last ? "rounded-lg bg-sidebar font-semibold text-white" : "border-b border-line")}>
            <dt>{r.label}</dt><dd className={cx("num", !last && num(r.value) < 0 && "text-bad")}>{num(r.value) < 0 ? "− " : last ? "" : "+ "}{inr(Math.abs(num(r.value)))}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function Ageing({ rows }: { rows: Row[] }) {
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const owed = num(r.value);
        const late = owed > 0 ? owed - num(r.not_due) : 0;
        const segs = [
          { k: "not_due", label: "Not due yet", color: "#a9b7ae" },
          { k: "late_30", label: "Up to 1 month late", color: "#e6b35a" },
          { k: "late_60", label: "1–2 months late", color: "#d98a3d" },
          { k: "late_90", label: "2–3 months late", color: "#c4632f" },
          { k: "late_90_plus", label: "Over 3 months late", color: "#a14a42" },
        ];
        return (
          <div key={r.label} className="rounded-lg border border-line p-3.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-base font-semibold">{r.label}</span>
              <span className="num text-lg font-semibold">{owed < 0 ? `Advance ${money(-owed)}` : money(owed)}</span>
            </div>
            {owed > 0 && <>
              <div className="mt-2 flex h-3 overflow-hidden rounded-full bg-soft-2" aria-hidden="true">
                {segs.map((s) => num(r[s.k]) > 0 && <div key={s.k} style={{ width: `${(num(r[s.k]) / owed) * 100}%`, background: s.color }} className="border-r-2 border-white last:border-0" />)}
              </div>
              <div className="mt-1.5 text-sm">
                {late > 0
                  ? <span className="font-medium text-bad">{money(late)} is late — oldest by {r.oldest_late_days} days</span>
                  : <span className="text-ok">Nothing late</span>}
                <span className="text-muted"> · {r.credit_days} days credit</span>
              </div>
            </>}
          </div>
        );
      })}
      <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-sm text-muted">
        {[["#a9b7ae", "Not due yet"], ["#e6b35a", "Up to 1 month late"], ["#d98a3d", "1–2 months"], ["#c4632f", "2–3 months"], ["#a14a42", "Over 3 months"]].map(([c, l]) => (
          <span key={l} className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: c }} />{l}</span>
        ))}
      </div>
    </div>
  );
}
