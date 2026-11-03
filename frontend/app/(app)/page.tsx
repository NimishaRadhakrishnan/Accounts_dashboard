"use client";

import { AlertTriangle, ChevronRight, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAuth } from "@/lib/auth";
import { ago, money, num, type Money } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { BarRow, Change, DetailSheet, GREEN, LAST_YEAR, Spark, StoryLine } from "@/components/overview-parts";
import { Card, cx, Empty, ErrorBox, Spinner } from "@/components/ui";

type Tile = { value: Money; compare: Money; last_year: Money | null; change_pct: number | null; good_when_up: boolean; spark: Money[];
  purchases?: Money; payables?: Money; late?: Money; stock_included?: boolean };
type Overview = {
  period: { key: string; title: string; label: string; compare_label: string; last_year_label: string; days: number; to: string };
  freshness: { minutes_ago: number | null; stale: boolean; error: string | null; company: string };
  story: { tone: string; kind: string; text: string }[];
  tiles: Record<"sales" | "collections" | "expenses" | "profit" | "cash" | "receivables", Tile>;
  sales_chart: { this_year_label: string; last_year_label: string; months: { month: string; this_year: Money | null; last_year: Money | null }[] };
  owe_us: { party: string; owed: Money; late: Money; oldest_late_days: number }[];
  top_dealers: { party: string; amount: Money; change_pct: number | null }[];
  spending: { name: string; amount: Money; change_pct: number | null }[];
  spending_other: Money;
  products: { item: string; amount: Money; qty: Money; unit: string }[];
  month_labels: string[];
};

type PeriodKey = "month" | "last_month" | "year";

function defaultPeriod(): PeriodKey {
  // In the first week of a month there is too little to judge, so start on last month.
  return new Date().getDate() <= 7 ? "last_month" : "month";
}

function Freshness({ f, onRefresh, loading }: { f: Overview["freshness"]; onRefresh: () => void; loading: boolean }) {
  const bad = f.stale || !!f.error;
  return (
    <div className={cx("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-3 py-2 text-base", bad ? "bg-warn-bg text-warn" : "bg-ok-bg text-ok")} role="status">
      <span className={cx("h-2.5 w-2.5 rounded-full", bad ? "bg-warn" : "bg-ok")} />
      <span>{bad ? <AlertTriangle className="mr-1 inline h-4 w-4" /> : null}
        Updated from Tally {ago(f.minutes_ago)}
        {f.stale && " — the Tally computer may be switched off. Figures may be old."}
        {!f.stale && f.error && ` — last try had a problem: ${f.error}`}
      </span>
      <button onClick={onRefresh} className="inline-flex items-center gap-1 underline underline-offset-4" aria-label="Check for new figures">
        <RefreshCw className={cx("h-4 w-4", loading && "animate-spin")} /> Refresh
      </button>
    </div>
  );
}

const TILE_INFO: { key: keyof Overview["tiles"]; label: string; hint: string }[] = [
  { key: "sales", label: "Sales", hint: "billed to dealers, before GST" },
  { key: "collections", label: "Money collected", hint: "received from dealers" },
  { key: "expenses", label: "Expenses", hint: "salaries, rent, fuel and more" },
  { key: "profit", label: "Profit (estimate)", hint: "sales minus costs" },
  { key: "cash", label: "Cash and bank", hint: "money we have now" },
  { key: "receivables", label: "Dealers owe us", hint: "still to be paid" },
];

function KpiTile({ info, t, vs, months, onOpen }: { info: (typeof TILE_INFO)[number]; t: Tile; vs: string; months: string[]; onOpen: () => void }) {
  const balanceTile = info.key === "cash" || info.key === "receivables";
  let foot: React.ReactNode = null;
  if (info.key === "cash" && t.payables !== undefined) foot = <>We owe suppliers <b className="text-ink">{money(t.payables)}</b></>;
  if (info.key === "receivables" && t.late !== undefined)
    foot = num(t.late) > 0 ? <span className="font-medium text-bad">{money(t.late)} of this is late</span> : <span className="text-ok">Nothing is late</span>;
  if (info.key === "expenses" && t.purchases !== undefined) foot = <>Materials bought: <b className="text-ink">{money(t.purchases)}</b></>;
  if (info.key === "profit") foot = <>An estimate{t.stock_included ? ", includes stock change" : ""}</>;
  return (
    <button onClick={onOpen} className="group flex flex-col rounded-xl border-2 border-line bg-white p-3.5 text-left shadow-card transition-colors hover:border-accent sm:p-5">
      <div className="text-base font-semibold leading-tight text-ink">{info.label}</div>
      <div className="hidden text-sm text-muted sm:block">{info.hint}</div>
      <div className={cx("num mt-2 text-xl font-bold leading-tight sm:text-3xl", info.key === "profit" && num(t.value) < 0 && "text-bad")}>{money(t.value)}</div>
      <div className="mt-1 min-h-6"><Change pct={t.change_pct} goodWhenUp={t.good_when_up} vs={balanceTile ? "at the start" : vs} size="sm" /></div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <Spark values={t.spark} labels={months} />
        <span className="hidden text-xs text-muted sm:inline">12 months</span>
      </div>
      {foot && <div className="mt-2 hidden border-t border-line pt-2 text-sm text-muted sm:block">{foot}</div>}
      <div className="mt-auto flex items-center gap-1 pt-2 text-sm font-medium text-accent-strong">Details <ChevronRight className="h-4 w-4" /></div>
    </button>
  );
}

function useNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const f = () => setNarrow(window.innerWidth < 640);
    f();
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return narrow;
}

const axisMoney = (v: number) => (v >= 1e7 ? `₹${(v / 1e7).toFixed(1)}Cr` : v >= 1e5 ? `₹${Math.round(v / 1e5)}L` : `₹${Math.round(v / 1e3)}K`);

function SalesChart({ c, partialMonth }: { c: Overview["sales_chart"]; partialMonth: string | null }) {
  const narrow = useNarrow();
  const data = c.months.map((m) => ({ month: m.month, thisYear: m.this_year === null ? null : num(m.this_year), lastYear: m.last_year === null ? null : num(m.last_year) }));
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-base">
        <span className="flex items-center gap-2"><span className="h-3.5 w-3.5 rounded-sm" style={{ background: GREEN }} />This year ({c.this_year_label})</span>
        <span className="flex items-center gap-2"><span className="h-1 w-5 rounded" style={{ background: LAST_YEAR }} />Last year ({c.last_year_label})</span>
      </div>
      <div className="h-64 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="#e3e9e5" />
            <XAxis dataKey="month" tickLine={false} axisLine={{ stroke: "#dce4df" }} tick={{ fontSize: 14, fill: "#4f5d56" }} interval={narrow ? 1 : 0} />
            <YAxis tickLine={false} axisLine={false} width={narrow ? 46 : 56} tick={{ fontSize: 13, fill: "#4f5d56" }} tickFormatter={axisMoney} />
            <Tooltip cursor={{ fill: "rgba(220,228,223,0.45)" }} content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const ty = payload.find((p) => p.dataKey === "thisYear")?.value as number | undefined;
              const ly = payload.find((p) => p.dataKey === "lastYear")?.value as number | undefined;
              return (
                <div className="rounded-lg border border-line bg-white px-4 py-3 text-base shadow-lg">
                  <div className="mb-1 font-semibold">{label}{label === partialMonth ? " (so far)" : ""}</div>
                  {ty !== undefined && ty !== null && <div>This year: <b className="num">{money(ty)}</b></div>}
                  {ly !== undefined && ly !== null && <div className="text-muted">Last year: <span className="num">{money(ly)}</span></div>}
                </div>
              );
            }} />
            <Bar dataKey="thisYear" fill={GREEN} maxBarSize={28} radius={[4, 4, 0, 0]} />
            <Line dataKey="lastYear" stroke={LAST_YEAR} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "#fff", fill: LAST_YEAR }} connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {partialMonth && <p className="mt-2 text-sm text-muted">{partialMonth} is not over yet, so its bar is only part of the month.</p>}
    </>
  );
}

export default function OverviewPage() {
  const { me } = useAuth();
  const [period, setPeriod] = useState<PeriodKey>("month");
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    let p: PeriodKey = defaultPeriod();
    try { p = (sessionStorage.getItem("vbt-period") as PeriodKey) || p; } catch { /* ignore */ }
    setPeriod(p);
    setReady(true);
  }, []);
  const choose = (p: PeriodKey) => { setPeriod(p); try { sessionStorage.setItem("vbt-period", p); } catch { /* ignore */ } };
  const { data, error, loading, reload } = useApi<Overview>(ready ? `/api/overview?period=${period}` : null);

  // keep the screen up to date by itself
  useEffect(() => {
    const t = setInterval(() => reload(), 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [reload]);

  const lastMonthName = useMemo(() => {
    const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1);
    return d.toLocaleDateString("en-IN", { month: "long" });
  }, []);
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const partial = data && data.period.key !== "last_month" ? new Date(data.period.to).toLocaleDateString("en-IN", { month: "short" }) : null;

  const chips: { key: PeriodKey; label: string; short: string }[] = [
    { key: "month", label: "This month so far", short: "This month" },
    { key: "last_month", label: lastMonthName, short: lastMonthName.slice(0, 3) },
    { key: "year", label: "This year", short: "This year" },
  ];

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">{hello}, {me?.full_name.split(" ")[0]}</h1>
          <p className="mt-1 text-lg text-muted">Here is how the business is doing.</p>
        </div>
        <div className="grid w-full grid-cols-3 gap-2 sm:flex sm:w-auto" role="tablist" aria-label="Which period">
          {chips.map((c) => (
            <button key={c.key} role="tab" aria-selected={period === c.key} onClick={() => choose(c.key)}
              className={cx("min-h-12 rounded-full border-2 px-2 text-base font-semibold transition-colors sm:px-5",
                period === c.key ? "border-sidebar bg-sidebar text-white" : "border-soft bg-white text-ink hover:border-accent")}>
              <span className="sm:hidden">{c.short}</span><span className="hidden sm:inline">{c.label}</span>
            </button>
          ))}
        </div>
      </div>

      {error ? (
        error.includes("No data from Tally")
          ? <Card><Empty title="Waiting for the first figures from Tally">The administrator needs to set up the Tally connector on the office computer (Settings → Tally link). Figures appear here automatically after that.</Empty></Card>
          : <ErrorBox message={error} onRetry={reload} />
      ) : !data ? <Spinner label="Getting the latest figures…" /> : (
        <div className={cx("space-y-6 transition-opacity", loading && "opacity-60")}>
          <Freshness f={data.freshness} onRefresh={reload} loading={loading} />

          <Card title={<span>In short — {data.period.label}</span>}>
            <ul className="-my-1 divide-y divide-line">
              {data.story.map((s, i) => <StoryLine key={i} tone={s.tone} text={s.text} onClick={() => setOpen(s.kind)} />)}
            </ul>
          </Card>

          <section aria-label="Main figures">
            <p className="mb-3 text-base text-muted">Arrows compare with {data.period.compare_label}. Green is good news, red needs a look. Tap any box for details.</p>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
              {TILE_INFO.map((info) => (
                <KpiTile key={info.key} info={info} t={data.tiles[info.key]} vs={data.period.compare_label.replace(/ \(.*\)$/, "")}
                  months={data.month_labels} onOpen={() => setOpen(info.key)} />
              ))}
            </div>
          </section>

          <Card title="Sales, month by month">
            <SalesChart c={data.sales_chart} partialMonth={partial} />
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Dealers who owe us the most" actions={<button onClick={() => setOpen("receivables")} className="text-base font-medium text-accent-strong underline underline-offset-4">See all</button>}>
              {data.owe_us.length ? (
                <ul className="divide-y divide-line">
                  {data.owe_us.map((r) => (
                    <li key={r.party} className="flex items-center gap-3 py-3">
                      <span className="min-w-0 flex-1">
                        <span className="block text-base font-medium">{r.party}</span>
                        {num(r.late) > 0
                          ? <span className="text-sm font-medium text-bad">{money(r.late)} late · oldest {r.oldest_late_days} days</span>
                          : <span className="text-sm text-ok">Not late</span>}
                      </span>
                      <span className="num text-lg font-semibold">{money(r.owed)}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-base text-ok">No dealer owes us anything.</p>}
            </Card>

            <Card title={`Best dealers — ${data.period.label}`} actions={<button onClick={() => setOpen("sales")} className="text-base font-medium text-accent-strong underline underline-offset-4">See all</button>}>
              {data.top_dealers.length ? (() => {
                const max = Math.max(...data.top_dealers.map((r) => num(r.amount)));
                return <div className="divide-y divide-line">{data.top_dealers.map((r) => (
                  <BarRow key={r.party} label={r.party} value={r.amount} max={max} right={<Change pct={r.change_pct} size="sm" />} />))}</div>;
              })() : <p className="text-base text-muted">No sales in this period yet.</p>}
            </Card>

            <Card title="Where the money went" actions={<button onClick={() => setOpen("expenses")} className="text-base font-medium text-accent-strong underline underline-offset-4">See all</button>}>
              {data.spending.length ? (() => {
                const max = Math.max(...data.spending.map((r) => num(r.amount)));
                return <div className="divide-y divide-line">
                  {data.spending.map((r) => <BarRow key={r.name} label={r.name} value={r.amount} max={max} right={<Change pct={r.change_pct} goodWhenUp={false} size="sm" />} />)}
                  {num(data.spending_other) > 0 && <div className="flex justify-between py-2.5 text-base text-muted"><span>Everything else</span><span className="num">{money(data.spending_other)}</span></div>}
                </div>;
              })() : <p className="text-base text-muted">No expenses in this period yet.</p>}
            </Card>

            {data.products.length > 0 && (
              <Card title={`Best-selling products — ${data.period.label}`}>
                {(() => {
                  const max = Math.max(...data.products.map((r) => num(r.amount)));
                  return <div className="divide-y divide-line">{data.products.map((r) => (
                    <BarRow key={r.item} label={r.item} value={r.amount} max={max} sub={`${num(r.qty).toLocaleString("en-IN")} ${r.unit}`} />))}</div>;
                })()}
              </Card>
            )}
          </div>

          <p className="pb-4 text-center text-sm text-muted">
            Figures come straight from Tally ({data.freshness.company}). Amounts are before GST. Nothing on this screen changes Tally.
          </p>
        </div>
      )}
      <DetailSheet kind={open} period={period} onClose={() => setOpen(null)} />
    </>
  );
}
